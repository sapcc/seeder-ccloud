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
from seeder_operator import OPERATOR_ANNOTATION
from seeder_ccloud import utils
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


class Traits(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.traits')
    @kopf.on.create('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.traits')
    def seed_domains_handler(memo: kopf.Memo, old, new, spec, name, annotations, **kwargs):
        logging.info('seeding {} traits'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

        try:
            memo['seeder'].all_seedtypes['traits'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


    def seed(self, traits):
        logging.info('seeding traits')
        for trait in traits:
            self._seed_trait(trait)

    
    def _seed_trait(self, trait):
        try:
            if not self.dry_run:
                self.openstack.get_placementclient().request('PUT', '/traits/{}'.format(trait))
        except Exception as e:
            logging.error("Failed to seed trait %s: %s" % (trait, e))