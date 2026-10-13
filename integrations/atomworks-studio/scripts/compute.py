"""Registered local/SSH/Brev transports. Provisioning belongs to the agent."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
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

    def register_compute(self, kind, name, runtime_root, studio_url, ssh_host='', instance_id='', weight_paths=None):
        cfg = {'kind':kind,'instance':name,'remote_root':runtime_root,'studio_url':studio_url,'weight_paths':weight_paths or []}
        if kind == 'ssh': cfg['ssh_host'] = ssh_host
        if kind == 'brev': cfg['instance_id'] = instance_id
        self.validate_config(cfg)
        path = self.root/'config.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(cfg,indent=2)); temp.chmod(0o600); temp.replace(path)
        return self.compute_status()

    def target_exec(self,cfg,command,timeout=60):
        kind=cfg.get('kind','brev')
        if kind=='brev': return self.brev(cfg,'exec',cfg['instance'],command,timeout=timeout)
        if kind=='ssh': return self.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','--',cfg['ssh_host'],command],timeout)
        return self.run(['bash','-lc',command],timeout)

    def target_copy(self,cfg,source,destination,download=False,timeout=180):
        kind=cfg.get('kind','brev')
        if kind=='brev':
            args=[f"{cfg['instance']}:{source}",str(destination)] if download else [str(source),f"{cfg['instance']}:{destination}"]
            return self.brev(cfg,'copy',*args,timeout=timeout)
        if kind=='ssh':
            args=[f"{cfg['ssh_host']}:{source}",str(destination)] if download else [str(source),f"{cfg['ssh_host']}:{destination}"]
            return self.run(['scp','-r','-o','BatchMode=yes','-o','ConnectTimeout=10','--',*args],timeout)
        src,dst=Path(source),Path(destination)
        if src.is_dir(): shutil.copytree(src,dst/src.name,dirs_exist_ok=True)
        else: shutil.copy2(src,dst)

    @staticmethod
    def target_fingerprint(cfg):
        return hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()

    def compute_status(self):
        try: cfg=self.config()
        except (ValueError,KeyError) as error: return {'state':'unregistered','detail':str(error)}
        result={'state':'registered','kind':cfg.get('kind','brev'),'name':cfg['instance'],'detail':'Registered; readiness has not been checked.'}
        path=self.root/'compute-check.json'
        if path.exists():
            check=json.loads(path.read_text())
            if check.get('fingerprint')==self.target_fingerprint(cfg):
                result.update(check)
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(check['checked_at'])).total_seconds()
                if age>900: result.update(state='registered',detail='Previous readiness check is over 15 minutes old; check again.')
        return result

    def check_compute(self):
        from core import REVISION
        cfg=self.config(); checks={}; gpu=''
        try:
            self.verify_target(cfg)
            gpu=self.target_exec(cfg,'nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader').strip()
            checks['gpu']=bool(gpu)
            root=cfg['remote_root']
            self.target_exec(cfg,f'test -x {shlex.quote(root+"/model/.venv/bin/rfd4-generate")} && test "$(cat {shlex.quote(root+"/model-revision")})" = {REVISION}')
            checks['runtime']=True
            checks['weights']=False
            if cfg.get('weight_paths'):
                self.target_exec(cfg,' && '.join('test -s '+shlex.quote(p) for p in cfg['weight_paths']))
                checks['weights']=True
            self.studio('GET','schema'); checks['studio']=True
            detail='GPU, runtime revision, registered weight files and Studio checked. No inference test was run.' if all(checks.values()) else 'GPU and runtime checked; register weight file paths to verify their presence.'
        except Exception as error: detail=str(error)
        result={'state':'ready' if len(checks)==4 and all(checks.values()) else 'needs_setup','detail':detail,'checks':checks,'gpu':gpu,'checked_at':datetime.now(timezone.utc).isoformat(),'fingerprint':self.target_fingerprint(cfg)}
        (self.root/'compute-check.json').write_text(json.dumps(result,indent=2))
        return self.compute_status()
