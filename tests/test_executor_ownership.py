"""Machine-wide owner races and refusal boundaries, without privileged writes."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import executor_ownership as owner


def value(executor='a', root='b'):
    return {'protocol': 1, 'executor_id': executor*32, 'controller_root_sha256': root*64,
            'linux_machine_id_sha256': 'c'*64, 'brev': {'organization_id':'org','instance_id':'instance'}}


def racing_claim(path, record, barrier, queue):
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        barrier.wait(timeout=10)
        try:queue.put({'result':owner._claim_directory(descriptor,record,allow_initial=True,owner_uid=os.getuid())})
        except Exception as error:queue.put({'error':str(error)})
    finally:os.close(descriptor)


class ExecutorOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.fd)

    def claim(self, expected=None, allow_initial=True):
        return owner._claim_directory(self.fd,expected or value(),allow_initial=allow_initial,owner_uid=os.getuid())

    def test_two_independent_claim_processes_publish_exactly_one_owner(self):
        context=multiprocessing.get_context('fork');barrier=context.Barrier(2);queue=context.Queue()
        processes=[context.Process(target=racing_claim,args=(str(self.path),value(executor),barrier,queue)) for executor in ('a','d')]
        for process in processes:process.start()
        try:
            results=[queue.get(timeout=15) for _ in processes]
            for process in processes:process.join(timeout=10);self.assertEqual(process.exitcode,0)
        finally:
            for process in processes:
                if process.is_alive():process.terminate();process.join(timeout=5)
            queue.close();queue.join_thread()
        winners=[row['result'] for row in results if 'result' in row]
        self.assertEqual(len(winners),1,results)
        self.assertFalse(winners[0]['reused'])
        saved=json.loads((self.path/owner.RECORD).read_text())
        self.assertEqual(saved,winners[0]['owner'])
        self.assertEqual(sorted(p.name for p in self.path.iterdir()),sorted([owner.RECORD,owner.COMMITTED,'executor-owner.lock']))
        loser=value('d' if saved['executor_id']=='a'*32 else 'a')
        before=(self.path/owner.RECORD).read_bytes()
        with self.assertRaisesRegex(ValueError,'different executor'):self.claim(loser)
        self.assertEqual((self.path/owner.RECORD).read_bytes(),before)

    def test_exact_retry_is_idempotent_without_rewriting_receipt(self):
        first=self.claim();before=(self.path/owner.RECORD).stat()
        self.assertFalse(first['reused']);self.assertTrue(self.claim()['reused'])
        after=(self.path/owner.RECORD).stat()
        self.assertEqual((before.st_ino,before.st_mtime_ns),(after.st_ino,after.st_mtime_ns))

    def test_copied_executor_id_with_other_root_refuses(self):
        self.claim()
        with self.assertRaisesRegex(ValueError,'different executor'):self.claim(value(root='e'))

    def test_different_provider_or_physical_identity_refuses(self):
        self.claim()
        for key,new in [('linux_machine_id_sha256','f'*64),('brev',{'organization_id':'org','instance_id':'replacement'})]:
            changed=value();changed[key]=new
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'different executor'):self.claim(changed)

    def test_missing_previous_ownership_never_reclaims(self):
        with self.assertRaisesRegex(ValueError,'missing'):self.claim(allow_initial=False)
        self.assertFalse((self.path/owner.RECORD).exists())

    def test_corrupt_receipt_never_overwrites(self):
        path=self.path/owner.RECORD;path.write_text('{corrupt');before=path.read_bytes()
        with self.assertRaises(json.JSONDecodeError):self.claim()
        self.assertEqual(path.read_bytes(),before)

    def test_record_and_lock_symlinks_cannot_escape(self):
        for name in (owner.RECORD,'executor-owner.lock'):
            with self.subTest(name=name):
                target=self.path/'unrelated';target.write_text('preserve')
                link=self.path/name;link.unlink(missing_ok=True);link.symlink_to(target)
                try:
                    with self.assertRaises(OSError):self.claim()
                    self.assertEqual(target.read_text(),'preserve')
                finally:link.unlink()

    def test_writable_record_and_lock_refuse(self):
        self.claim()
        for name in (owner.RECORD,'executor-owner.lock'):
            with self.subTest(name=name):
                p=self.path/name;p.chmod(0o666)
                try:
                    with self.assertRaisesRegex(ValueError,'protected'):self.claim()
                finally:p.chmod(0o644)

    def test_schema_validation_is_strict(self):
        for changed in ({'protocol':True},{'protocol':2},{'executor_id':'not-an-id'},{'brev':{'instance_id':'id'}},{'controller_root_sha256':'x'*64}):
            bad=value()|changed
            with self.subTest(changed=changed),self.assertRaises(ValueError):owner.validate(bad)
        self.assertEqual(owner.validate(value()),value())

    def test_public_claim_requires_admin_and_exact_review_before_filesystem(self):
        with patch.object(owner.os,'geteuid',return_value=1000),patch.object(owner,'protected_directory') as directories:
            with self.assertRaisesRegex(ValueError,'administrator'):owner.claim(value(),'wrong')
            directories.assert_not_called()
        with patch.object(owner.os,'geteuid',return_value=0),patch.object(owner,'protected_directory') as directories:
            with self.assertRaisesRegex(ValueError,'review changed'):owner.claim(value(),'wrong',allow_initial=True)
            directories.assert_not_called()

    def test_public_claim_refuses_identity_drift_before_filesystem(self):
        record=value();digest=owner.checksum({'action':'claim_executor','owner':record,'allow_initial':True})
        with patch.object(owner.os,'geteuid',return_value=0),patch.object(owner,'physical_identity',return_value='d'*64),patch.object(owner,'protected_directory') as directories:
            with self.assertRaisesRegex(ValueError,'identity changed'):owner.claim(record,digest,allow_initial=True)
            directories.assert_not_called()

    def test_inspection_of_absent_binding_performs_no_writes(self):
        with patch.object(owner,'physical_identity',return_value='c'*64),patch.object(owner,'protected_directory',side_effect=FileNotFoundError),patch.object(owner.os,'mkdir') as mkdir,patch.object(owner,'write_record') as write:
            self.assertEqual(owner.inspect(value())['state'],'unclaimed')
            mkdir.assert_not_called();write.assert_not_called()

    def test_readable_receipt_is_not_writable_by_group_or_other(self):
        self.claim();self.assertEqual((self.path/owner.RECORD).stat().st_mode & 0o777,0o644)
        self.assertEqual(owner._read(self.fd,owner_uid=os.getuid()),value())

    def test_missing_committed_receipt_cannot_be_recreated_by_new_initial_claim(self):
        self.claim();(self.path/owner.RECORD).unlink()
        with self.assertRaisesRegex(ValueError,'committed ownership receipt is missing'):self.claim()
        self.assertFalse((self.path/owner.RECORD).exists())

    def test_changed_commit_marker_cannot_be_overwritten(self):
        self.claim();path=self.path/owner.COMMITTED
        path.write_text(json.dumps({'protocol':999,'owner_checksum':'e'*64}));before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'commit marker changed'):self.claim()
        self.assertEqual(path.read_bytes(),before)

    def inspect_fixture(self):
        @contextmanager
        def protected(path):
            yield self.fd
        read=owner.read_record
        def ordinary_read(directory,name,**kwargs):return read(directory,name,owner_uid=os.getuid())
        with patch.object(owner,'physical_identity',return_value='c'*64),patch.object(owner,'protected_directory',side_effect=protected),patch.object(owner,'read_record',side_effect=ordinary_read):
            return owner.inspect(value())

    def test_ordinary_inspection_requires_durable_publication_marker(self):
        self.claim();before=(self.path/owner.RECORD).stat()
        self.assertEqual(self.inspect_fixture()['state'],'owned')
        (self.path/owner.COMMITTED).unlink()
        self.assertEqual(self.inspect_fixture()['state'],'pending')
        after=(self.path/owner.RECORD).stat()
        self.assertEqual((before.st_ino,before.st_mtime_ns),(after.st_ino,after.st_mtime_ns))
        self.assertFalse((self.path/owner.COMMITTED).exists())

    def test_ordinary_inspection_refuses_orphan_or_changed_marker(self):
        self.claim();path=self.path/owner.COMMITTED
        saved=path.read_bytes();path.write_text(json.dumps({'protocol':999}))
        with self.assertRaisesRegex(ValueError,'commit marker changed'):self.inspect_fixture()
        path.write_bytes(saved);(self.path/owner.RECORD).unlink()
        with self.assertRaisesRegex(ValueError,'committed ownership receipt is missing'):self.inspect_fixture()

    def test_restrictive_admin_umask_still_allows_ordinary_reads(self):
        previous=os.umask(0o077)
        try:self.claim()
        finally:os.umask(previous)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o755)
        self.assertEqual((self.path/owner.RECORD).stat().st_mode & 0o777,0o644)

    def test_fifo_receipt_refuses_without_blocking(self):
        os.mkfifo(self.path/owner.RECORD,0o600)
        with self.assertRaisesRegex(ValueError,'not protected'):self.claim()
        self.assertTrue((self.path/owner.RECORD).is_fifo())

    def test_retry_finishes_durability_after_rename_sync_failure(self):
        real_sync=os.fsync;calls=[]
        def interrupted(descriptor):
            calls.append(descriptor)
            if len(calls)==2:raise OSError('Injected directory fsync failure after rename')
            return real_sync(descriptor)
        with patch.object(owner.os,'fsync',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'after rename'):self.claim()
        self.assertTrue((self.path/owner.RECORD).exists())
        with patch.object(owner.os,'fsync',wraps=real_sync) as synced:
            self.assertTrue(self.claim()['reused'])
            self.assertGreaterEqual(synced.call_count,2)
        self.assertEqual(json.loads((self.path/owner.RECORD).read_text()),value())

    def test_retry_syncs_parent_after_mkdir_acknowledgment_failure(self):
        @contextmanager
        def protected(path):
            location=self.path if path==owner.BASE.parent else self.path/owner.BASE.name
            descriptor=os.open(location,os.O_RDONLY|os.O_DIRECTORY)
            try:yield descriptor
            finally:os.close(descriptor)
        record=value();digest=owner.checksum({'action':'claim_executor','owner':record,'allow_initial':True})
        real_sync=os.fsync;real_claim=owner._claim_directory
        def claim_in_fixture(directory,expected,*,allow_initial):
            return real_claim(directory,expected,allow_initial=allow_initial,owner_uid=os.getuid())
        with patch.object(owner.os,'geteuid',return_value=0),patch.object(owner,'physical_identity',return_value='c'*64),patch.object(owner,'protected_directory',side_effect=protected),patch.object(owner,'_claim_directory',side_effect=claim_in_fixture):
            with patch.object(owner.os,'fsync',side_effect=OSError('Injected mkdir parent sync failure')):
                with self.assertRaisesRegex(OSError,'mkdir parent'):owner.claim(record,digest,allow_initial=True)
            self.assertTrue((self.path/owner.BASE.name).is_dir())
            self.assertFalse((self.path/owner.BASE.name/owner.RECORD).exists())
            synchronized=[]
            def synchronize(descriptor):
                synchronized.append(os.fstat(descriptor).st_ino);return real_sync(descriptor)
            with patch.object(owner.os,'fsync',side_effect=synchronize):
                self.assertFalse(owner.claim(record,digest,allow_initial=True)['reused'])
            self.assertIn(self.path.stat().st_ino,synchronized)

if __name__=='__main__':unittest.main()
