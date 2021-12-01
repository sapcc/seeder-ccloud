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

from novaclient import exceptions as novaexceptions
from keystoneclient import exceptions

from seeder.openstack.openstack_helper import OpenstackHelper
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass


class Role_Inferences(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)
   
    def seed(self, role_inferences, seeder):
        for role_inference in role_inferences:
            self._seed_role_inference(role_inference)

    def _seed_role_inference(self, role_inference):
        """ seed a keystone role inference """
        logging.debug("seeding role-inference %s" % role_inference)

        # todo: role.domainId ? just for global roles?

        role_inference = self.openstack.sanitize(role_inference, ('prior_role', 'implied_role'))

        # resolve role-id's
        prior_role_id = self.openstack.get_role_id(role_inference['prior_role'])
        if not prior_role_id:
            logging.warn(
                "skipping role-inference '%s', since its prior_role is unknown" % role_inference)
            return
        implied_role_id = self.openstack.get_role_id(role_inference['implied_role'])
        if not implied_role_id:
            logging.warn(
                "skipping role-inference '%s', since its implied_role is unknown" % role_inference)
            return

        try:
            self.openstack.get_keystoneclient().inference_rules.get(prior_role_id, implied_role_id)
        except exceptions.NotFound:
            logging.info("create role-inference '%s'" % role_inference)
            if not self.dry_run:
                self.openstack.get_keystoneclient().inference_rules.create(prior_role_id, implied_role_id)