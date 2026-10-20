"""Representative upstream short-monomer inference and structure validation."""
import json
import os
from pathlib import Path
import tempfile

VALIDATE = r'''import hashlib,json,sys
from pathlib import Path
import numpy as np
from biotite.structure.io.pdbx import CIFFile,get_structure
root=Path(sys.argv[1]).resolve(); evidence=[]
for path in sorted(root.rglob('*.cif')):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Smoke output escapes its run directory')
    atoms=get_structure(CIFFile.read(path),model=1)
    if len(atoms)==0 or not np.isfinite(atoms.coord).all():
        raise ValueError('Smoke output lacks finite atomic coordinates')
    evidence.append({'path':str(path.relative_to(root)),'atoms':len(atoms),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
if not evidence:raise ValueError('Smoke inference produced no CIF structures')
print(json.dumps({'structures':evidence}))
'''


def smoke(root, run, lock_fd):
    root=Path(root);model=root/'model'
    parent=root/'setup-smoke';parent.mkdir(exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='monomer-short-',dir=parent))
    args=[str(model/'.venv/bin/rfd4-generate'),'inputs=data/benchmarks/monomer',
          'subset_to_examples=monomer-short','num_replicates=1','batch_size=1',
          'seed=42','compile_lengths=null','out_dir='+str(output),'hydra.run.dir='+str(output/'hydra')]
    run(args,cwd=model,check=True,pass_fds=(lock_fd,),env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',DATA_PATH=str(model/'data_path')))
    result=json.loads(run([str(model/'.venv/bin/python'),'-B','-c',VALIDATE,str(output)],check=True,capture_output=True,text=True).stdout)
    if not isinstance(result.get('structures'),list) or not result['structures']:
        raise ValueError('Smoke inference returned no validated structures')
    return {'example':'monomer-short','output_dir':str(output),'command':args,**result}
