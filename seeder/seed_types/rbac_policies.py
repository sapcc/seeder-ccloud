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
import re

from seeder.openstack.openstack_helper import OpenstackHelper
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass

from keystoneclient import exceptions


class Rbac_Policies(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    def seed(self, rbac_policies, seeder):
        for rbac_policy in rbac_policies:
            self._seed_rbac_policy(rbac_policy)


    def _seed_rbac_policy(self, rbac):
        """ seed a neutron rbac-policy """

        object_name_regex = r"^([^@]+)@([^@]+)@([^@]+)$"
        target_name_regex = r"^([^@]+)@([^@]+)$"

        logging.debug("seeding rbac-policy %s" % rbac)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        rbac = self.openstack.sanitize(rbac, ('object_type', 'object_name', 'object_id', 'action', 'target_tenant_name', 'target_tenant'))

        try:
            if 'object_type' not in rbac or not rbac['object_type'] or rbac['object_type'] != 'network':
                logging.warn("skipping rbac-policy '%s', since object_type is missing" % rbac)
                return
            if 'object_name' not in rbac or not rbac['object_name']:
                logging.warn("skipping rbac-policy '%s', since object_name is missing" % rbac)
                return
            # network@project@domain ?
            network_id = None
            match = re.match(object_name_regex, rbac['object_name'])
            if match:
                project_id = self.openstack.get_project_id(match.group(3), match.group(2))
                if project_id:
                    network_id = self.openstack.get_network_id(project_id, match.group(1))
            if not network_id:
                logging.warn("skipping rbac-policy '%s': could not locate object_name" % rbac)
                return
            rbac['object_id'] = network_id
            rbac.pop('object_name', None)

            if 'target_tenant_name' not in rbac or not rbac['target_tenant_name']:
                logging.warn("skipping rbac-policy '%s', since target_tenant_name is missing" % rbac)
                return
            # project@domain ?
            project_id = None
            match = re.match(target_name_regex, rbac['target_tenant_name'])
            if match:
                project_id = self.openstack.get_project_id(match.group(2), match.group(1))
            if not project_id:
                logging.warn("skipping rbac-policy '%s': could not locate target_tenant_name" % rbac)
                return
            rbac['target_tenant'] = project_id
            rbac.pop('target_tenant_name', None)

            try:
                query = {'object_id': rbac['object_id'], 'object_type': rbac['object_type'], 'action': rbac['action'],
                        'target_tenant': rbac['target_tenant']}
                result = neutron.list_rbac_policies(retrieve_all=True, **query)
            except exceptions.NotFound:
                result = None

            if not result or not result['rbac_policies']:
                body = {'rbac_policy': rbac.copy()}

                logging.info("create rbac-policy '%s'" % rbac)
                if not self.dry_run:
                    neutron.create_rbac_policy(body=body)

        except Exception as e:
            logging.error("could not seed rbac-policy %s: %s" % (rbac, e))
            raise