"""
 Copyright 2021 SAP SE
 
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
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils
from deepdiff import DeepDiff

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.roles')
def validate_roles(spec, dryrun, **_):
    roles = spec.get('roles', [])
    for role in roles:
        if 'name' not in role or not role['name']:
            raise kopf.AdmissionError("Roles must have a name if present..")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.roles')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.roles')
def seed_roles_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} roles'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        changed = utils.get_changed_seeds(old, new)
        Roles(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Roles():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


    def seed(self, roles):
        logging.info('seeding roles')
        for role in roles:
            role = self.openstack.sanitize(role, ('name', 'description', 'domainId'))
            self.seed_role(role)


    def seed_role(self, role):
        """ seed a keystone role """
        logging.info("seeding role %s" % role)

        # todo: role.domainId ?
        if 'domainId' in role:
            result = self.openstack.get_keystoneclient().roles.list(name=role['name'], domain=role['domainId'])
        else:
            result = self.openstack.get_keystoneclient().roles.list(name=role['name'])
        if not result:
            logging.info("create role '%s'" % role)
            if not self.dry_run:
                resource = self.openstack.get_keystoneclient().roles.create(**role)
        else:
            resource = result[0]
            diff = DeepDiff(role, resource.to_dict())
            if 'values_changed' in diff:
                logging.debug("role %s differs: '%s'" % (role['name'], diff))
                if not self.dry_run:
                    self.openstack.get_keystoneclient().roles.update(resource.id, **role)