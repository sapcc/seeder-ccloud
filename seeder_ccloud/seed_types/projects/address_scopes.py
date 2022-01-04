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
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_operator import SEED_CRD, OPERATOR_ANNOTATION
from subnet_pools import Subnet_Pools


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.address_scopes')
def validate(spec, dryrun, **_):
    address_scopes = spec.get('address_scopes', [])
    for address_scope in address_scopes:
        if 'name' not in address_scope or not address_scope['name']:
            raise kopf.AdmissionError("address_scope must have a name...")
        subnet_pools = address_scope.get('subnet_pools', [])
        for subnet_pool in subnet_pools:
            if 'name' not in subnet_pool or not subnet_pool['name']:
                raise kopf.AdmissionError("subnet_pool must have a name...")
        


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.address_scopes')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.address_scopes')
def seed_address_scopes_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} address_scopes'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        a = Address_Scopes(memo['args'])
        a.seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Address_Scopes():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.args = args
        self.dry_run = dry_run


    def seed(self, address_scopes):
        for address_scope in address_scopes:
            self._seed_address_scope(address_scope)


    def _seed_address_scope(self, scope):
        """
        seed a projects neutron address scopes and dependent objects
        :param project: 
        :param address_scopes: 
        :param args: 
        :param sess: 
        :return: 
        """
        project_name = scope['project']
        project_id = self.openstack.get_project_id(scope['domain'], project_name)
        
        logging.debug("seeding address-scopes of project %s" % project_name)

        neutron = self.openstack.get_neutronclient()
        try:
            subnet_pools = None
            if 'subnet_pools' in scope:
                subnet_pools = scope.pop('subnet_pools', None)

            scope = self.openstack.sanitize(scope, ('name', 'ip_version', 'shared'))

            body = {'address_scope': scope.copy()}
            body['address_scope']['tenant_id'] = project_id
            query = {'tenant_id': project_id, 'name': scope['name']}
            result = neutron.list_address_scopes(retrieve_all=True,
                                                **query)
            if not result or not result['address_scopes']:
                logging.info(
                    "create address-scope '%s/%s'" % (
                        project_name, scope['name']))
                if not self.dry_run:
                    result = neutron.create_address_scope(body)
                    resource = result['address_scope']
            else:
                resource = result['address_scopes'][0]
                for attr in list(scope.keys()):
                    if scope[attr] != resource.get(attr, ''):
                        logging.info(
                            "%s differs. update address-scope '%s/%s'" % (
                                attr, project_name, scope['name']))
                        # drop read-only attributes
                        body['address_scope'].pop('tenant_id', None)
                        body['address_scope'].pop('ip_version', None)
                        if not self.dry_run:
                            neutron.update_address_scope(resource['id'],
                                                        body)
                        break

            if subnet_pools:
                pools = Subnet_Pools(self.args, self.dry_run)
                for subnet_pool in subnet_pools:
                    subnet_pool['project'] = project_name
                    subnet_pool['address_scope_id'] = resource['id']
                pools.seed(subnet_pools)
        except Exception as e:
            logging.error("could not seed address scope %s/%s: %s" % (
                project_name, scope['name'], e))
            raise