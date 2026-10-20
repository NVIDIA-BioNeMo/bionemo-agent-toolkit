"""Publish reviewed package ownership in an existing protected root directory.

This is not authorization: the setup controller must validate the explicit
reviewed action and hold its machine reservation before invoking this helper.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
from toolchain_paths import protected_directory, transaction_directory, read_record, write_record
from remote_job import pending_machine_package


def publish(base, job_id, transaction, expected_checksum):
    if os.geteuid()!=0:raise ValueError('Package ownership publication requires authorized sudo')
    digest=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=expected_checksum:raise ValueError('Reviewed prerequisite transaction checksum changed')
    base=Path(base)
    with protected_directory(base) as parent:
        descriptor=os.open('ownership.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=parent)
        with os.fdopen(descriptor,'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:previous_owner=read_record(parent,'package-owner.json')
            except FileNotFoundError:previous_owner=None
            pending=pending_machine_package(base)
            if pending:
                if pending['job_id']==job_id and pending['transaction_sha256']==digest:
                    return {'job_id':job_id,'transaction_sha256':digest,'directory':pending['directory'],'reused':True}
                raise ValueError('A prior privileged package transaction must be reconciled first')
            with transaction_directory(parent,job_id) as directory:
                record={'protocol':1,'job_id':job_id,'transaction':transaction,'transaction_sha256':digest}
                try:existing=read_record(directory,'package-intent.json')
                except FileNotFoundError:existing=None
                if existing is not None:
                    if previous_owner and previous_owner['job_id']!=job_id:
                        raise ValueError('A later package owner superseded this unpublished intent')
                    if existing!=record:raise ValueError('Package intent is immutable; use a newly reviewed operation')
                    # Recover the intent-to-owner persistence boundary only when
                    # no stage was dispatched and no later owner replaced it.
                    try:read_record(directory,'package-stage.json')
                    except FileNotFoundError:pass
                    else:raise ValueError('This operation already has a stage outcome; reconcile it')
                else:write_record(directory,'package-intent.json',record)
                owner={'job_id':job_id,'directory':str(base/job_id),'transaction_sha256':digest}
                write_record(parent,'package-owner.json',owner)
                return dict(owner,reused=existing is not None)
