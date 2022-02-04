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
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from osc_placement.resources.resource_class import PER_CLASS_URL

config = utils.Config()

@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.resource_classes')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.resource_classes')
def seed_resource_classes_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} resource_classes'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        changed = utils.get_changed_seeds(old, new)
        Resource_Classes(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Resource_Classes():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


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