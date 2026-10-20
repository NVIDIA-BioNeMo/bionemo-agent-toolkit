"""Managed setup preparation; runtime mutation is bound to a reviewed recipe."""
import hashlib
import json
from pathlib import Path
import tempfile
from runtime_recipe import RECIPE

CHECKSUM_TOKEN='__RFD4_REVIEW_CHECKSUM__'


def setup_template(scripts, review, remote):
    import shlex
    import ownership_adapter
    guard=ownership_adapter.command('require_execution_scope',review['executor_ownership']['owner'],
                                    proof=review['executor_ownership'],files=review['ownership_guard_files'],scripts=scripts)
    return '#!/bin/bash\nset -e\nexport PYTHONDONTWRITEBYTECODE=1\n'+guard+'\nexec '+shlex.join([
        'python3','-B',remote+'/runtime_setup.py',review['remote_root'],
        review['operation_id'],remote+'/setup-review.json',CHECKSUM_TOKEN])+'\n'


def setup_expected(review, review_checksum):
    from execution_payload import validate_manifest
    script=review['execution_script_template'].replace(CHECKSUM_TOKEN,review_checksum)
    files=dict(review['files'])
    files['run.sh']=hashlib.sha256(script.encode()).hexdigest()
    files['setup-review.json']=hashlib.sha256(json.dumps(review,sort_keys=True).encode()).hexdigest()
    return validate_manifest(files,{'kind':'setup','id':review['operation_id'],
        'review_checksum':review_checksum,'executor_ownership':review['executor_ownership']})


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def prerequisite_profile():
    return json.loads(Path(__file__).with_name('toolchain_profile.json').read_text())


def setup_payload(scripts, destination, review, remote, review_checksum):
    """Snapshot the bytes that were reviewed, never reread them after hashing."""
    import shlex
    destination.mkdir()
    for name,digest in review['files'].items():
        if Path(name).name!=name or name in ('setup-review.json','run.sh'):
            raise ValueError('Invalid setup helper filename')
        source=scripts/name
        if source.is_symlink():raise ValueError('Setup helper cannot be a symlink')
        content=source.read_bytes()
        if hashlib.sha256(content).hexdigest()!=digest:
            raise ValueError('Setup package changed while staging')
        (destination/name).write_bytes(content)
    (destination/'setup-review.json').write_text(json.dumps(review,sort_keys=True))
    template=review.get('execution_script_template')
    if template is None:
        template=setup_template(destination,review,remote)
    (destination/'run.sh').write_text(template.replace(CHECKSUM_TOKEN,review_checksum))


class SetupOperation:
    def review_prerequisites(self, machine):
        import shlex
        if RECIPE.get("install_mode") == "public_wheels" or RECIPE["id"] == "rfd4-public-c7c6cac-wheels-v1":
            from public_prerequisite import probe_script,bind_review
        else:
            from prerequisite_review import probe_script,bind_review
        cfg=dict(machine['config'],target_id=machine['id'])
        self.verify_target(cfg)
        return bind_review(json.loads(self.target_exec(cfg,shlex.join(['python3','-I','-c',probe_script()]),timeout=180)))

    def cancel_compute_operation(self, operation_id):
        import shlex
        op=self.managed.cancel(operation_id)
        if op['action']=='setup' and op['dispatched'] and op['state']=='needs_attention':
            cfg=dict(self.managed.machine(op['machine_id'])['config'],target_id=op['machine_id'])
            path=op['review']['remote_root']+'/setup-operations/'+operation_id+'/cancel-requested'
            code='import os,sys; f=open(sys.argv[1],"a"); f.flush(); os.fsync(f.fileno()); f.close()'
            try:
                if not op['review'].get('executor_ownership'):
                    raise ValueError('Legacy setup has no ownership proof; inspect its outcome without delivering a new remote cancellation.')
                self.require_execution_scope(cfg,op['review']['executor_ownership'])
                self.target_exec(cfg,shlex.join(['python3','-c',code,path]))
                return dict(op,detail='Cancellation delivered. The active stage may finish; subsequent setup stages will stop. Reconcile before releasing the machine.')
            except Exception as error:
                return dict(op,detail='Cancellation recorded locally, but remote delivery is unconfirmed. Retry cancellation and reconcile; setup may still progress.',delivery_error=str(error))
        return op

    def prepare_runtime_setup(self, operation_id, machine_id):
        state=self.managed
        machine=state.machine(machine_id)
        op=state.choose(operation_id,'setup',machine_id)
        scripts=Path(__file__).parent
        cfg=dict(machine['config'],target_id=machine_id)
        ownership=self.require_execution_scope(cfg)
        prerequisites=self.review_prerequisites(machine)
        preparation=prerequisites.get('status')=='preparation_required'
        files=['runtime_setup.py','runtime_install.py','runtime_install_profile.json','runtime_dependencies.lock','runtime_bootstrap.py','source_stage.py','source_integrity.py','runtime_recipe.py','runtime_recipe.json','runtime_download.py','runtime_smoke.py','generation.py','public_model_bundle.py','remote_job.py','toolchain_paths.py','executor_ownership.py','ownership_adapter.py','execution_payload.py']
        files+=['prerequisite_privileged.py','prerequisite_setup.py','prerequisite_review.py','toolchain_profile.json','toolchain_review.py','toolchain_plan.py']
        files+=['toolchain_download.py','toolchain_bundle.py','toolchain_owner.py','toolchain_recovery.py']
        from toolchain_launch import BUNDLE_FILES
        if prerequisites.get("kind") == "public_wheels":
            files += ["public_prerequisite.py"]
        files=sorted(set(files)|BUNDLE_FILES)
        import ownership_adapter
        review={'operation_id':operation_id,'action':'setup','machine_id':machine_id,'executor_ownership':ownership,
                'ownership_guard_files':ownership_adapter.manifest(scripts),
                'machine_revision':machine['revision'],'selection_revision':op['selection_revision'],
                'session_id':op['session_id'],'recipe_id':RECIPE['id'],
                'recipe_checksum':checksum(RECIPE),'recipe':json.loads(json.dumps(RECIPE)),'remote_root':machine['config']['remote_root'],
                'prerequisites':prerequisites,
                'prerequisite_requires_sudo':bool(prerequisites.get('changes')),
                'prerequisite_download_bytes':prerequisites['download_bytes'],
                'files':{name:hashlib.sha256((scripts/name).read_bytes()).hexdigest() for name in files},
                'effect':'Fetch the reviewed model commit using existing Git access if no checkout exists, then install the hash-locked public wheels and download the pinned model/autoencoder bundle. Then run one upstream short-monomer inference to validate setup.'}
        if prerequisites.get('kind') == 'public_wheels':
            review['effect'] = ('Install the reviewed hash-locked public wheels and pinned Python 3.12 bootstrap, '
                                'download verified model files, then run one short-monomer inference. '
                                'No apt, compiler installation, or privileged operating-system package changes are planned. '
                                'The preliminary platform/driver review does not establish GPU runtime or inference readiness.')
        if preparation:
            review['phase']='prepare_archives'
            review['effect']=('Download and verify '+str(len(prerequisites['packages']))+
                              ' pinned package archives ('+str(prerequisites['download_bytes'])+
                              ' bytes) into the machine cache. No package installation or model execution. '
                              'After preparation, request a separate installation review.')
        else:
            review['effect']+=(' The prerequisite review contains '+str(len(prerequisites['changes']))+' operating-system package changes requiring sudo.'
                               if prerequisites['changes'] else ' Operating-system prerequisites conform; no privileged package installation is planned.')
        import execution_adapter
        review['publication_bundle']=execution_adapter.bundle(scripts)
        review['publication_files']=execution_adapter.manifest(review['publication_bundle'])
        if any(review['publication_files'].get(name)!=review['files'][name] for name in (module+'.py' for module in execution_adapter.MODULES)):
            raise ValueError('Setup publication helper changed during review')
        remote=review['remote_root']+'/setup-operations/'+operation_id
        review['execution_script_template']=setup_template(scripts,review,remote+'/payload')
        digest=checksum(review)
        local=self.state/operation_id/'setup-payloads'/digest
        local.parent.mkdir(parents=True,exist_ok=True)
        expected=setup_expected(review,digest)
        from run_payload import file_hashes
        if local.exists():
            if local.is_symlink() or file_hashes(local)!=expected['files']:raise ValueError('Frozen setup payload changed')
        else:
            # No network or execution: retain exact reviewed helper bytes locally.
            with tempfile.TemporaryDirectory(prefix='.setup-payload-',dir=local.parent) as temporary:
                staged=Path(temporary)/'payload'
                setup_payload(scripts,staged,review,remote+'/payload',digest)
                if file_hashes(staged)!=expected['files']:raise ValueError('Setup payload differs from review')
                import os
                for path in staged.iterdir():
                    with path.open('rb') as handle:os.fsync(handle.fileno())
                fd=os.open(staged,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
                from source_stage import publish
                try:publish(staged,local)
                except FileExistsError:
                    if local.is_symlink() or file_hashes(local)!=expected['files']:raise ValueError('Conflicting setup payload appeared')
                fd=os.open(local.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
        with state.transaction() as data:
            current=data['operations'][operation_id]
            if current['state']!='requested' or current['action']!='setup' or current['machine_id']!=machine_id or current['machine_revision']!=machine['revision'] or current['cancel_requested']:
                raise ValueError('Setup operation changed; review again')
            current['review']=review
        return {k:v for k,v in review.items() if k not in ('publication_bundle','execution_script_template')} | {'review_checksum':digest}

    def execute_runtime_setup(self, operation_id, review_checksum):
        import shlex
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if not review or op['action']!='setup' or review['machine_id']!=op['machine_id'] or checksum(review)!=review_checksum:
            raise ValueError('Setup review changed')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        if op['dispatched']:return self.reconcile_runtime_setup(operation_id)
        preparation=review.get('phase')=='prepare_archives'
        if preparation!=(review.get('prerequisites',{}).get('status')=='preparation_required'):
            raise ValueError('Setup preparation phase does not match its review')
        local=self.state/operation_id/'setup-payloads'/review_checksum
        from run_payload import file_hashes
        if not review.get('execution_script_template') or local.is_symlink() or file_hashes(local)!=setup_expected(review,review_checksum)['files']:
            raise ValueError('Frozen setup package changed; review again')
        profile=json.loads((local/'toolchain_profile.json').read_text())
        if review.get('prerequisites',{}).get('changes') and profile.get('status')!='qualified':
            raise ValueError('Privileged prerequisite profile has not completed qualification')
        if op['state']!='authorized':
            state.transition(operation_id,'authorized',evidence={'kind':'reviewed_tool_call','checksum':review_checksum},expected_review_checksum=review_checksum)
        cfg=dict(state.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        remote=review['remote_root']+'/setup-operations/'+operation_id
        try:
            state.reserve(op['machine_id'],operation_id,'setup')
            jobs=self.machine_jobs(op['machine_id'])
            if jobs['active_jobs'] or jobs['unresolved_active_jobs']:
                raise ValueError('Active or unresolved jobs block runtime mutation')
            if not review.get('executor_ownership'):
                raise ValueError('Setup review predates executor ownership; prepare a new review.')
            self.require_execution_scope(cfg,review['executor_ownership'])
            if self.review_prerequisites(state.machine(op['machine_id']))!=review['prerequisites']:
                raise ValueError('Machine prerequisites changed; obtain a new setup review')
            jobs=self.machine_jobs(op['machine_id'])
            if jobs['active_jobs'] or jobs['unresolved_active_jobs']:
                raise ValueError('Active or unresolved jobs on the verified host block runtime mutation')
            import uuid,execution_adapter
            from execution_payload import canonical
            expected=setup_expected(review,review_checksum)
            attempt=remote+'/uploads/'+uuid.uuid4().hex
            self.target_exec(cfg,'mkdir -p '+shlex.quote(attempt))
            self.target_copy(cfg,local,attempt,timeout=180)
            publication=json.loads(self.target_exec(cfg,execution_adapter.command(attempt+'/'+local.name,remote+'/payload',expected,operation_id,
                reviewed_bundle=review['publication_bundle'],reviewed_files=review['publication_files']),timeout=180))
            if publication.get('path')!=remote+'/payload' or publication.get('manifest_sha256')!=hashlib.sha256(canonical(expected)).hexdigest():
                raise ValueError('Setup publication receipt differs from review')
            state.transition(operation_id,'dispatched',expected_review_checksum=review_checksum)
        except Exception:
            current=state.operation(operation_id)
            if current['state']=='authorized' and not current['dispatched']:
                state.transition(operation_id,'failed',evidence={'kind':'setup_not_dispatched'},release_reservation=True)
            raise
        try:
            receipt=json.loads(self.target_exec(cfg,shlex.join(['python3','-B',remote+'/payload/remote_job.py','launch-published',remote,operation_id,canonical(expected).decode()])))
            if receipt.get('job_id')!=operation_id:raise ValueError('Setup receipt identity mismatch')
            return self.reconcile_runtime_setup(operation_id)
        except Exception as error:
            current=state.operation(operation_id)
            if current['state']=='dispatched':
                state.transition(operation_id,'needs_attention',evidence={'kind':'unknown_setup_outcome','detail':str(error)})
            raise

    def reconcile_runtime_setup(self, operation_id):
        import shlex
        state=self.managed;op=state.operation(operation_id)
        if op['action']!='setup' or not op.get('review'):raise ValueError('No reviewed setup operation')
        if not op['dispatched'] or op['state'] in ('succeeded','failed','cancelled'):return op
        cfg=dict(state.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        remote=op['review']['remote_root']+'/setup-operations/'+operation_id
        self.verify_target(cfg)
        helper=remote+('/payload' if op['review'].get('execution_script_template') else '')+'/remote_job.py'
        result=json.loads(self.target_exec(cfg,shlex.join(['python3','-B',helper,'status',remote,operation_id])))
        if result.get('job_id')!=operation_id:raise ValueError('Setup status identity mismatch')
        if result['state']=='failed':
            if op['cancel_requested']:
                try:
                    journal=json.loads(self.target_exec(cfg,'cat '+shlex.quote(op['review']['remote_root']+'/runtime-setup.json')))
                except Exception as error:
                    # Terminal process evidence is sufficient to record failure.
                    # A missing journal cannot prove that cancellation caused it.
                    return state.transition(operation_id,'failed',evidence={'kind':'remote_setup_terminal','result':result,'cancellation_unconfirmed':True,'journal_error':str(error)},release_reservation=True)
                if journal.get('operation_id')==operation_id and journal.get('stage')=='cancelled':
                    return state.transition(operation_id,'cancelled',evidence={'kind':'setup_cancelled','result':result,'journal':journal},release_reservation=True)
            return state.transition(operation_id,'failed',evidence={'kind':'remote_setup_terminal','result':result},release_reservation=True)
        if result['state']=='completed':
            journal=json.loads(self.target_exec(cfg,'cat '+shlex.quote(op['review']['remote_root']+'/runtime-setup.json')))
            if op['review'].get('phase')=='prepare_archives':
                if (journal.get('operation_id')!=operation_id or journal.get('stage')!='archives_prepared'
                        or journal.get('ready') is not False or journal.get('review_checksum')!=checksum(op['review'])
                        or journal.get('prepared_packages')!=op['review']['prerequisites']['packages']):
                    raise ValueError('Preparation completion lacks matching archive evidence')
                return state.transition(operation_id,'succeeded',evidence={'kind':'archives_prepared','journal':journal},
                                        release_reservation=True)
            if journal.get('operation_id')!=operation_id or journal.get('recipe_id')!=op['review']['recipe_id'] or journal.get('stage')!='accepted' or journal.get('ready') is not True or not journal.get('smoke',{}).get('structures'):
                raise ValueError('Setup completion lacks matching smoke acceptance evidence')
            from setup_acceptance import validate
            paths=validate(op['review'],journal)
            return state.complete_setup(operation_id,checksum(op['review']),journal,paths)
        if result.get('package_stage') and op['review'].get('prerequisites',{}).get('changes'):
            try:result['prerequisite_status']=self.reconcile_setup_prerequisites(op,'observe')
            except Exception as error:result['prerequisite_observation_error']=str(error)
        if result['state']=='unknown':
            if op['state']=='dispatched':
                op=state.transition(operation_id,'needs_attention',evidence={'kind':'unknown_setup_process','result':result})
            return dict(op,remote_status=result,recovery_action='recover_runtime_setup',detail='Setup process outcome is unknown. Recover checks remote leases and permanently fences an orphaned dispatch; it never repeats installation. If the machine is unreachable, reconnect before recovery.')
        return dict(op,remote_status=result,detail='Monitoring the original setup; no installer was repeated.')

    def reconcile_setup_prerequisites(self, op, action):
        import shlex
        review=op['review']
        cfg=dict(self.managed.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        if action!='observe':
            if not review.get('executor_ownership'):raise ValueError('Setup recovery lacks executor ownership proof')
            self.require_execution_scope(cfg,review['executor_ownership'])
        else:self.verify_target(cfg)
        remote=review['remote_root']+'/setup-operations/'+op['id']
        payload=remote+('/payload' if review.get('execution_script_template') else '')
        result=json.loads(self.target_exec(cfg,shlex.join(['python3','-B',payload+'/prerequisite_privileged.py',
            action,review['remote_root'],op['id'],payload+'/setup-review.json',checksum(review)]),timeout=180))
        if result.get('job_id')!=op['id']:raise ValueError('Prerequisite recovery identity mismatch')
        return result

    def recover_runtime_setup(self, operation_id):
        import shlex
        op=self.managed.operation(operation_id)
        if op['action']!='setup' or not op.get('review') or not op['dispatched']:
            raise ValueError('No dispatched setup to recover')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        cfg=dict(self.managed.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        if not op['review'].get('executor_ownership'):raise ValueError('Setup recovery lacks executor ownership proof')
        self.require_execution_scope(cfg,op['review']['executor_ownership'])
        remote=op['review']['remote_root']+'/setup-operations/'+operation_id
        if op['review'].get('prerequisites',{}).get('changes'):
            helper=remote+('/payload' if op['review'].get('execution_script_template') else '')+'/remote_job.py'
            before=json.loads(self.target_exec(cfg,shlex.join(['python3','-B',helper,'status',remote,operation_id])))
            if before.get('job_id')!=operation_id:raise ValueError('Setup status identity mismatch')
            if before.get('package_stage'):
                prerequisite=self.reconcile_setup_prerequisites(op,'recover')
                if prerequisite.get('state') not in ('succeeded','failed'):
                    return dict(op,prerequisite_status=prerequisite,detail='The original package stage remains unresolved; no setup was repeated or reservation released.')
            # remote_job.recover rechecks protected package-transaction ownership
            # under executor leases. The separate executor ownership check above
            # is performed by this controller, not by that remote recovery helper.
        helper=remote+('/payload' if op['review'].get('execution_script_template') else '')+'/remote_job.py'
        result=json.loads(self.target_exec(cfg,shlex.join(['python3','-B',helper,'recover',remote,operation_id])))
        if result.get('job_id')!=operation_id:raise ValueError('Setup recovery identity mismatch')
        if result.get('reason')=='orphaned_dispatch_fenced' and result.get('state')=='failed':
            return self.managed.transition(operation_id,'failed',evidence={'kind':'orphaned_setup_fenced','result':result},release_reservation=True)
        return self.reconcile_runtime_setup(operation_id)
