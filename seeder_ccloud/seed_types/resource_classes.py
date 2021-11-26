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
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

from osc_placement.resources.resource_class import PER_CLASS_URL


class Resource_Classes(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)
   
    def seed(self, resource_classes):
        logging.info('seeding resource_classes')
        for resource_class in resource_classes:
                self._seed_resource_class(resource_class)


    def _seed_resource_class(self, resource_class):
        logging.debug("seeding resource-class %s" % resource_class)
        try:
            # api_version=1.7 -> idempotent resource class creation
            if not self.dry_run:
                _ = self.openstack.get_placementclient(api_version='1.7').request('PUT', PER_CLASS_URL.format(name=resource_class))
        except Exception as e:
            logging.error("Failed to seed resource-class %s: %s" % (resource_class, e))