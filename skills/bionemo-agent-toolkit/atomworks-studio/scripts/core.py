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

class Backend(Compute):
    def __init__(self, root=ROOT, runner=subprocess.run):
        self.root = Path(root)
        self.state = self.root / 'state'
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runner = runner
        self.lock = threading.Lock()

    def config(self, session_id=None):
        path = self.compute_config_path(session_id)
        if session_id is not None and not path.exists():
            # Capture a default once, using an OS lock across both MCP servers.
            import fcntl
            with (self.root/'selection.lock').open('a') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX)
                default = self.root/'config.json'
                if default.exists() and not path.exists():
                    temp=path.with_name(uuid.uuid4().hex+'.tmp')
                    temp.write_text(default.read_text());temp.chmod(0o600);temp.replace(path)
        if not path.exists():
            raise ValueError('No compute registered. Ask the agent to configure a local GPU, SSH host, or Brev machine.')
        cfg = json.loads(path.read_text())
        return self.validate_config(cfg)

    def run(self, args, timeout=60):
        result = self.runner(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
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
        if cfg.get('registry_target'):
            import registry
            registry.verify(cfg['registry_target'], require_registry=False)
        if cfg.get('kind','brev') == 'brev':
            rows=json.loads(self.brev(cfg, 'ls', '--json'))['workspaces']
            if not any(row['name']==cfg['instance'] and row['id']==cfg['instance_id'] for row in rows):
                raise ValueError('The configured instance is not in the active Brev organization; restore the original organization.')

    def preflight(self):
        return self.check_compute()

    def studio_url(self):
        # Editor service can be CPU-only and independent of any GPU target.
        url = os.environ.get('RFD4_EDITOR_URL')
        if not url:
            path=self.root/'editor.json'
            if path.exists(): url=json.loads(path.read_text())['studio_url']
        if not url: url=self.config()['studio_url']
        self.validate_config({'kind':'local','instance':'editor','remote_root':'/tmp','studio_url':url})
        return url

    def studio(self, method, path, **kwargs):
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
        (directory / 'snapshot.json').write_text(json.dumps(record, indent=2))
        return record

    def read(self, item_id, filename):
        return json.loads((self.state / safe_id(item_id) / filename).read_text())

    def launch(self, snapshot_id, samples=1, seed=42, request_id=None, target=None, generation=None):
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
            record = {'job_id': job_id, 'snapshot_id': snapshot_id, 'samples': samples, 'seed': seed, 'generation': generation, 'instance': cfg['instance'], 'status': 'queued', 'target': cfg}
            if (jobdir / 'job.json').exists():
                existing = self.read(job_id, 'job.json')
                if options(existing.get('generation')) != generation or any(existing[k] != record[k] for k in ('snapshot_id', 'samples', 'seed', 'instance', 'target')):
                    raise ValueError('Request ID already used with different parameters')
                return existing
            jobdir.mkdir(mode=0o700, exist_ok=True)
            self.save_job(record)
        import sys
        worker_log = (jobdir / 'worker.log').open('a')
        try:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker.py')), str(self.root), job_id], stdin=subprocess.DEVNULL, stdout=worker_log, stderr=worker_log, start_new_session=True)
        except Exception as error:
            record.update(status='failed', error=str(error))
            self.save_job(record)
            raise
        finally:
            worker_log.close()
        return record

    def save_job(self, job):
        target = self.state / job['job_id'] / 'job.json'
        temp = target.with_name(f'.job-{uuid.uuid4().hex}.tmp')
        temp.write_text(json.dumps(job, indent=2))
        temp.replace(target)

    def _submit(self, cfg, record, source):
        try:
            self.verify_target(cfg)
            root = cfg['remote_root']
            remote = f"{root}/runs/{record['job_id']}"
            record['remote_dir'] = remote
            self.target_exec(cfg, f'test -x {shlex.quote(root + "/model/.venv/bin/rfd4-generate")} && test "$(cat {root}/model-revision)" = {REVISION} && mkdir -p {shlex.quote(remote)}')
            self.target_copy(cfg, source, f"{remote}/input.cif", timeout=180)
            args = [root + '/model/.venv/bin/rfd4-generate', f'inputs={remote}/input.cif', f'out_dir={remote}/output',
                    f'num_replicates={record["samples"]}', f'seed={record["seed"]}', 'batch_size=1', 'compile_lengths=null', 'prevalidate_inputs=true'] + overrides(record.get('generation'))
            # The shell sees only fixed commands, validated paths, IDs and numeric options.
            script = f'#!/bin/bash\nset +e\n(cd {shlex.quote(root + "/model")} && {shlex.join(args)})\ncode=$?\nprintf "%s" "$code" > {shlex.quote(remote + "/exit_code")}\nexit "$code"\n'
            local_script = self.state / record['job_id'] / 'run.sh'
            local_script.write_text(script)
            self.target_copy(cfg, local_script, f"{remote}/run.sh", timeout=180)
            record['status'] = 'submitting'
            self.save_job(record)
            # Never automatically retry this launch if the network outcome is ambiguous.
            self.target_exec(cfg, f'nohup bash {remote}/run.sh > {remote}/run.log 2>&1 < /dev/null & echo $! > {remote}/pid')
            record['status'] = 'submitted'
        except Exception as error:
            record['status'] = 'submission_unknown' if record['status'] == 'submitting' else 'failed'
            record['error'] = str(error)
        self.save_job(record)

    def status(self, job_id):
        record = self.read(job_id, 'job.json')
        if record['status'] not in ('submitted', 'submitting', 'submission_unknown', 'running'):
            return record
        cfg = self.validate_config(record['target'])
        self.verify_target(cfg)
        if cfg['instance'] != record['instance']:
            raise ValueError('Restore the original instance in config before polling this job')
        remote = record['remote_dir']
        output = self.target_exec(cfg, f'if test -f {remote}/exit_code; then cat {remote}/exit_code; elif test -f {remote}/pid && kill -0 "$(cat {remote}/pid)" 2>/dev/null; then echo RUNNING; else echo UNKNOWN; fi')
        value = output.strip()
        if value == '0': record['status'] = 'completed'
        elif value.isdigit(): record.update(status='failed', exit_code=int(value))
        elif value == 'RUNNING': record['status'] = 'running'
        else: record['status'] = 'submission_unknown'
        self.save_job(record)
        return record

    def collect(self, job_id):
        record = self.status(job_id)
        if record['status'] != 'completed':
            raise ValueError('Job has not completed successfully')
        cfg = self.validate_config(record['target'])
        self.verify_target(cfg)
        destination = self.state / safe_id(job_id) / 'results'
        destination.mkdir(exist_ok=True)
        self.target_copy(cfg, f"{record['remote_dir']}/output/inference_samples", destination, download=True, timeout=300)
        return {'job_id': job_id, 'files': [str(p) for p in destination.rglob('*.cif*')]}

    def open_result(self, job_id, index=0):
        record = self.read(job_id, 'job.json')
        if record['status'] != 'completed':
            raise ValueError('Complete and retrieve this job first')
        files = sorted((self.state / safe_id(job_id) / 'results').rglob('*.cif*'))
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
