"""Execute the real isolated bootstrap/shell guard against controlled readers.

The controlled readers test launch refusal/ordering, not real root permissions;
executor_ownership's protected filesystem behavior has separate tests.
"""
import os,shlex,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import ownership_adapter as adapter

class OwnershipRuntimeGuardTests(unittest.TestCase):
    def test_runtime_never_starts_without_committed_owner(self):
        for state in ('unclaimed','pending','owned','foreign'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'toolchain_paths.py').write_text('# Controlled reader dependency\n')
                source=("def inspect(expected):\n    raise ValueError('foreign executor')\n" if state=='foreign' else "def inspect(expected):\n    return {'state':"+repr(state)+"}\n")
                (root/'executor_ownership.py').write_text(source)
                owner={'protocol':1,'executor_id':'a'*32,'controller_root_sha256':'b'*64,'linux_machine_id_sha256':'c'*64,'brev':None}
                marker=root/'model-started'
                model=shlex.join([sys.executable,'-c',"from pathlib import Path;Path("+repr(str(marker))+").write_text('one model invocation')"])
                script=root/'run.sh';script.write_text('#!/bin/bash\nset -e\n'+adapter.command('require',owner,scripts=root)+'\n'+model+'\n')
                result=subprocess.run(['bash',str(script)],capture_output=True,text=True,timeout=15,stdin=subprocess.DEVNULL)
                if state=='owned':self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(marker.exists())
                else:self.assertNotEqual(result.returncode,0);self.assertFalse(marker.exists())

if __name__=='__main__':unittest.main()
