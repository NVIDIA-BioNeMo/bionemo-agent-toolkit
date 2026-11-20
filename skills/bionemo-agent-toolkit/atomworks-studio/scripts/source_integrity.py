"""Compare tracked bytes with the immutable Git tree, independent of index flags."""
import hashlib
import os
from pathlib import Path
import subprocess


def verify_source(root, revision, generated=None):
    root=Path(root).resolve()
    tree=subprocess.check_output(['git','-C',str(root),'ls-tree','-rz','--full-tree',revision])
    tracked=set()
    for record in tree.split(b'\0'):
        if not record:continue
        metadata,name=record.split(b'\t',1)
        mode,kind,expected=metadata.decode().split()
        relative=name.decode();tracked.add(relative);path=root/relative
        if any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            raise ValueError('Source parent is a symbolic link: '+relative)
        if kind!='blob' or mode not in ('100644','100755','120000'):
            raise ValueError('Unsupported source tree entry: '+relative)
        if mode=='120000':
            if not path.is_symlink():raise ValueError('Source link changed: '+relative)
            contents=os.readlink(path).encode()
            if not path.resolve().is_relative_to(root):raise ValueError('Source link escapes checkout: '+relative)
        else:
            if path.is_symlink() or not path.is_file():raise ValueError('Source file missing or replaced: '+relative)
            if bool(path.stat().st_mode & 0o111) != (mode == '100755'):
                raise ValueError('Source executable mode changed: '+relative)
            contents=path.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()
        if actual!=expected:raise ValueError('Source differs from pinned tree: '+relative)
    # Scan the whole checkout, including ignored files and root-level imports.
    # Environment dependencies and downloaded model data have separate verifiers.
    # Never follow untracked directory links, including links back into the tree.
    excluded={'.git', '.venv', 'data_path'}
    executable_suffixes={'.py','.pyc','.pyo','.so','.pyd','.dll','.dylib',
                         '.yaml','.yml','.toml','.sh','.pth','.egg','.zip'}
    def traversal_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=traversal_error):
        parent=Path(directory)
        for name in list(dirs):
            path=parent/name;relative=path.relative_to(root).as_posix()
            if parent==root and name in excluded:
                dirs.remove(name)
                continue
            if path.is_symlink():
                if relative not in tracked:
                    raise ValueError('Untracked source directory link: '+relative)
                dirs.remove(name)
        for name in files:
            path=parent/name;relative=path.relative_to(root).as_posix()
            if relative in tracked:continue
            if path.is_symlink():
                raise ValueError('Untracked source link: '+relative)
            if path.suffix in executable_suffixes or path.stat().st_mode & 0o111:
                allowed=(generated or {}).get(relative)
                if not allowed or hashlib.sha256(path.read_bytes()).hexdigest()!=allowed:
                    raise ValueError('Untracked runtime source requires review: '+relative)
    return True
