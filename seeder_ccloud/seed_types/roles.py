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

import logging
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass

from deepdiff import DeepDiff


class Roles(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)

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
            diff = DeepDiff(resource, role)
            if len(diff.keys()) > 0:
                logging.debug("role %s differs: '%s'" % (role['name'], diff))
                if not self.dry_run:
                    self.openstack.get_keystoneclient().roles.update(resource.id, **role)