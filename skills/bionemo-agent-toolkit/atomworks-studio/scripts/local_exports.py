"""Bounded local exports for MCP hosts without file-download support."""
import base64
import hashlib
import json
from pathlib import Path
import re
import uuid

LIMIT = 20_000_000


def save(root, filename, mime_type, text=None, base64_data=None):
    if not isinstance(filename,str) or not filename or len(filename)>200:
        raise ValueError('Invalid export filename')
    name=re.sub(r'[\\/\x00-\x1f\x7f]', '_', filename)
    if mime_type=='chemical/x-mmcif' and name.endswith('.cif') and isinstance(text,str) and base64_data is None:
        if len(text)>LIMIT:raise ValueError('Export exceeds 20 MB')
        data=text.encode('utf-8')
    elif mime_type=='application/zip' and name.endswith('.zip') and text is None and isinstance(base64_data,str):
        if len(base64_data)>28_000_000:raise ValueError('Export exceeds 20 MB')
        data=base64.b64decode(base64_data,validate=True)
        if not data.startswith(b'PK'):raise ValueError('Invalid ZIP export')
    else:raise ValueError('Export must be a CIF text or ZIP archive')
    if not data or len(data)>LIMIT:raise ValueError('Export is empty or exceeds 20 MB')
    parent=Path(root)/'exports'
    if parent.is_symlink():raise ValueError('Export directory cannot be a symlink')
    parent.mkdir(mode=0o700,exist_ok=True)
    export_id=uuid.uuid4().hex
    directory=parent/export_id;directory.mkdir(mode=0o700)
    path=directory/name
    with path.open('xb') as handle:
        path.chmod(0o600);handle.write(data)
    record={'export_id':export_id,'filename':name,'mime_type':mime_type,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    manifest=directory/'receipt.json'
    with manifest.open('x') as handle:
        manifest.chmod(0o600);json.dump(record,handle)
    return record


def get(root, export_id):
    if not isinstance(export_id,str) or not re.fullmatch(r'[0-9a-f]{32}',export_id):
        raise ValueError('Invalid export ID')
    parent=Path(root)/'exports';directory=parent/export_id;receipt=directory/'receipt.json'
    if any(p.is_symlink() for p in (parent,directory,receipt)):raise ValueError('Export paths cannot be symlinks')
    record=json.loads(receipt.read_text())
    name=record.get('filename')
    if record.get('export_id')!=export_id or not isinstance(name,str) or Path(name).name!=name or name in ('.','..'):
        raise ValueError('Export receipt changed')
    path=directory/name
    if path.is_symlink() or not path.is_file() or path.stat().st_size>LIMIT:raise ValueError('Export file unavailable')
    data=path.read_bytes()
    if len(data)!=record['size'] or hashlib.sha256(data).hexdigest()!=record['sha256']:
        raise ValueError('Export file changed')
    return dict(record,path=str(path.resolve()))
