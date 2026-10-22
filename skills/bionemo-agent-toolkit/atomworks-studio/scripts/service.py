from __future__ import annotations

# Local, single-user Brev execution and immutable Studio export adapter.

from runtime_recipe import options, overrides
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
from runtime_recipe import RECIPE
REVISION = RECIPE['model_revision']

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
        if not url:
            from editor_app import default_editor_url
            url = default_editor_url(self.root)
        self.validate_config({'kind':'local','instance':'editor','remote_root':'/tmp','studio_url':url})
        return url

    def studio(self, method, path, **kwargs):
        from editor_app import ensure_editor
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
        from editor_app import ensure_editor
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
                                          else self.require_execution_scope(cfg))
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
            self.require_execution_scope(cfg,record['executor_ownership'])
            from run_payload import verified
            import run_payload as execution_adapter
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


# Checksum-bound planning and process-safe submission around the Studio adapter.
import fcntl
from runtime_recipe import options


from lifecycle import Lifecycle
from setup_operation import SetupOperation
from lifecycle import CreateOperation

class Service(CreateOperation, SetupOperation, Lifecycle, Backend):
    def plans(self):
        return [json.loads(p.read_text()) for p in sorted(self.state.glob('*/plan.json'), key=lambda p:p.stat().st_mtime, reverse=True)]

    def prepare(self, session_id, note='', samples=1, seed=42, image_base64=None, generation=None):
        if type(samples) is not int or not 1 <= samples <= 16 or type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError('Use 1–16 designs and a nonnegative 31-bit seed')
        generation = options(generation)
        snapshot = self.snapshot(session_id, note, {'image_base64': image_base64} if image_base64 else None)
        selection, target = self.selected_compute(session_id)
        if target is None:
            raise ValueError('Connect compute before reviewing a run')
        ownership=self.require_execution_scope(target)
        from run_payload import freeze
        execution=freeze(self.state/snapshot['snapshot_id'],target,snapshot,samples,seed,generation,ownership)
        plan = dict(snapshot, selection=selection, session_id=session_id, samples=samples, seed=seed, generation=generation, target=target, executor_ownership=ownership, execution_payload=execution)
        plan['plan_checksum'] = self.checksum(plan)
        (self.state / plan['snapshot_id'] / 'plan.json').write_text(json.dumps(plan, indent=2))
        return self.public_plan(plan)

    @staticmethod
    def checksum(plan):
        return hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k != 'plan_checksum'},sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @staticmethod
    def public_plan(plan):
        return {k:v for k,v in plan.items() if k not in ('target', 'image_markup', 'execution_payload')} | {'instance':plan['target']['instance'], 'instance_id':plan['target'].get('instance_id', '')}

    def execute(self, plan_id, plan_checksum):
        plan = self.read(plan_id, 'plan.json')
        if plan_checksum != plan['plan_checksum'] or self.checksum(plan) != plan_checksum:
            raise ValueError('Plan changed; prepare and review again')
        source = self.state / safe_id(plan_id) / 'input.cif'
        if hashlib.sha256(source.read_bytes()).hexdigest() != plan['sha256']:
            raise ValueError('Snapshot was modified; prepare and review again')
        # One stable job per approved plan, even across separate MCP processes.
        with (self.state / 'submission.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            # Reopening/retrying an existing run must never submit it elsewhere.
            if (self.state/plan_id/'job.json').exists():
                return self.read(plan_id, 'job.json')
            if not plan.get('execution_payload'):
                raise ValueError('This older plan has no frozen execution payload. Prepare and review a new plan; existing runs remain available.')
            if plan.get('selection') != self.managed.selection(plan.get('session_id') or 'workspace'):
                raise ValueError('Compute selection changed; prepare and review again')
            if plan['target'] != self.config(plan.get('session_id')):
                raise ValueError('Compute configuration changed; prepare and review again')
            state = self.managed
            machine_id = plan['target']['target_id']
            activity = self.compute_status(plan.get('session_id'))
            if activity.get('active_jobs') or activity.get('unresolved_active_jobs'):
                raise ValueError('Existing or unresolved run must be reconciled before another submission')
            state.reserve(machine_id, plan_id, 'run')
            try:
                status = self.check_compute(plan.get('session_id'))
                if status['state'] != 'ready':
                    raise ValueError('Compute is not ready: '+status['detail'])
                if not plan.get('executor_ownership'):
                    raise ValueError('Plan predates required executor ownership; review a new plan.')
                ownership=self.require_execution_scope(plan['target'],plan['executor_ownership'])
                activity=self.machine_jobs(machine_id)
                if activity['active_jobs'] or activity['unresolved_active_jobs']:
                    raise ValueError('Active or unresolved jobs on the verified host block submission')
                # Linearization point: once the durable job is accepted, a later
                # disconnect leaves it running. Before this point it invalidates approval.
                with state.transaction() as data:
                    if plan['selection'] != state._selection(data, plan.get('session_id') or 'workspace'):
                        raise ValueError('Compute selection changed; prepare and review again')
                    return self.launch(plan_id, plan['samples'], plan['seed'], request_id=plan_id,
                                       target=plan['target'], generation=plan.get('generation'), executor_ownership=ownership, plan_checksum=plan['plan_checksum'], execution_payload=plan['execution_payload'])
            except Exception:
                job_path = self.state/plan_id/'job.json'
                if not job_path.exists() or self.read(plan_id, 'job.json')['status'] == 'failed':
                    state.release(machine_id, plan_id, 'No remote dispatch; submission preparation failed')
                raise

    def recover_queued_job(self, job_id, accepted_plan_checksum):
        """Explicit continuation of an accepted job, never a new plan or run."""
        if not isinstance(accepted_plan_checksum,str) or len(accepted_plan_checksum)!=64:
            raise ValueError('Provide the original accepted plan checksum')
        from worker import run_worker
        return run_worker(self.root,safe_id(job_id),accepted_plan_checksum=accepted_plan_checksum)

    def save_draft(self, session_id, note='', image_base64=None, settings=None):
        """Save even incomplete designs; validation is required only for review."""
        safe_session(session_id)
        if len(note)>20000 or len(json.dumps(settings))>10000: raise ValueError('Draft notes are too large')
        import base64
        if image_base64:
            if len(image_base64)>14000000 or not base64.b64decode(image_base64,validate=True).startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Use a PNG under 10 MB')
        try:
            exported=self.studio('POST',f'sessions/{session_id}/export')
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404 and 'session not found or expired' in error.response.text:
                raise ValueError('EDITOR_SESSION_EXPIRED: Restore a saved draft to continue. Existing saved drafts are unchanged.') from error
            raise
        from datetime import datetime, timezone
        record={'draft_id':session_id,'revision':exported['revision'],'cif':exported['cif'],'note':note,'image_base64':image_base64,'settings':settings,'saved_at':datetime.now(timezone.utc).isoformat()}
        selection = self.managed.selection(session_id)
        record['previous_machine_id'] = selection['machine_id'] or selection['previous_machine_id']
        directory=self.root/'drafts'; directory.mkdir(exist_ok=True,mode=0o700)
        path=directory/(session_id+'.json')
        serialized=json.dumps(record)
        temp=directory/(uuid.uuid4().hex+'.tmp');temp.write_text(serialized);temp.chmod(0o600);temp.replace(path)
        return dict({k:record[k] for k in ('draft_id','revision','saved_at')}, snapshot_checksum=hashlib.sha256(serialized.encode()).hexdigest())

    def list_drafts(self):
        return {'drafts':[{k:v[k] for k in ('draft_id','revision','saved_at','note')} for p in sorted((self.root/'drafts').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True) for v in [json.loads(p.read_text())]]}

    def restore_draft(self, draft_id, expected_checksum=None):
        serialized=(self.root/'drafts'/(safe_session(draft_id)+'.json')).read_bytes()
        if expected_checksum is not None and hashlib.sha256(serialized).hexdigest()!=expected_checksum:
            raise ValueError('The saved draft changed; save and review the document again')
        record=json.loads(serialized)
        result=self.import_cif(record['cif'])
        # Restoring scientific work never reconnects compute, including legacy drafts.
        previous = record.get('previous_machine_id')
        if previous:
            state = self.managed
            with state.transaction() as data:
                if previous in data['machines']:
                    selection = state._selection(data, result['session_id'])
                    data['sessions'][result['session_id']] = dict(selection, previous_machine_id=previous)
        return {'session_id':result['session_id'],'note':record['note'],'image_base64':record.get('image_base64'),'settings':record.get('settings')}

    def overview(self):
        jobs = [json.loads(p.read_text()) for p in self.state.glob('*/job.json')]
        return {'plans':[self.public_plan(p) for p in self.plans()], 'jobs':[self.public_job(j) for j in jobs]}

    def public_job(self, job):
        """Expose run identity/status, not the frozen executable source bundle."""
        result={k:v for k,v in job.items() if k not in ('target','execution_payload','published_payload')}
        for field in ('error','detail'):
            value=result.get(field)
            if value is not None and (not isinstance(value,str) or len(value)>1000
                    or ('Command ' in value and ' timed out' in value)):
                result[field]='An earlier command failed or timed out. Ask chat to inspect the original operation; do not resubmit an uncertain run.'
        result['machine_name']=job.get('instance') or 'Original machine'
        if job.get('status')=='queued':
            if job.get('execution_payload') and job.get('remote_dispatch_started') is False and job.get('plan_checksum'):
                result['detail']='Waiting for the original worker. If this run stays queued, ask chat to continue this saved run; do not submit another design.'
                result['recovery_action']='recover_queued_rfd4_job'
            else:
                result['detail']='This older run has no durable dispatch proof. Inspect its original executor in chat; do not replay it.'
        return result

    def viewer_payload(self, result):
        session_id = safe_session(result['session_id'])
        exported = self.studio('POST', f'sessions/{session_id}/export')
        structure = result.get('structure')
        if structure is None or structure['revision'] != exported['revision']:
            structure = self.studio('GET', f'sessions/{session_id}')['structure']
        if structure['revision'] != exported['revision']:
            raise ValueError('The structure changed while loading; reload it before selecting atoms')
        return {k: v for k, v in dict(result, cif=exported['cif'], structure=structure).items()
                if k not in ('editor_path', 'editor_url')}

    def resolve_selection(self, session_id, atom_indices, scope='residue'):
        safe_session(session_id)
        self.validate_indices(atom_indices)
        if scope not in ('atom', 'residue', 'chain'):
            raise ValueError('Choose atom, residue, or chain')
        return self.studio('POST', f'sessions/{session_id}/selections/resolve',
                           json={'atom_indices':atom_indices, 'scope':scope})

    @staticmethod
    def validate_indices(atom_indices):
        if not atom_indices or len(atom_indices) > 100000 or any(type(i) is not int or i < 0 for i in atom_indices):
            raise ValueError('Select valid nonnegative atom indices')

    def set_condition(self, session_id, atom_indices, condition, enabled, expected_revision):
        safe_session(session_id)
        self.validate_indices(atom_indices)
        if condition not in ('hotspot', 'sequence', 'coordinate'):
            raise ValueError('Unsupported condition for this preview')
        if type(expected_revision) is not int or expected_revision < 0 or type(enabled) is not bool:
            raise ValueError('Supply the current revision and an enabled boolean')
        return self.studio('POST', f'sessions/{session_id}/conditions', json={
            'atom_indices':atom_indices, 'condition':condition, 'enabled':enabled,
            'expected_revision':expected_revision, 'scope':'atom'})

    def result_files(self, job_id):
        job = self.read(job_id, 'job.json')
        if job['status'] != 'completed':
            raise ValueError('Complete the job before retrieving results')
        from pathlib import Path
        return [Path(p) for p in self.collect(job_id)['files']]

    def results(self, job_id):
        files = self.result_files(job_id)
        return {'job_id': job_id, 'designs': [{'index': i, 'name': p.name} for i,p in enumerate(files)]}

    def open_run_structure(self, job_id, index=None):
        job = self.read(job_id, 'job.json')
        metadata = self.saved_run_metadata(job)
        if index is None:
            snapshot = self.state / safe_id(job['snapshot_id']) / 'input.cif'
            return dict(self.viewer_payload(self.import_cif(snapshot.read_text())), document_metadata=metadata)
        self.result_files(job_id)
        return dict(self.viewer_payload(self.open_result(job_id, index)), document_metadata=metadata)

    def saved_run_metadata(self, job):
        """Restore provenance from the accepted input, never the currently open draft."""
        snapshot_id = safe_id(job.get('snapshot_id', job['job_id']))
        directory = self.state / snapshot_id
        path = directory / 'plan.json'
        if not path.exists():
            return {'source':'unavailable', 'note':'', 'image_base64':None, 'settings':None}
        plan = json.loads(path.read_text())
        if (plan.get('snapshot_id') != snapshot_id
                or self.checksum(plan) != plan.get('plan_checksum')
                or hashlib.sha256((directory/'input.cif').read_bytes()).hexdigest() != plan.get('sha256')):
            raise ValueError('Saved run plan or input changed; preserve the run and reconcile its provenance before opening')
        generation = options(plan.get('generation'))
        if (type(plan.get('samples')) is not int or not 1 <= plan['samples'] <= 16
                or type(plan.get('seed')) is not int or not 0 <= plan['seed'] < 2**31
                or job.get('snapshot_id') != snapshot_id
                or any(job.get(key) != plan.get(key) for key in ('samples','seed','target'))
                or options(job.get('generation')) != generation):
            raise ValueError('Saved settings do not match the accepted run; reconcile its provenance before opening')
        note = plan.get('note','')
        if not isinstance(note,str) or len(note)>20000:raise ValueError('Invalid saved run note')
        image = None
        image_path = directory/'annotation.png'
        image_unavailable = image_path.exists() and not plan.get('image_sha256')
        if plan.get('image_sha256'):
            import base64
            raw = image_path.read_bytes()
            if (len(raw)>10_500_000 or not raw.startswith(b'\x89PNG\r\n\x1a\n')
                    or hashlib.sha256(raw).hexdigest()!=plan['image_sha256']):
                raise ValueError('Saved run image note changed; reconcile its provenance before opening')
            image = base64.b64encode(raw).decode()
        return {'source':'saved_run','note':note,'image_base64':image,
                'image_note_unavailable':image_unavailable,
                'settings':{'samples':plan['samples'],'seed':plan['seed'],'generation':generation}}

    def download_results(self, job_id):
        import base64
        import io
        import zipfile
        files = self.result_files(job_id)
        if not files or sum(p.stat().st_size for p in files) > 20_000_000:
            raise ValueError('Result archive unavailable or too large for inline transfer')
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i,p in enumerate(files):
                archive.write(p, f'design-{i+1}/{p.name}')
            archive.write(self.state / safe_id(job_id) / 'input.cif', 'input.cif')
        return {'filename': f'rfd4-{safe_id(job_id)}.zip', 'mime_type': 'application/zip',
                'base64': base64.b64encode(data.getvalue()).decode()}
