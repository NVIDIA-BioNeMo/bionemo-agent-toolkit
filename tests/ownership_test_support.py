"""Explicit precondition for tests focused on contracts other than ownership.

This does not claim a machine or qualify ownership enforcement. The dedicated
ownership helper/operation/gate suites exercise refusal without these patches.
"""
from unittest.mock import patch
from executor_ownership import checksum


def assume_owned(test, service, *, skip_transport_identity=False):
    def proof(cfg):
        owner={'protocol':1,'executor_id':'a'*32,'controller_root_sha256':'b'*64,
               'linux_machine_id_sha256':'c'*64,'brev':None}
        provider=({'organization_id':cfg['organization_id'],'instance_id':cfg['instance_id']}
                  if cfg.get('kind')=='brev' else None)
        return {'owner':owner,'owner_checksum':checksum(owner),'brev':provider}
    for name,kwargs in [('local_ownership_proof',{'side_effect':proof}),
                        ('local_execution_scope',{'side_effect':proof}),
                        ('ownership_status',{'return_value':{'state':'owned'}})]:
        mocked=patch.object(service,name,**kwargs);mocked.start();test.addCleanup(mocked.stop)
    if skip_transport_identity:
        mocked=patch.object(service,'verify_target');mocked.start();test.addCleanup(mocked.stop)
