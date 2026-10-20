"""Publish a checksum-bound helper bundle; never execute source-directory code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid
from toolchain_paths import protected_directory
from toolchain_launch import BUNDLE_FILES,verify_bundle


def publish_bundle(base,source,hashes):
    if os.geteuid()!=0:raise ValueError('Helper publication requires authorized sudo')
    if set(hashes)!=BUNDLE_FILES:raise ValueError('Incomplete reviewed helper manifest')
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    base=Path(base);source=Path(source);destination=base/digest
    with protected_directory(base) as parent:
        try:os.stat(digest,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:
            verify_bundle(destination,hashes)
            return {'path':str(destination),'manifest_sha256':digest,'reused':True}
        temporary='.bundle-'+uuid.uuid4().hex
        os.mkdir(temporary,0o700,dir_fd=parent)
        descriptor=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        try:
            for name in sorted(BUNDLE_FILES):
                # Read once and copy those exact bytes. A concurrent source edit
                # either matches the reviewed digest or is refused before publish.
                source_fd=os.open(source/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(source_fd,'rb') as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ValueError('Helper source is not a regular file')
                    content=handle.read(2*1024*1024+1)
                if len(content)>2*1024*1024 or hashlib.sha256(content).hexdigest()!=hashes[name]:
                    raise ValueError('Helper source differs from reviewed bytes: '+name)
                target=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444,dir_fd=descriptor)
                with os.fdopen(target,'wb') as handle:
                    handle.write(content);handle.flush();os.fsync(handle.fileno())
            os.fsync(descriptor)
            verify_bundle(base/temporary,hashes)
            try:os.rename(temporary,digest,src_dir_fd=parent,dst_dir_fd=parent)
            except (FileExistsError,OSError):
                # A concurrent publisher may have won. Only accept its exact
                # verified content; never replace or repair an existing bundle.
                verify_bundle(destination,hashes)
            os.fsync(parent)
            return {'path':str(destination),'manifest_sha256':digest,'reused':False}
        finally:
            os.close(descriptor)
            # Only remove the unpublished staging directory created by this call.
            remaining=base/temporary
            if remaining.exists():shutil.rmtree(remaining)
