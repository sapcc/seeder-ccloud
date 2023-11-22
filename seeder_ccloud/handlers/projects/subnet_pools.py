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
from deepdiff import DeepDiff
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
def validate(memo: kopf.Memo, dryrun, spec, old, warnings: List[str], **_):
    subnet_pools = spec['openstack'].get('subnet_pools', [])
    
    for subnet_pool in subnet_pools:
        if 'name' not in subnet_pool or not subnet_pool['name']:
            raise kopf.AdmissionError("subnet_pool must have a name...")

    if dryrun and subnet_pools:
        old_subnet_pools = None
        if old is not None:
            old_subnet_pools = old['spec']['openstack'].get('networks', None)
        try:
            changed = utils.get_changed_seeds(old_subnet_pools, subnet_pools)
            diffs = Subnet_Pools(memo['args'], dryrun).seed(changed)
            if diffs:
                warnings.append({'subnet_pools': diffs})
        except Exception as error:
            raise kopf.AdmissionError(error)     


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.subnet_pools')
def seed_subnet_pools_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.debug(f"seeding {name} subnet_pools")
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError(f"error seeding {name}: dependencies error", delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Subnet_Pools(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError(f"error seeding {name}: {error}", delay=30)


class Subnet_Pools():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, subnet_pools):
        self.diffs = {}
        for subnet_pool in subnet_pools:
            self._seed_subnet_pool(subnet_pool)
        return self.diffs


    def _seed_subnet_pool(self, subnet_pool):
        project_name = subnet_pool['project']
        project_id = self.openstack.get_project_id(subnet_pool['domain'], project_name)
        logging.debug(f"seeding subnet-pool {subnet_pool['name']} of project {project_name}")

        neutron = self.openstack.get_neutronclient()
        tags = subnet_pool.pop('tags', None)
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
        resource = None
        self.diffs[subnet_pool['name']] = []
        if not result or not result['subnetpools']:
            logging.info(f"create subnet-pool {project_name}/{subnet_pool['name']}")
            self.diffs[subnet_pool['name']].append('create')
            if not self.dry_run:
                result = neutron.create_subnetpool(body)
                resource = result['subnetpools'][0]
        else:
            resource = result['subnetpools'][0]
            diff = DeepDiff(resource.get('prefixes', []), subnet_pool.get('prefixes', []))
            if diff:
                self.diffs[subnet_pool['name']].append(f"{list(diff.keys())[0]}: {list(diff.values())[0]}")
                logging.info(f"network {subnet_pool['name']} differs: {diff}")

            for attr in list(subnet_pool.keys()):
                if attr != 'prefixes':
                    # https://github.com/seperman/deepdiff/issues/180
                    # a hacky comparison due to the neutron api not dealing with string/int attributes consistently
                    if str(subnet_pool[attr]) != str(resource.get(attr, '')):
                        logging.info(f"subnet_pool {subnet_pool['name']} differs: {attr}")
                        self.diffs[subnet_pool['name']].append(f"value_changed: {attr}")

            if self.diffs[subnet_pool['name']]:
                if not self.dry_run:
                    # drop read-only attributes
                    body['subnetpool'].pop('tenant_id', None)
                    body['subnetpool'].pop('shared', None)
                    neutron.update_subnetpool(resource['id'], body)
        
        if tags and resource:
            self._seed_subnet_pool_tags(resource, tags)


    def _seed_subnet_pool_tags(self, subnet_pool, tags):
        """
            seed neutron tags of a subnet_pool
            :param network:
            :param tags:
            :param args:
            :param sess:
            :return:
            """

        logging.debug(f"seeding tags of subnet_pool {subnet_pool['name']}")

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        for tag in tags:
            if tag not in subnet_pool['tags']:
                self.diffs[subnet_pool['name']].append(f"create tag: {tag}")
                logging.debug(f"adding tag {tag} to network {subnet_pool['name']}")
                if not self.dry_run:
                    neutron.add_tag('subnetpools', subnet_pool['id'], tag)