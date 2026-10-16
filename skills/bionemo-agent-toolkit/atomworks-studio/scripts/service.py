"""Checksum-bound planning and process-safe submission around the Studio adapter."""
import hashlib
import json
import fcntl
import uuid
from generation import options
from core import Backend, safe_id, safe_session

class Service(Backend):
    def plans(self):
        return [json.loads(p.read_text()) for p in sorted(self.state.glob('*/plan.json'), key=lambda p:p.stat().st_mtime, reverse=True)]

    def prepare(self, session_id, note='', samples=1, seed=42, image_base64=None, generation=None):
        if type(samples) is not int or not 1 <= samples <= 16 or type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError('Use 1–16 designs and a nonnegative 31-bit seed')
        generation = options(generation)
        snapshot = self.snapshot(session_id, note, {'image_base64': image_base64} if image_base64 else None)
        plan = dict(snapshot, session_id=session_id, samples=samples, seed=seed, generation=generation, target=self.config(session_id))
        plan['plan_checksum'] = self.checksum(plan)
        (self.state / plan['snapshot_id'] / 'plan.json').write_text(json.dumps(plan, indent=2))
        return self.public_plan(plan)

    @staticmethod
    def checksum(plan):
        return hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k != 'plan_checksum'},sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @staticmethod
    def public_plan(plan):
        return {k:v for k,v in plan.items() if k not in ('target', 'image_markup')} | {'instance':plan['target']['instance'], 'instance_id':plan['target'].get('instance_id', '')}

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
            if plan['target'] != self.config(plan.get('session_id')):
                raise ValueError('Compute configuration changed; prepare and review again')
            status = self.check_compute(plan.get('session_id'))
            if status['state'] != 'ready':
                raise ValueError('Compute is not ready: '+status['detail'])
            return self.launch(plan_id, plan['samples'], plan['seed'], request_id=plan_id, target=plan['target'], generation=plan.get('generation'))

    def save_draft(self, session_id, note='', image_base64=None, settings=None):
        """Save even incomplete designs; validation is required only for review."""
        safe_session(session_id)
        if len(note)>20000 or len(json.dumps(settings))>10000: raise ValueError('Draft notes are too large')
        import base64
        if image_base64:
            if len(image_base64)>14000000 or not base64.b64decode(image_base64,validate=True).startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Use a PNG under 10 MB')
        exported=self.studio('POST',f'sessions/{session_id}/export')
        from datetime import datetime, timezone
        record={'draft_id':session_id,'revision':exported['revision'],'cif':exported['cif'],'note':note,'image_base64':image_base64,'settings':settings,'saved_at':datetime.now(timezone.utc).isoformat()}
        try: record['target']=self.config(session_id)
        except ValueError: pass
        directory=self.root/'drafts'; directory.mkdir(exist_ok=True,mode=0o700)
        path=directory/(session_id+'.json')
        temp=directory/(uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(record));temp.chmod(0o600);temp.replace(path)
        return {k:record[k] for k in ('draft_id','revision','saved_at')}

    def list_drafts(self):
        return {'drafts':[{k:v[k] for k in ('draft_id','revision','saved_at','note')} for p in sorted((self.root/'drafts').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True) for v in [json.loads(p.read_text())]]}

    def restore_draft(self, draft_id):
        record=json.loads((self.root/'drafts'/(safe_session(draft_id)+'.json')).read_text())
        result=self.import_cif(record['cif'])
        if record.get('target'):
            path=self.compute_config_path(result['session_id'])
            path.write_text(json.dumps(record['target']));path.chmod(0o600)
        return {'session_id':result['session_id'],'note':record['note'],'image_base64':record.get('image_base64'),'settings':record.get('settings')}

    def overview(self):
        jobs = [json.loads(p.read_text()) for p in self.state.glob('*/job.json')]
        return {'plans':[self.public_plan(p) for p in self.plans()], 'jobs':[{k:v for k,v in j.items() if k != 'target'} for j in jobs]}

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
        directory = self.state / safe_id(job_id) / 'results'
        if not list(directory.rglob('*.cif*')):
            self.collect(job_id)
        return sorted(directory.rglob('*.cif*'))

    def results(self, job_id):
        files = self.result_files(job_id)
        return {'job_id': job_id, 'designs': [{'index': i, 'name': p.name} for i,p in enumerate(files)]}

    def open_run_structure(self, job_id, index=None):
        job = self.read(job_id, 'job.json')
        if index is None:
            snapshot = self.state / safe_id(job['snapshot_id']) / 'input.cif'
            return self.viewer_payload(self.import_cif(snapshot.read_text()))
        self.result_files(job_id)
        return self.viewer_payload(self.open_result(job_id, index))

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
