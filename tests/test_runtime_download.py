import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from runtime_download import fetch

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):
        super().__init__(data);self.status=status;self.headers=headers or {}

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'weight.ckpt';self.data=b'correct checkpoint'
        self.spec={'size':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest()}

    def test_resume_verified_partial(self):
        self.path.with_name('weight.ckpt.part').write_bytes(self.data[:5])
        def opener(request,timeout):
            self.assertEqual(request.headers['Range'],'bytes=5-')
            return Response(self.data[5:],206,{'Content-Range':'bytes 5-17/18'})
        fetch('https://example/weight',self.path,self.spec,opener)
        self.assertEqual(self.path.read_bytes(),self.data)

    def test_server_ignoring_range_restarts_safely(self):
        self.path.with_name('weight.ckpt.part').write_bytes(b'wrong prefix')
        fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data))
        self.assertEqual(self.path.read_bytes(),self.data)

    def test_corrupt_download_never_published(self):
        with self.assertRaises(ValueError):fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(b'x'*len(self.data)))
        self.assertFalse(self.path.exists())

    def test_valid_existing_file_needs_no_request(self):
        self.path.write_bytes(self.data)
        def unexpected(*a,**kw):raise AssertionError('Must reuse verified checkpoint')
        self.assertEqual(fetch('https://example/weight',self.path,self.spec,unexpected),self.path)

    def test_incorrect_range_is_rejected(self):
        self.path.with_name('weight.ckpt.part').write_bytes(self.data[:5])
        with self.assertRaises(ValueError):fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data[5:],206,{'Content-Range':'bytes 0-12/18'}))
        self.assertFalse(self.path.exists())

    def test_interrupted_download_resumes_to_verified_file(self):
        class Interrupted(Response):
            def read(self,size):
                if self.tell():raise ConnectionError('connection lost')
                return super().read(5)
        with self.assertRaises(ConnectionError):
            fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Interrupted(self.data))
        self.assertFalse(self.path.exists())
        self.assertEqual(self.path.with_name('weight.ckpt.part').read_bytes(),self.data[:5])
        fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data[5:],206,{'Content-Range':'bytes 5-17/18'}))
        self.assertEqual(self.path.read_bytes(),self.data)

    def test_corruption_can_recover_on_next_attempt(self):
        with self.assertRaises(ValueError):
            fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(b'x'*18))
        fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data))
        self.assertEqual(self.path.read_bytes(),self.data)
        self.assertEqual(len(list(self.path.parent.glob('*.invalid-*'))),1)

    def test_incorrect_total_is_rejected_before_append(self):
        partial=self.path.with_name('weight.ckpt.part');partial.write_bytes(self.data[:5])
        with self.assertRaises(ValueError):
            fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data[5:],206,{'Content-Range':'bytes 5-17/19'}))
        self.assertEqual(partial.read_bytes(),self.data[:5])

    def test_unsolicited_partial_response_is_validated(self):
        with self.assertRaises(ValueError):
            fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data,206,{'Content-Range':'bytes 1-18/19'}))
        self.assertFalse(self.path.exists())

    def test_disk_full_partial_write_recovers_without_publication(self):
        import errno
        from unittest.mock import patch
        original_open=Path.open
        partial=self.path.with_name('weight.ckpt.part')
        class FullDisk:
            def __init__(self, handle): self.handle=handle
            def __enter__(self): return self
            def __exit__(self, *args): return self.handle.__exit__(*args)
            def write(self, data):
                self.handle.write(data[:5]);self.handle.flush()
                raise OSError(errno.ENOSPC, 'No space left on device')
        def open_with_full_disk(path, mode='r', *args, **kwargs):
            handle=original_open(path,mode,*args,**kwargs)
            return FullDisk(handle) if path==partial and mode=='wb' else handle
        with patch.object(Path,'open',open_with_full_disk):
            with self.assertRaises(OSError) as caught:
                fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data))
        self.assertEqual(caught.exception.errno,errno.ENOSPC)
        self.assertFalse(self.path.exists())
        self.assertEqual(partial.read_bytes(),self.data[:5])
        def resumed(request,timeout):
            self.assertEqual(request.headers['Range'],'bytes=5-')
            return Response(self.data[5:],206,{'Content-Range':'bytes 5-17/18'})
        fetch('https://example/weight',self.path,self.spec,resumed)
        self.assertEqual(self.path.read_bytes(),self.data)
        self.assertFalse(partial.exists())

    def test_failed_fsync_never_publishes_and_can_recover(self):
        import errno
        from unittest.mock import patch
        with patch('runtime_download.os.fsync',side_effect=OSError(errno.EIO,'I/O error')):
            with self.assertRaises(OSError):
                fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data))
        self.assertFalse(self.path.exists())
        partial=self.path.with_name('weight.ckpt.part')
        self.assertEqual(partial.read_bytes(),self.data)
        def no_network(*args,**kwargs): raise AssertionError('Valid completed partial should be reused')
        import os
        real_fsync=os.fsync
        publications=[]
        def synced(fd):
            publications.append(self.path.exists())
            return real_fsync(fd)
        with patch('runtime_download.os.fsync',side_effect=synced):
            fetch('https://example/weight',self.path,self.spec,no_network)
        self.assertEqual(publications,[False,True])
        self.assertEqual(self.path.read_bytes(),self.data)

    def test_directory_sync_failure_is_retried_for_valid_destination(self):
        import errno,os
        from unittest.mock import patch
        real_fsync=os.fsync
        calls=[]
        def fail_directory(fd):
            calls.append(self.path.exists())
            if self.path.exists():raise OSError(errno.EIO,'Directory sync failed')
            return real_fsync(fd)
        with patch('runtime_download.os.fsync',side_effect=fail_directory):
            with self.assertRaises(OSError):
                fetch('https://example/weight',self.path,self.spec,lambda *a,**kw:Response(self.data))
        self.assertEqual(calls,[False,True])
        self.assertEqual(self.path.read_bytes(),self.data)
        def no_network(*args,**kwargs):raise AssertionError('Verified bytes must be reused')
        with patch('runtime_download.os.fsync',side_effect=OSError(errno.EIO,'Still failing')):
            with self.assertRaises(OSError):fetch('https://example/weight',self.path,self.spec,no_network)
        with patch('runtime_download.os.fsync',wraps=real_fsync) as synced:
            fetch('https://example/weight',self.path,self.spec,no_network)
        self.assertEqual(synced.call_count,2)
        self.assertEqual(self.path.read_bytes(),self.data)
