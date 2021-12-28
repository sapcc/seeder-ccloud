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
from seeder_operator import OPERATOR_ANNOTATION, SEED_CRD
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud import utils
from deepdiff import DeepDiff


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.roles')
def validate(spec, dryrun, **_):
    roles = spec.get('roles', [])
    for role in roles:
        if 'name' not in role or not role['name']:
            raise kopf.AdmissionError("Roles must have a name if present..")


class Roles(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.roles')
    @kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.roles')
    def seed_roles_handler(memo: kopf.Memo, new, name, annotations, **_):
        logging.info('seeding {} roles'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

        try:
            memo['seeder'].all_seedtypes['roles'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


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