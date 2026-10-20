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

    def register_compute(self, kind, name, runtime_root, studio_url, ssh_host='', instance_id='', weight_paths=None, session_id=None, registry_target=None, organization_id=None, expected_revision=None):
        cfg = {'kind':kind,'instance':name,'remote_root':runtime_root,'studio_url':studio_url,'weight_paths':weight_paths or []}
        if kind == 'ssh': cfg['ssh_host'] = ssh_host
        if kind == 'brev': cfg['instance_id'] = instance_id
        if registry_target: raise ValueError('External registry references are no longer accepted')
        self.validate_config(cfg)
        import registry
        if kind == 'ssh': cfg['ssh_access'] = registry.effective_access(ssh_host, self.run)
        state = self.managed
        if kind == 'ssh':
            identity = registry.linux_machine_identity(cfg, self.run)
        elif kind == 'brev':
            if not organization_id:
                raise ValueError('Brev registration requires an explicit organization ID')
            cfg['organization_id'] = organization_id
            identity = {'provider': 'brev', 'organization_id': organization_id, 'instance_id': instance_id}
            # Updating only runtime paths must not discard this same machine's
            # verified access snapshot. Transport drift is still checked on use.
            prior=[m for m in state.snapshot()['machines'].values() if m['identity']==identity]
            if len(prior)==1 and prior[0]['config'].get('instance')==name and prior[0]['config'].get('ssh_access'):
                cfg['ssh_access']=prior[0]['config']['ssh_access']
        else:
            identity = registry.linux_machine_identity(cfg, self.run)
        session = session_id or 'workspace'
        revision = state.selection(session)['revision'] if expected_revision is None else expected_revision
        state.register(identity, cfg, session, revision)
        return self.compute_status(session_id)

    def disconnect_compute(self, session_id, expected_revision):
        selection = self.managed.select(session_id or 'workspace', None, expected_revision)
        return {'selection': selection, 'detail': 'Disconnected this session. The machine and its jobs remain running; billing is unchanged.'}

    def capabilities(self):
        from managed_state import SCHEMA
        return {'protocol': 3, 'schema': SCHEMA, 'executor_id': self.managed.snapshot()['executor_id'],
                'execution': 'single_user_local_executor', 'transports': ['local', 'ssh', 'brev'],
                'inference_cancellation': False, 'shared_compute': False}

    def compute_config_path(self, session_id=None):
        if session_id is None: return self.root/'config.json'
        from core import safe_session
        directory = self.root/'sessions'
        directory.mkdir(exist_ok=True, mode=0o700)
        return directory/(safe_session(session_id)+'.compute.json')

    def available_compute(self):
        data = self.managed.snapshot()
        return {'available': True, 'targets': [dict(target_id=k, provider='BioNeMo',
            title=v['config'].get('title', v['config']['instance']), executor='local_process',
            supported=True, kind=v['config']['kind']) for k,v in data['machines'].items()],
            'unresolved': data.get('migration', {}).get('unresolved', [])}

    def register_registry_compute(self, target_id, runtime_root=None, studio_url=None, weight_paths=None, session_id=None, expected_revision=None):
        state = self.managed
        machine = state.machine(target_id)
        cfg = machine['config']
        if any(value is not None and value != cfg[key] for key,value in
               [('remote_root',runtime_root),('studio_url',studio_url),('weight_paths',weight_paths)]):
            raise ValueError('Register updated runtime paths before selecting this target')
        self.validate_config(cfg)
        identity = None
        if cfg['kind'] in ('local', 'ssh'):
            import registry
            identity = registry.linux_machine_identity(cfg, self.run)
        session = session_id or 'workspace'
        revision = state.selection(session)['revision'] if expected_revision is None else expected_revision
        state.select(session, target_id, revision, identity, machine['revision'])
        return self.compute_status(session_id)

    def inspect_compute_target(self, target_id):
        cfg = dict(self.managed.machine(target_id)['config'],target_id=target_id)
        try:
            self.verify_target(cfg)
            self.target_exec(cfg, 'true', timeout=15)
            return {'target_id':target_id, 'connected':True, 'detail':'Connection checked; model readiness is checked separately.'}
        except Exception as error:
            return {'target_id':target_id, 'connected':False, 'detail':str(error)}

    def target_exec(self,cfg,command,timeout=60):
        kind=cfg.get('kind','brev')
        if kind in ('brev','ssh'):
            from ssh_transport import execute
            return execute(cfg,command,self.run,timeout)
        return self.run(['bash','-lc',command],timeout)

    def refresh_compute_access(self,operation_id,machine_id):
        from access_refresh import refresh
        return refresh(self,operation_id,machine_id)

    def refresh_selected_compute_access(self,session_id,expected_revision):
        selection,cfg=self.selected_compute(session_id)
        if selection['revision']!=expected_revision:
            raise ValueError('Compute selection changed; select the machine again')
        if cfg is None or cfg['kind']!='brev':
            raise ValueError('Select a saved Brev machine before refreshing its access')
        operation=self.begin_setup(session_id,cfg['target_id'],expected_revision)
        return self.refresh_compute_access(operation['id'],cfg['target_id'])

    def recover_compute_access(self,operation_id):
        from access_refresh import recover
        return recover(self,operation_id)

    def target_copy(self,cfg,source,destination,download=False,timeout=180):
        kind=cfg.get('kind','brev')
        if kind in ('brev','ssh'):
            from ssh_transport import copy
            return copy(cfg,source,destination,download,self.run,timeout)
        src,dst=Path(source),Path(destination)
        if src.is_dir(): shutil.copytree(src,dst/src.name,dirs_exist_ok=True)
        else: shutil.copy2(src,dst)

    @staticmethod
    def target_fingerprint(cfg):
        return hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()

    def compute_status(self, session_id=None):
        selection, cfg = self.selected_compute(session_id)
        if not selection['machine_id']:
            return self.with_setup({'state':'unregistered', 'selection':selection, 'detail':'Connect compute for this session.'}, session_id)
        result={'selection':selection, 'state':'registered','kind':cfg.get('kind','brev'),'name':cfg.get('title',cfg['instance']),'detail':'Registered; readiness has not been checked.', 'fingerprint':self.target_fingerprint(cfg), 'source':'BioNeMo'}
        path=self.root/('compute-check-'+self.target_fingerprint(cfg)+'.json')
        if path.exists():
            check=json.loads(path.read_text())
            if check.get('fingerprint')==self.target_fingerprint(cfg):
                result.update(check)
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(check['checked_at'])).total_seconds()
                if age>900: result.update(state='registered',detail='Previous readiness check is over 15 minutes old; check again.')
        result.update(self.machine_jobs(cfg['target_id']))
        if self.runtime_setup_incomplete(cfg['target_id']):
            result.update(state='needs_setup',detail='Runtime setup has not passed acceptance. Complete or recover setup before running a design.')
        from ownership_operation import OwnershipRequired, ConnectionRequired
        try:
            proof=self.local_execution_scope(cfg)
            if result.get('state')=='ready' and result.get('executor_ownership')!=proof:
                result.update(state='registered',detail='Executor ownership or readiness evidence changed; check again before running.')
        except ConnectionRequired as error:
            result.update(state='registered',detail=str(error),provider_error=error.code)
        except OwnershipRequired as error:
            result.update(state='ownership_required',detail=str(error),provider_error=error.code)
        return self.with_setup(result,session_id)

    def runtime_setup_incomplete(self, machine_id):
        data=self.managed.snapshot()
        operation=data['machines'][machine_id].get('runtime_setup_operation')
        if not operation:return False
        op=data['operations'].get(operation,{})
        acceptance=data['machines'][machine_id].get('setup_acceptance',{})
        return (op.get('state')!='succeeded' or op.get('review',{}).get('phase')=='prepare_archives'
                or acceptance.get('operation_id')!=operation or acceptance.get('stage')!='accepted'
                or acceptance.get('ready') is not True)

    def machine_jobs(self, machine_id):
        jobs = [json.loads(p.read_text()) for p in self.state.glob('*/job.json')]
        metadata = self.managed.snapshot()
        mapping = metadata.get('legacy_target_mapping', {})
        bindings = metadata.get('legacy_run_bindings', {})
        from managed_state import State
        selected=metadata['machines'].get(machine_id)
        physical=State._physical(selected) if selected else None
        related={machine_id}
        if physical:
            related.update(key for key,machine in metadata['machines'].items() if State._physical(machine)==physical)
        def machine_for(job):
            if job['job_id'] in bindings:
                return bindings[job['job_id']]['machine_id']
            target = job.get('machine_id') or job.get('target', {}).get('target_id')
            return mapping.get(target, target)
        result = {}
        result['active_jobs'] = [j['job_id'] for j in jobs if machine_for(j) in related and j['status'] in ('queued','submitting','submitted','submission_unknown','running')]
        def unresolved(job):
            machine = metadata['machines'].get(machine_for(job))
            return machine is None or not State._physical(machine)
        result['unresolved_active_jobs'] = [j['job_id'] for j in jobs
            if unresolved(j) and j['status'] in ('queued','submitting','submitted','submission_unknown','running')]
        return result

    def with_setup(self, result, session_id):
        session = session_id or 'workspace'
        operations = [op for op in self.managed.snapshot()['operations'].values()
                      if op['session_id'] == session]
        if operations:
            result['operation'] = self.managed.operation(operations[-1]['id'])
        return result

    def begin_setup(self, session_id=None, target_id=None, expected_revision=None):
        session = session_id or 'workspace'
        state = self.managed
        selection = state.selection(session)
        revision = selection['revision'] if expected_revision is None else expected_revision
        return state.request(session, 'connect', target_id, revision)

    def compute_operation(self, operation_id):
        op = self.managed.operation(operation_id)
        # Context is authoritative data, not instructions or approval.
        return {'operation': op, 'selection': self.managed.selection(op['session_id']),
                'choices': ['connect_existing', 'start_previous_brev', 'create_brev'],
                'requires_user_choice': True,
                'detail': 'Inspect the selected saved machine and continue the intended connection/setup action. A prior shutdown does not cancel a new request. A running dedicated Brev machine can use dedicated-user execution without a privileged ownership claim; verify its physical identity and live runtime. Existing ownership-bound machines and historical jobs keep their committed-owner checks. Stopped-machine lifecycle safeguards are unchanged; provider visibility or a reused name is insufficient. This request does not authorize claiming, provisioning or stopping.'}

    def check_compute(self, session_id=None):
        from core import REVISION
        selection, cfg = self.selected_compute(session_id)
        if cfg is None:
            return self.compute_status(session_id)
        if self.runtime_setup_incomplete(cfg['target_id']):
            return self.compute_status(session_id)
        checks={}; gpu=''; connected=False; power='unknown'; provider_error=None;ownership=None
        try:
            if cfg['kind'] == 'brev':
                from brev_provider import Brev
                observation = Brev(self.run).observe(cfg['organization_id'], cfg['instance_id'])
                power = observation['power']
                if power != 'running':
                    raise ValueError('Brev reports ' + power + '; resolve compute in chat before connecting')
            ownership=self.require_execution_scope(cfg)
            self.target_exec(cfg,'true'); connected=True
            from runtime_recipe import inspect
            evidence = inspect(self, cfg)
            checks = evidence['checks']
            gpu = '\n'.join(f"{g['name']}, {g['memory'] // (1024**2)} MiB" for g in evidence['gpus'])
            detail = 'Pinned runtime and checkpoint digests verified. No inference test was run.' if all(checks.values()) else '; '.join(evidence['details'] + ['Failed checks: ' + ', '.join(k for k,v in checks.items() if not v)])
        except Exception as error:
            detail=str(error)
            provider_error=getattr(error, 'code', None)
        result={'state':('ownership_required' if provider_error=='executor_ownership_required' else ('ready' if len(checks)==9 and all(checks.values()) else ('needs_setup' if connected else 'disconnected'))),'detail':detail,'checks':checks,'gpu':gpu,'power':power,'transport':'reachable' if connected else 'unreachable','provider_error':provider_error,'checked_at':datetime.now(timezone.utc).isoformat(),'fingerprint':self.target_fingerprint(cfg)}
        result['executor_ownership']=ownership
        if self.managed.selection(session_id or 'workspace') != selection:
            return self.compute_status(session_id)
        path=self.root/('compute-check-'+self.target_fingerprint(cfg)+'.json')
        temp=path.with_name(uuid.uuid4().hex+'.tmp'); temp.write_text(json.dumps(result,indent=2)); temp.replace(path)
        return self.compute_status(session_id)
