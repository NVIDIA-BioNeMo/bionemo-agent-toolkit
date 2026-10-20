"""Checksum-bound planning and process-safe submission around the Studio adapter."""
import hashlib
import json
import fcntl
import uuid
from generation import options
from core import Backend, safe_id, safe_session

from lifecycle import Lifecycle
from setup_operation import SetupOperation
from create_operation import CreateOperation

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
        ownership=self.require_executor_ownership(target)
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
                ownership=self.require_executor_ownership(plan['target'],plan['executor_ownership'])
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
        exported=self.studio('POST',f'sessions/{session_id}/export')
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
