"""Local, single-user Brev execution and immutable Studio export adapter."""
from __future__ import annotations
from generation import options, overrides
import hashlib
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import uuid
from urllib.parse import urlparse
import httpx

ROOT = Path(os.environ.get('RFD4_STUDIO_HOME', str(Path.home() / '.local/share/bionemo-rfd4')))
ASSETS = ROOT.parent / 'rfd4-assets'
REVISION = '84d83b98442e5946a6a626d0d99a19773207e894'

def safe_id(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise ValueError('Invalid identifier')
    return value

def safe_session(value: str) -> str:
    # Studio uses URL-safe random tokens, which can begin with '-' or '_'.
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value):
        raise ValueError('Invalid Studio session identifier')
    return value

from compute import Compute
from ownership_operation import OwnershipOperation

class Backend(OwnershipOperation, Compute):
    def __init__(self, root=ROOT, runner=subprocess.run):
        self.root = Path(root)
        from upgrade_state import require_workspace_activation
        require_workspace_activation(self.root)
        self.state = self.root / 'state'
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runner = runner
        self.lock = threading.Lock()

    @property
    def managed(self):
        from upgrade_state import require_workspace_activation
        require_workspace_activation(self.root)
        from managed_state import State
        state = State(self.root)
        return state

    def selected_compute(self, session_id=None):
        state = self.managed
        with state.transaction() as data:
            selection = dict(state._selection(data, session_id or 'workspace'))
            if not selection['machine_id']:
                return selection, None
            machine = data['machines'][selection['machine_id']]
            cfg = self.validate_config(dict(machine['config'], target_id=machine['id'],
                    machine_revision=machine['revision'], selection_revision=selection['revision']))
            return selection, cfg

    def config(self, session_id=None):
        _, cfg = self.selected_compute(session_id)
        if cfg is None:
            raise ValueError('No compute selected for this session. Connect a saved machine in chat.')
        return cfg

    def run(self, args, timeout=60, *, pass_fds=()):
        inherited={'pass_fds':pass_fds} if pass_fds else {}
        try:
            result = self.runner(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, **inherited)
        except subprocess.TimeoutExpired:
            # TimeoutExpired.__str__ includes argv. Publication argv carries
            # the reviewed source bundle; never persist or display that text.
            # This says nothing about whether an external action happened.
            raise TimeoutError(f'Compute command timed out after {timeout} seconds. Its external outcome may be unknown; reconcile the original operation before retrying.') from None
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-4000:])
        return result.stdout

    def brev(self, cfg, *args, timeout=60):
        output = self.run([cfg.get('brev_executable', 'brev'), *args], timeout)
        # Brev exec appends the instance name for its pipeable workflow.
        if args and args[0] == 'exec':
            lines = output.rstrip().splitlines()
            if output.rstrip().endswith(cfg['instance']):
                output = output.rstrip()[:-len(cfg['instance'])].rstrip()
        return output

    def verify_target(self, cfg):
        import registry
        expected = cfg.get('ssh_access') or cfg.get('registry_target', {}).get('host_access')
        if expected: registry.verify_access(expected, self.run)
        if cfg.get('kind','brev') == 'brev':
            from brev_provider import Brev
            if not cfg.get('organization_id'):
                raise ValueError('Legacy Brev target needs its organization verified before access')
            provider = Brev(self.run)
            row = provider.check_context(cfg['organization_id'], cfg['instance_id'])
            if row.get('name') != cfg['instance']:
                raise ValueError('Brev machine name changed; refresh its saved access before execution')
        if cfg.get('target_id'):
            if cfg.get('kind','brev')=='brev':
                identity=registry.machine_identity_from_output(self.target_exec(cfg,'cat /etc/machine-id',timeout=15))
            else:
                identity=registry.linux_machine_identity(cfg,self.run)
            self.managed.bind_physical_identity(cfg['target_id'],identity)


    def preflight(self):
        return self.check_compute()

    def studio_url(self):
        # Editor service can be CPU-only and independent of any GPU target.
        url = os.environ.get('RFD4_EDITOR_URL')
        if not url:
            path=self.root/'editor.json'
            if path.exists(): url=json.loads(path.read_text())['studio_url']
        if not url:
            default = self.root/'config.json'
            if default.exists(): url=json.loads(default.read_text()).get('studio_url')
        if not url: raise ValueError('CPU editor is not configured. Set RFD4_EDITOR_URL or configure editor.json; GPU registration is separate.')
        self.validate_config({'kind':'local','instance':'editor','remote_root':'/tmp','studio_url':url})
        return url

    def studio(self, method, path, **kwargs):
        from editor_runtime import ensure_editor
        ensure_editor(self)
        with httpx.Client(base_url=self.studio_url(), timeout=60, trust_env=False) as client:
            response = client.request(method, '/api/v1/' + path, **kwargs)
            response.raise_for_status()
            return response.json()

    def import_cif(self, cif: str):
        if len(cif.encode()) > 20_000_000 or '_atom_site.' not in cif:
            raise ValueError('Supply a molecular CIF under 20 MB')
        result = self.studio('POST', 'sessions', files={'file': ('design.cif', cif, 'chemical/x-mmcif')})
        result['editor_url'] = self.studio_url().rstrip('/') + result['editor_path'] + '&viewer=molstar'
        return result

    def load_demo(self):
        from editor_runtime import ensure_editor
        ensure_editor(self)
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.get(self.studio_url().rstrip('/') + '/api/v1/examples/protein_binder/cif')
            response.raise_for_status()
        result = self.import_cif(response.text)
        result.update(demo='pdl1-binder', title='Design a binder for PD-L1', samples=1, seed=42,
                      note='Design a protein binder at the prepared PD-L1 hotspots, keeping the target fixed.',
                      description='The PD-L1 target and binding hotspots are prepared. RFD4 will design a 50–120-residue partner.',
                      source='AtomWorks Studio protein_binder.cif; RFD4 all_ppi.yaml:rfd3_pdl1')
        return result

    def annotate(self, session_id, expression, condition):
        safe_session(session_id)
        if condition not in ('hotspot', 'sequence', 'coordinate'):
            raise ValueError('Use hotspot, sequence, or coordinate; inspect other conditions in Studio')
        selection = self.studio('POST', f'sessions/{session_id}/selections/query', json={'expression': expression})
        indices = selection['atom_indices']
        if not indices:
            raise ValueError('Selection matched no atoms; no annotation applied')
        return self.studio('POST', f'sessions/{session_id}/conditions', json={'atom_indices': indices, 'condition': condition})

    def snapshot(self, session_id, note='', markup=None):
        safe_session(session_id)
        if len(note) > 20000:
            raise ValueError('Design note is too long')
        image = None
        if markup:
            markup = dict(markup)
            encoded = markup.pop('image_base64', None)
            if encoded:
                if len(encoded) > 14000000:
                    raise ValueError('Image is too large')
                image = base64.b64decode(encoded, validate=True)
                if not image.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Annotated image must be PNG')
            if len(json.dumps(markup)) > 2000000:
                raise ValueError('Too much markup; simplify the drawing')
        exported = self.studio('POST', f'sessions/{session_id}/export')
        # Match upstream RFD4GenerationProvider.warning_checks; model prevalidation remains enabled.
        exported['issues'] = [dict(i, severity='warning') if i.get('check') == 'missing_atoms' else i for i in exported['issues']]
        errors = [i for i in exported['issues'] if i.get('severity', i.get('level')) == 'error']
        if errors:
            raise ValueError('Studio validation failed: ' + json.dumps(errors))
        snap_id = uuid.uuid4().hex
        directory = self.state / snap_id
        directory.mkdir(mode=0o700)
        cif = exported['cif'].encode()
        (directory / 'input.cif').write_bytes(cif)
        if image:
            (directory / 'annotation.png').write_bytes(image)
        record = {'snapshot_id': snap_id, 'sha256': hashlib.sha256(cif).hexdigest(), 'studio_revision': exported['revision'],
                  'issues': exported['issues'], 'note': note, 'image_markup': markup,
                  'source_revision': REVISION, 'annotation_semantics': 'Image marks are notes; only exported molecular conditions affect generation.'}
        if image:
            record['image_sha256'] = hashlib.sha256(image).hexdigest()
        (directory / 'snapshot.json').write_text(json.dumps(record, indent=2))
        return record

    def read(self, item_id, filename):
        return json.loads((self.state / safe_id(item_id) / filename).read_text())

    def launch(self, snapshot_id, samples=1, seed=42, request_id=None, target=None, generation=None, executor_ownership=None, plan_checksum=None, execution_payload=None):
        if type(samples) is not int or not 1 <= samples <= 16 or type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError('samples must be 1–16 and seed a nonnegative 31-bit integer')
        generation = options(generation)
        cfg = target if target is not None else self.config()
        safe_id(snapshot_id)
        snap = self.read(snapshot_id, 'snapshot.json')
        source = self.state / snapshot_id / 'input.cif'
        if hashlib.sha256(source.read_bytes()).hexdigest() != snap['sha256']:
            raise ValueError('Snapshot was modified; export again')
        job_id = safe_id(request_id or uuid.uuid4().hex)
        with self.lock:
            jobdir = self.state / job_id
            record = {'machine_id': cfg.get('target_id'), 'job_id': job_id, 'snapshot_id': snapshot_id, 'samples': samples, 'seed': seed, 'generation': generation, 'instance': cfg['instance'], 'status': 'queued', 'target': cfg,'remote_dispatch_started':False,'plan_checksum':plan_checksum,'execution_payload':execution_payload}
            if (jobdir / 'job.json').exists():
                existing = self.read(job_id, 'job.json')
                if options(existing.get('generation')) != generation or any(existing[k] != record[k] for k in ('snapshot_id', 'samples', 'seed', 'instance', 'target')):
                    raise ValueError('Request ID already used with different parameters')
                return existing
            # Service.execute already verified the frozen proof before its
            # short acceptance transaction. Never take a state lock or perform
            # network I/O recursively inside that transaction. The detached
            # worker independently rechecks this proof before its first write.
            record['executor_ownership']=(executor_ownership if executor_ownership is not None
                                          else self.require_executor_ownership(cfg))
            jobdir.mkdir(mode=0o700, exist_ok=True)
            self.save_job(record)
        import sys
        worker_log = (jobdir / 'worker.log').open('a')
        try:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker.py')), str(self.root), job_id], stdin=subprocess.DEVNULL, stdout=worker_log, stderr=worker_log, start_new_session=True)
        except Exception as error:
            self.fail_undispatched(record,'Worker could not be spawned: '+str(error))
            raise
        finally:
            worker_log.close()
        return record

    def save_job(self, job):
        from registry import atomic
        target = self.state / job['job_id'] / 'job.json'
        atomic(target,job)

    def fail_undispatched(self, record, reason):
        if record.get('status')!='queued' or record.get('remote_dispatch_started') is True:
            raise ValueError('A possibly dispatched run cannot be classified as safely undispatched')
        record.update(status='failed',error=reason,remote_dispatch_started=False,dispatch_not_started=True)
        self.save_job(record)
        return record

    def _submit(self, cfg, record, source):
        if record.get('status')!='queued':return record
        if record.get('remote_dispatch_started') is True:
            raise ValueError('Queued run has prior dispatch evidence; reconcile it without staging again')
        record['remote_dispatch_started']=False
        try:
            if not record.get('executor_ownership'):
                raise ValueError('Queued run has no reviewed executor ownership proof; preserve it and review a new run.')
            self.require_executor_ownership(cfg,record['executor_ownership'])
            from run_payload import verified
            import execution_adapter
            from execution_payload import canonical, validate_manifest
            review=record.get('execution_payload')
            if not review or not record.get('plan_checksum'):
                raise ValueError('Queued run predates immutable execution publication; preserve its history and review a new run')
            payload=verified(Path(source).parent,review)
            root = cfg['remote_root']
            remote = f"{root}/runs/{record['job_id']}"
            record['remote_dir'] = remote
            attempt=remote+'/uploads/'+uuid.uuid4().hex
            self.target_exec(cfg, f'test -x {shlex.quote(root + "/model/.venv/bin/rfd4-generate")} && test "$(git -C {shlex.quote(root + "/model")} rev-parse HEAD)" = {REVISION} && mkdir -p {shlex.quote(attempt)}')
            self.target_copy(cfg,payload,attempt,timeout=180)
            expected=validate_manifest(review['files'],{'kind':'run','id':record['job_id'],
                'review_checksum':record['plan_checksum'],'executor_ownership':record['executor_ownership']})
            receipt=json.loads(self.target_exec(cfg,execution_adapter.command(attempt+'/'+payload.name,remote+'/payload',expected,record['job_id'],
                reviewed_bundle=review['publication_bundle'],reviewed_files=review['publication_files']),timeout=180))
            if receipt.get('path')!=remote+'/payload' or receipt.get('manifest_sha256')!=hashlib.sha256(canonical(expected)).hexdigest():
                raise ValueError('Published execution receipt differs from accepted run')
            record['runtime_protocol'] = 3
            record['published_payload']=expected
            record['status'] = 'submitting'
            record['remote_dispatch_started']=True
            record.pop('dispatch_not_started',None)
            self.save_job(record)
            # Never automatically retry this launch if the network outcome is ambiguous.
            output = self.target_exec(cfg, shlex.join([root + '/model/.venv/bin/python','-B', remote + '/payload/remote_job.py', 'launch-published', remote, record['job_id'],canonical(expected).decode()]))
            receipt = json.loads(output)
            if receipt.get('job_id') != record['job_id']:
                raise ValueError('Remote launch receipt identity mismatch')
            record['status'] = 'submitted'
        except Exception as error:
            if record.get('remote_dispatch_started') is True:
                record.update(status='submission_unknown',error=str(error))
            else:
                self.fail_undispatched(record,str(error))
        self.save_job(record)
        if record.get('dispatch_not_started') is True:self.status(record['job_id'])
        return record

    def status(self, job_id):
        record = self.read(job_id, 'job.json')
        if record['status'] not in ('submitted', 'submitting', 'submission_unknown', 'running'):
            if record.get('status')=='failed' and record.get('dispatch_not_started') is True and record.get('remote_dispatch_started') is False and record.get('machine_id'):
                self.managed.reconcile_undispatched_run(record)
            if record.get('status')=='queued':
                if record.get('execution_payload') and record.get('remote_dispatch_started') is False and record.get('plan_checksum'):
                    return dict(record,recovery_action='recover_queued_rfd4_job',detail='Waiting for the original worker. If this run stays queued, ask chat to continue this saved run; do not submit another design.')
                return dict(record,detail='This older run has no durable dispatch proof. Inspect its original executor in chat; do not replay it.')
            return record
        if not record.get('remote_dir'):
            return dict(record,detail='No durable remote dispatch path is recorded. Preserve this unresolved run and its machine reservation; inspect the original executor rather than replaying it.')
        cfg = self.validate_config(record['target'])
        self.verify_target(cfg)
        if cfg['instance'] != record['instance']:
            raise ValueError('Restore the original instance in config before polling this job')
        remote = record['remote_dir']
        if record.get('runtime_protocol') in (2,3):
            helper=remote+('/payload' if record.get('runtime_protocol')==3 else '')+'/remote_job.py'
            output = self.target_exec(cfg, shlex.join([cfg['remote_root'] + '/model/.venv/bin/python',
                '-B',helper, 'status', remote, record['job_id']]))
            observed = json.loads(output)
            if observed.get('job_id') != record['job_id']:
                raise ValueError('Remote status identity mismatch')
            record['status'] = observed['state'] if observed.get('state') in ('running','completed','failed') else 'submission_unknown'
            if 'exit_code' in observed: record['exit_code'] = observed['exit_code']
        else:
            output = self.target_exec(cfg, f'if test -f {remote}/exit_code; then cat {remote}/exit_code; elif test -f {remote}/pid && kill -0 "$(cat {remote}/pid)" 2>/dev/null; then echo RUNNING; else echo UNKNOWN; fi')
            value = output.strip()
            if value == '0': record['status'] = 'completed'
            elif value.isdigit(): record.update(status='failed', exit_code=int(value))
            elif value == 'RUNNING': record['status'] = 'running'
            else: record['status'] = 'submission_unknown'
        if record['status'] in ('completed', 'failed') and record.get('machine_id'):
            state = self.managed
            reservation = state.snapshot()['reservations'].get(record['machine_id'])
            if reservation and reservation['owner_id'] == record['job_id']:
                state.release(record['machine_id'], record['job_id'], 'Remote terminal job state verified')
        self.save_job(record)
        return record

    def collect(self, job_id):
        from artifacts import collect
        return collect(self, job_id)

    def open_result(self, job_id, index=0):
        record = self.read(job_id, 'job.json')
        if record['status'] != 'completed':
            raise ValueError('Complete and retrieve this job first')
        files = [Path(p) for p in self.collect(job_id)['files']]
        if type(index) is not int or not 0 <= index < len(files):
            raise ValueError('Retrieve designs first, then choose an available result')
        path = files[index]
        if path.suffix == '.gz':
            import gzip
            with gzip.open(path, 'rt') as handle:
                cif = handle.read(20_000_001)
        else:
            cif = path.read_text()
        result = self.import_cif(cif)
        result['result_file'] = path.name
        return result
