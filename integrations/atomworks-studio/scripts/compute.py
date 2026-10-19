"""Registered local/SSH/Brev transports. Provisioning belongs to the agent."""
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

    def register_compute(self, kind, name, runtime_root, studio_url, ssh_host='', instance_id='', weight_paths=None, session_id=None, registry_target=None):
        cfg = {'kind':kind,'instance':name,'remote_root':runtime_root,'studio_url':studio_url,'weight_paths':weight_paths or []}
        if kind == 'ssh': cfg['ssh_host'] = ssh_host
        if kind == 'brev': cfg['instance_id'] = instance_id
        if registry_target: raise ValueError('External registry references are no longer accepted')
        self.validate_config(cfg)
        import registry
        if kind == 'ssh': cfg['ssh_access'] = registry.effective_access(ssh_host, self.run)
        cfg = registry.Catalog(self.root).put(cfg)
        path = self.compute_config_path(session_id)
        temp = path.with_name(uuid.uuid4().hex+'.tmp')
        temp.write_text(json.dumps(cfg,indent=2)); temp.chmod(0o600); temp.replace(path)
        return self.compute_status(session_id)

    def compute_config_path(self, session_id=None):
        if session_id is None: return self.root/'config.json'
        from core import safe_session
        directory = self.root/'sessions'
        directory.mkdir(exist_ok=True, mode=0o700)
        return directory/(safe_session(session_id)+'.compute.json')

    def available_compute(self):
        import registry
        catalog = registry.Catalog(self.root)
        for path in [self.root/'config.json', *sorted((self.root/'sessions').glob('*.compute.json'))]:
            if path.exists(): catalog.migrate(path)
        return {'available': True, 'targets': [dict(target_id=k, provider='BioNeMo',
            title=v.get('title',v['instance']), executor='local_process', supported=True, kind=v['kind'])
            for k,v in catalog.read()['targets'].items()]}

    def register_registry_compute(self, target_id, runtime_root=None, studio_url=None, weight_paths=None, session_id=None):
        import registry
        cfg = registry.Catalog(self.root).resolve(target_id)
        # Selection reuses saved settings; changing them requires explicit registration.
        if any(value is not None and value != cfg[key] for key,value in
               [('remote_root',runtime_root),('studio_url',studio_url),('weight_paths',weight_paths)]):
            raise ValueError('Register updated runtime paths before selecting this target')
        self.validate_config(cfg)
        self.verify_target(cfg)
        registry.atomic(self.compute_config_path(session_id), cfg)
        return self.compute_status(session_id)

    def inspect_compute_target(self, target_id):
        import registry
        cfg = registry.Catalog(self.root).resolve(target_id)
        try:
            self.verify_target(cfg)
            self.target_exec(cfg, 'true', timeout=15)
            return {'target_id':target_id, 'connected':True, 'detail':'Connection checked; model readiness is checked separately.'}
        except Exception as error:
            return {'target_id':target_id, 'connected':False, 'detail':str(error)}

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

    def compute_status(self, session_id=None):
        try: cfg=self.config(session_id)
        except (ValueError,KeyError) as error: return self.with_setup({'state':'unregistered','detail':str(error)}, session_id)
        result={'state':'registered','kind':cfg.get('kind','brev'),'name':cfg.get('title',cfg['instance']),'detail':'Registered; readiness has not been checked.', 'fingerprint':self.target_fingerprint(cfg), 'source':'BioNeMo'}
        path=self.root/('compute-check-'+self.target_fingerprint(cfg)+'.json')
        if path.exists():
            check=json.loads(path.read_text())
            if check.get('fingerprint')==self.target_fingerprint(cfg):
                result.update(check)
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(check['checked_at'])).total_seconds()
                if age>900: result.update(state='registered',detail='Previous readiness check is over 15 minutes old; check again.')
        jobs = [json.loads(p.read_text()) for p in self.state.glob('*/job.json')]
        result['active_jobs'] = [j['job_id'] for j in jobs if j.get('target')==cfg and j['status'] in ('queued','submitting','submitted','submission_unknown','running')]
        return self.with_setup(result,session_id)

    def setup_path(self, session_id):
        from core import safe_session
        directory=self.root/'setup';directory.mkdir(exist_ok=True,mode=0o700)
        return directory/(safe_session(session_id or 'workspace')+'.json')

    def with_setup(self, result, session_id):
        path=self.setup_path(session_id)
        if path.exists():
            record=json.loads(path.read_text())
            result['setup']=record
            if record['stage'] in ('connecting','installing','downloading','checking') and result['state']!='ready':
                result['state']='setting_up'
            if record['stage']=='action_needed' and result['state']!='ready': result['state']='needs_setup'
        return result

    def begin_setup(self, session_id=None):
        path=self.setup_path(session_id)
        with (self.root/'setup.lock').open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            if path.exists():
                previous=json.loads(path.read_text())
                if previous['stage'] not in ('complete','cancelled'): return previous
            record={'request_id':uuid.uuid4().hex,'session_id':session_id,'stage':'requested','detail':'Continue setup in chat. No machine has been started.', 'updated_at':datetime.now(timezone.utc).isoformat()}
            temp=path.with_name(uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(record));temp.replace(path)
            return record

    def update_setup(self, request_id, stage, detail, session_id=None):
        if stage not in ('connecting','installing','downloading','checking','action_needed','complete','cancelled'):
            raise ValueError('Unsupported setup stage')
        if len(detail)>2000: raise ValueError('Use a short setup status')
        path=self.setup_path(session_id)
        with (self.root/'setup.lock').open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            record=json.loads(path.read_text())
            if record['request_id']!=request_id: raise ValueError('Setup request changed; inspect it before continuing')
            record.update(stage=stage,detail=detail,updated_at=datetime.now(timezone.utc).isoformat())
            temp=path.with_name(uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(record));temp.replace(path)
        return record

    def check_compute(self, session_id=None):
        from core import REVISION
        cfg=self.config(session_id); checks={}; gpu=''; connected=False
        try:
            import registry
            registry.Catalog(self.root).verify(cfg)
            self.verify_target(cfg)
            self.target_exec(cfg,'true'); connected=True
            gpu=self.target_exec(cfg,'nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader').strip()
            checks['gpu']=bool(gpu)
            root=cfg['remote_root']
            self.target_exec(cfg,f'test -x {shlex.quote(root+"/model/.venv/bin/rfd4-generate")} && test "$(cat {shlex.quote(root+"/model-revision")})" = {REVISION}')
            checks['runtime']=True
            checks['weights']=False
            if cfg.get('weight_paths'):
                self.target_exec(cfg,' && '.join('test -s '+shlex.quote(p) for p in cfg['weight_paths']))
                checks['weights']=True
            detail='GPU, runtime revision and registered weight files checked. No inference test was run.' if all(checks.values()) else 'GPU and runtime checked; register weight file paths to verify their presence.'
        except Exception as error: detail=str(error)
        result={'state':'ready' if len(checks)==3 and all(checks.values()) else ('needs_setup' if connected else 'disconnected'),'detail':detail,'checks':checks,'gpu':gpu,'checked_at':datetime.now(timezone.utc).isoformat(),'fingerprint':self.target_fingerprint(cfg)}
        path=self.root/('compute-check-'+self.target_fingerprint(cfg)+'.json')
        temp=path.with_name(uuid.uuid4().hex+'.tmp'); temp.write_text(json.dumps(result,indent=2)); temp.replace(path)
        return self.compute_status(session_id)
