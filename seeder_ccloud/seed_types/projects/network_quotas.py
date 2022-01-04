"""
 Copyright 2022 SAP SE
 
 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
 
     http://www.apache.org/licenses/LICENSE-2.0
 
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""
import logging, kopf
from keystoneclient import exceptions
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_operator import SEED_CRD, OPERATOR_ANNOTATION


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.network_quotas')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.network_quotas')
def seed_domain_users_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} network_quotas'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        n = Network_Quotas(memo['args'])
        n.seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Network_Quotas():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, network_quotas):
        keystone = self.openstack.get_keystoneclient()
        limes = keystone.services.list(name='limes')
        # only seed network quota if limes is not available
        if len(limes):
            return
        
        for network_quota in network_quotas:
            self._seed_network_quota(network_quota)


    def _seed_network_quota(self, network_quota):
        """
        seed a projects network quota
        """
        project_id = self.openstack.get_project_id(network_quota['domain'], network_quota['project'])
        project_name = network_quota['project']
        logging.debug("seeding network-quota of project %s" % project_name)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        quota = self.openstack.sanitize(network_quota, (
            'floatingip', 'healthmonitor', 'l7policy', 'listener',
            'loadbalancer',
            'network', 'pool', 'port', 'rbac_policy', 'router',
            'security_group',
            'security_group_rule', 'subnet', 'subnetpool', 'bgpvpn'))
        
        body = {'quota': quota.copy()}
        result = neutron.show_quota(project_id)
        if not result or not result['quota']:
            logging.info(
                "set project %s network quota to '%s'" % (
                    project_name, quota))
            if not self.dry_run:
                neutron.update_quota(project_id, body)
        else:
            resource = result['quota']
            new_quota = {}
            for attr in list(quota.keys()):
                if int(quota[attr]) > int(resource.get(attr, '')):
                    logging.info(
                        "%s differs. set project %s network quota to '%s'" % (
                            attr, project_name, quota[attr]))
                    new_quota[attr] = quota[attr]
            if len(new_quota) and not self.dry_run:
                neutron.update_quota(project_id, {'quota': new_quota})   