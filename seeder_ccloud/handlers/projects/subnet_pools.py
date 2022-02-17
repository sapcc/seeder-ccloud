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
from designateclient.v2 import client as designateclient
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
def validate(spec, dryrun, **_):
    subnet_pools = spec.get('subnet_pools', [])
    for subnet_pool in subnet_pools:
        if 'name' not in subnet_pool or not subnet_pool['name']:
            raise kopf.AdmissionError("subnet_pool must have a name...")
        


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
def seed_subnet_pools_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} subnet_pools'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Subnet_Pools(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Subnet_Pools():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, subnet_pools):
        for subnet_pool in subnet_pools:
            self._seed_subnet_pool(subnet_pool)


    def _seed_subnet_pool(self, subnet_pool):
        project_name = subnet_pool['project']
        project_id = self.openstack.get_project_id(subnet_pool['domain'], project_name)
        logging.debug(
            "seeding subnet-pools of project %s" % project_name)

        neutron = self.openstack.get_neutronclient()
        try:
            subnet_pool = self.openstack.sanitize(subnet_pool, (
                'name', 'default_quota', 'prefixes', 'min_prefixlen',
                'shared',
                'default_prefixlen', 'max_prefixlen', 'description',
                'address_scope_id', 'is_default'))

            body = {'subnetpool': subnet_pool.copy()}
            body['subnetpool']['tenant_id'] = project_id

            query = {'tenant_id': project_id,
                    'name': subnet_pool['name']}
            result = neutron.list_subnetpools(retrieve_all=True,
                                            **query)
            if not result or not result['subnetpools']:
                logging.info(
                    "create subnet-pool '%s/%s'" % (
                        project_name, subnet_pool['name']))
                if not self.dry_run:
                    result = neutron.create_subnetpool(body)
            else:
                resource = result['subnetpools'][0]
                for attr in list(subnet_pool.keys()):
                    if attr == 'prefixes':
                        for prefix in subnet_pool['prefixes']:
                            if prefix not in resource.get('prefixes',
                                                        []):
                                logging.info(
                                    "update subnet-pool prefixes '%s/%s'" % (
                                        project_name,
                                        subnet_pool['name']))
                                # drop read-only attributes
                                body['subnetpool'].pop('tenant_id',
                                                    None)
                                body['subnetpool'].pop('shared', None)
                                if not self.dry_run:
                                    neutron.update_subnetpool(resource['id'], body)
                                break
                    else:
                        # a hacky comparison due to the neutron api not dealing with string/int attributes consistently
                        if str(subnet_pool[attr]) != str(
                                resource.get(attr, '')):
                            logging.info(
                                "%s differs. update subnet-pool'%s/%s'" % (
                                    attr, project_name,
                                    subnet_pool['name']))
                            # drop read-only attributes
                            body['subnetpool'].pop('tenant_id', None)
                            body['subnetpool'].pop('shared', None)
                            if not self.dry_run:
                                neutron.update_subnetpool(resource['id'],
                                                        body)
                            break
        except Exception as e:
            logging.error("could not seed subnet pool %s/%s: %s" % (
                project_name, subnet_pool['name'], e))
            raise