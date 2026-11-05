"""Read-only legacy target validation and transports for existing job results."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import uuid
import fcntl
from datetime import datetime, timezone
from urllib.parse import urlparse

class Compute:
    @staticmethod
    def validate_config(cfg):
        kind = cfg.get('kind', 'brev')
        if kind not in ('local', 'ssh', 'brev'): raise ValueError('Choose local, ssh, or brev')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', cfg['instance']): raise ValueError('Use a simple target name')
        if kind == 'brev' and not cfg.get('instance_id'): raise ValueError('Brev requires an instance ID')
        if kind == 'ssh' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,200}', cfg.get('ssh_host','')): raise ValueError('Use an existing SSH config alias or user@host')
        for path in [cfg['remote_root'], *cfg.get('weight_paths',[])]:
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+',path) or '..' in path.split('/'): raise ValueError('Use absolute runtime and weight paths without traversal')
        parsed = urlparse(cfg['studio_url'])
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.path not in ('','/') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Studio must be a loopback HTTP service; tunnel remote Studio first')
        return cfg

    def target_exec(self,cfg,command,timeout=60):
        kind=cfg.get('kind','brev')
        if kind in ('brev','ssh'):
            from registry import execute
            return execute(cfg,command,self.run,timeout)
        return self.run(['bash','-lc',command],timeout)

    def target_copy(self,cfg,source,destination,download=False,timeout=180):
        kind=cfg.get('kind','brev')
        if kind in ('brev','ssh'):
            from registry import copy
            return copy(cfg,source,destination,download,self.run,timeout)
        src,dst=Path(source),Path(destination)
        if src.is_dir(): shutil.copytree(src,dst/src.name,dirs_exist_ok=True)
        else: shutil.copy2(src,dst)
