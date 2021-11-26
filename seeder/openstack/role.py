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
from seeder.openstack.openstack_helper import OpenstackHelper
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass


class Role(BaseRegisteredSeedTypeClass):
    def __init__(self, args):
        self.opentack = OpenstackHelper(args)

    def seed(self, spec):
        logging.info('seeding roles')
        if 'roles' in spec:
            for role in spec['roles']:
                if role:
                    self.seed_role(role)

    def seed_role(self, role):
        """ seed a keystone role """
        logging.info("seeding role %s" % role)

        role = self.openstack.sanitize(role, ('name', 'description', 'domainId'))

        # todo: role.domainId ?
        if 'domainId' in role:
            result = self.openstack.get_keystoneclient().roles.list(name=role['name'], domain=role['domainId'])
        else:
            result = self.openstack.get_keystoneclient().roles.list(name=role['name'])
        if not result:
            logging.info("create role '%s'" % role)
            resource = self.openstack.get_keystoneclient().roles.create(**role)
        else:
            resource = result[0]
            for attr in list(role.keys()):
                if role[attr] != resource._info.get(attr, ''):
                    logging.info(
                        "%s differs. update role '%s'" % (attr, role))
                    self.openstack.get_keystoneclient().roles.update(resource.id, **role)
                    break