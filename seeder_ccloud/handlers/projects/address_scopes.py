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
from typing import List
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.handlers.projects.subnet_pools import Subnet_Pools
from deepdiff import DeepDiff

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.address_scopes')
def validate_address_scopes(memo: kopf.Memo, dryrun, spec, old, warnings: List[str], **_):
    address_scopes = spec['openstack'].get('address_scopes', [])
    for address_scope in address_scopes:
        if 'name' not in address_scope or not address_scope['name']:
            raise kopf.AdmissionError("address_scope must have a name...")
        subnet_pools = address_scope.get('subnet_pools', [])
        for subnet_pool in subnet_pools:
            if 'name' not in subnet_pool or not subnet_pool['name']:
                raise kopf.AdmissionError("subnet_pool must have a name...")

    if dryrun and address_scopes:
        old_address_scopes = None
        if old is not None:
            old_address_scopes = old['spec']['openstack'].get('address_scopes', None)
        try: 
            changed = utils.get_changed_seeds(old_address_scopes, address_scopes)
            diffs = Address_Scopes(memo['args'], dryrun).seed(changed)
            if diffs:
                warnings.append({'address_scopes': diffs})
        except Exception as e:
            raise kopf.AdmissionError(e)


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.address_scopes')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.address_scopes')
def seed_address_scopes_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.debug('seeding {} address_scopes'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError(f"error seeding {name}: dependencies error", delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Address_Scopes(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError(f"error seeding {name}: {error}", delay=30)


class Address_Scopes():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.args = args
        self.dry_run = dry_run


    def seed(self, address_scopes):
        self.diffs = {}
        for address_scope in address_scopes:
            try:
                self._seed_address_scope(address_scope)
            except Exception as e:
                raise Exception(f"{address_scope['name']}. error: {e}")
        return self.diffs


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
        domain_name = scope['domain']
        project_id = self.openstack.get_project_id(domain_name, project_name)
        
        logging.debug(f"seeding address-scope {scope['name']} of project {project_name}")

        neutron = self.openstack.get_neutronclient()
        self.diffs[scope['name']] = []
 
        subnet_pools = None
        if 'subnet_pools' in scope:
            subnet_pools = scope.pop('subnet_pools', None)

        scope = self.openstack.sanitize(scope, ('name', 'ip_version', 'shared'))

        body = {'address_scope': scope.copy()}
        body['address_scope']['tenant_id'] = project_id
        query = {'tenant_id': project_id, 'name': scope['name']}
        result = neutron.list_address_scopes(retrieve_all=True,
                                            **query)
        resource = None
        if not result or not result['address_scopes']:
            logging.info(f"create address-scope {project_name}/{scope['name']}")
            self.diffs[scope['name']].append('create')
            if not self.dry_run:
                result = neutron.create_address_scope(body)
                resource = result['address_scope']
        else:
            resource = result['address_scopes'][0]
            diff = DeepDiff(resource, scope)
            if 'values_changed' in diff:
                self.diffs[scope['name']].append(diff['values_changed'])
                logging.info(f"address-scope {project_name}/{scope['name']} differs.")
                # drop read-only attributes
                body['address_scope'].pop('tenant_id', None)
                body['address_scope'].pop('ip_version', None)
                if not self.dry_run:
                    neutron.update_address_scope(resource['id'],
                                                body)

        if subnet_pools and resource:
            self.diffs[scope['name'] + "_subnetpools"] = {}
            pools = Subnet_Pools(self.args, self.dry_run)
            for subnet_pool in subnet_pools:
                subnet_pool['project'] = project_name
                subnet_pool['domain'] = domain_name
                subnet_pool['address_scope_id'] = resource['id']
            self.diffs[scope['name'] + "_subnetpools"] = pools.seed(subnet_pools)