"""Coordinate one reviewed prerequisite stage under the existing setup lease.

The privileged adapter owns publication, one-shot launch and external finalization.
This coordinator never retries a dispatch or treats transport failure as absence.
"""
import hashlib
import json
from pathlib import Path
import time
from toolchain_download import download_archives
from toolchain_review import review as package_review


def install_prerequisites(root, operation_id, reviewed, *, privileged, journal,
                          check_cancel, publication_started=lambda:None, record_terminal=lambda receipt:None, download=download_archives,
                          review=package_review, sleep=time.sleep):
    transaction=reviewed['prerequisites']
    profile=json.loads(Path(__file__).with_name('toolchain_profile.json').read_text())
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if transaction['profile_sha256']!=digest:
        raise ValueError('Prerequisite profile changed after setup review')
    fresh=dict(review(profile),helper_hashes=transaction['helper_hashes'])
    if fresh!=transaction:raise ValueError('Prerequisite state changed; obtain a new setup review')
    check_cancel()
    if not transaction['changes']:
        return {'state':'not_needed','profile_sha256':digest}
    # Production activation remains gated until the image/profile is qualified.
    if profile.get('status')!='qualified':
        raise ValueError('Privileged prerequisite profile has not completed qualification')
    journal('prerequisites_downloading')
    archives=download(profile,transaction,Path(root)/'setup-operations'/operation_id/'package-cache',check_cancel=check_cancel)
    check_cancel()
    if dict(review(profile),helper_hashes=transaction['helper_hashes'])!=transaction:
        raise ValueError('Prerequisite state changed during download; review again')
    # From this point, cancellation must reconcile published ownership first.
    publication_started()
    published=False
    try:
        privileged('publish',operation_id,transaction,profile,archives)
        published=True
        check_cancel()
    except BaseException:
        if published:
            record_terminal(privileged('fence',operation_id,transaction,profile,archives))
        raise
    journal('prerequisites_installing')
    # Lost acknowledgement escapes as needs-attention to the existing setup
    # journal. Never redispatch here, including on a timeout.
    privileged('launch',operation_id,transaction,profile,archives)
    pending_observations=0
    while True:
        journal('prerequisites_reconciling')
        receipt=privileged('observe',operation_id,transaction,profile,archives)
        if receipt.get('job_id')!=operation_id or receipt.get('transaction_sha256')!=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest():
            raise ValueError('Prerequisite observation identity changed')
        if receipt.get('state')=='succeeded':
            record_terminal(receipt)
            check_cancel()
            return receipt
        if receipt.get('state')=='failed':
            record_terminal(receipt)
            raise ValueError('Prerequisite installation failed; review its recorded outcome before continuing')
        if receipt.get('state') not in ('running','pending'):
            raise ValueError('Prerequisite outcome is uncertain; reconcile the original operation')
        pending_observations=pending_observations+1 if receipt.get('state')=='pending' else 0
        if pending_observations>=60:
            raise TimeoutError('Package worker receipt remains unconfirmed; reconcile the original operation without redispatch')
        # Cancellation during apt does not kill it or release machine ownership.
        # The outer setup checks cancellation after safe terminal reconciliation.
        sleep(2)
