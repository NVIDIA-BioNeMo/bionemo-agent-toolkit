"""Stage one reviewed source revision without overwriting an existing checkout."""
import os
import ctypes
import sys
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from source_integrity import verify_source


def publish(source, destination, *, directory_fd=None):
    """Atomic no-replace rename; refuse platforms without an exclusive primitive."""
    libc=ctypes.CDLL(None,use_errno=True)
    if sys.platform=='linux' and hasattr(libc,'renameat2'):
        fn=libc.renameat2
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        fn.restype=ctypes.c_int
        parent=-100 if directory_fd is None else directory_fd
        result=fn(parent,os.fsencode(source),parent,os.fsencode(destination),1)
    elif sys.platform=='darwin' and directory_fd is not None and hasattr(libc,'renameatx_np'):
        fn=libc.renameatx_np
        fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        fn.restype=ctypes.c_int
        result=fn(directory_fd,os.fsencode(source),directory_fd,os.fsencode(destination),4)
    elif sys.platform=='darwin' and directory_fd is None and hasattr(libc,'renamex_np'):
        fn=libc.renamex_np
        fn.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
        fn.restype=ctypes.c_int
        result=fn(os.fsencode(source),os.fsencode(destination),4)
    else:
        raise ValueError('Exclusive source publication is unavailable on this platform')
    if result:
        error=ctypes.get_errno()
        raise OSError(error,os.strerror(error),str(destination))


def stage(root, recipe, *, run=subprocess.run):
    root=Path(root)
    model=root/'model'
    revision=recipe['model_revision']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Source revision must be a full commit SHA')
    if model.is_symlink():
        raise ValueError('Model checkout cannot be a symbolic link')
    if model.exists():
        if not model.is_dir():raise ValueError('Model checkout path is occupied')
        verify_source(model,revision,recipe.get('generated_source_hashes'))
        actual=run(['git','-C',str(model),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
        if actual!=revision:raise ValueError('Existing checkout revision differs; preserve it and review a separate runtime root')
        return model
    repository=recipe['model_repository']
    url=urlsplit(repository)
    if url.scheme!='https' or url.hostname!='github.com' or url.username or url.password or url.query or url.fragment:
        raise ValueError('Model source must be a credential-free reviewed GitHub HTTPS URL')
    root.mkdir(parents=True,exist_ok=True)
    # TemporaryDirectory removes only the directory this call created. A failed
    # fetch never publishes a partial model or deletes an existing model.
    with tempfile.TemporaryDirectory(prefix='.source-stage-',dir=root) as folder:
        temp=Path(folder)/'checkout';temp.mkdir()
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',PYTHONDONTWRITEBYTECODE='1')
        def git(*args):
            try:
                return run(['git','-C',str(temp),*args],check=True,capture_output=True,text=True,env=env,timeout=600)
            except subprocess.CalledProcessError:
                raise ValueError('Pinned source fetch or checkout failed. Check repository access and Git authentication on this machine; no partial model was activated.') from None
        git('init','-q')
        git('remote','add','origin',repository)
        git('fetch','--no-tags','--depth=1','origin',revision)
        git('checkout','--detach',revision)
        if git('rev-parse','HEAD').stdout.strip()!=revision:
            raise ValueError('Fetched source revision differs from review')
        verify_source(temp,revision,recipe.get('generated_source_hashes'))
        if model.exists() or model.is_symlink():
            raise ValueError('Model path appeared during staging; no replacement allowed')
        publish(temp,model)
        descriptor=os.open(str(root),os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    return model
