"""One controller worker per run; persisted dispatch uncertainty is never retried."""
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from core import Backend,safe_id


def run_worker(root, job_id, *, accepted_plan_checksum=None):
    backend=Backend(Path(root));job_id=safe_id(job_id)
    directory=backend.state/job_id
    with (directory/'worker-dispatch.lock').open('a') as lease:
        try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'job_id':job_id,'worker':'already_running'}
        # Reread only after acquiring the process lease. A stale process argument
        # or saved queued object never authorizes staging another worker's job.
        job=backend.read(job_id,'job.json')
        if accepted_plan_checksum is not None and job.get('plan_checksum')!=accepted_plan_checksum:
            raise ValueError('Recovery checksum does not match the accepted run')
        if job.get('status')!='queued':return job
        if job.get('remote_dispatch_started') is True:
            job.update(status='submission_unknown',error='Prior dispatch evidence requires remote reconciliation; no worker was repeated')
            backend.save_job(job);return job
        if not job.get('execution_payload') or job.get('remote_dispatch_started') is not False:
            job.update(status='submission_unknown',error='Legacy queued run has no durable immutable-payload dispatch proof. Preserve and inspect its original outcome; it cannot be replayed.')
            job.pop('dispatch_not_started',None)
            backend.save_job(job);return job
        try:
            machine=job.get('machine_id')
            reservation=backend.managed.snapshot()['reservations'].get(machine,{})
            if (not machine or job.get('target',{}).get('target_id')!=machine
                    or reservation.get('owner_id')!=job_id or reservation.get('purpose')!='run'):
                raise ValueError('Accepted run reservation is missing or belongs to other work; no reservation was recreated')
            source=backend.state/safe_id(job['snapshot_id'])/'input.cif'
            plan=backend.read(job['snapshot_id'],'plan.json')
            digest=hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k!='plan_checksum'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if not job.get('plan_checksum') or digest!=plan.get('plan_checksum') or digest!=job['plan_checksum']:
                raise ValueError('Saved reviewed plan changed before submission')
            if any(job.get(k)!=plan.get(k) for k in ('snapshot_id','samples','seed','generation','target','executor_ownership','execution_payload')):
                raise ValueError('Accepted job no longer matches the reviewed plan')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=plan['sha256']:
                raise ValueError('Saved input changed before submission')
            from run_payload import verified
            verified(source.parent,plan['execution_payload'])
        except Exception as error:
            backend.fail_undispatched(job,str(error))
            return backend.status(job_id)
        # A killed controller may leave an SSH child running. Only the durable
        # pre-launch submitting marker governs uncertainty; a free local lease
        # alone never proves that a remote child stopped.
        return backend._submit(job['target'],job,source)


if __name__=='__main__':
    run_worker(Path(sys.argv[1]),sys.argv[2])
