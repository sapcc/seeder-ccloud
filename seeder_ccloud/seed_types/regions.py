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
import kopf, logging
from seeder_operator import OPERATOR_ANNOTATION, SEED_CRD
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils

from deepdiff import DeepDiff


class Regions(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.regions')
    @kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.regions')
    def seed_domains_handler(memo: kopf.Memo, old, new, spec, name, annotations, **kwargs):
        logging.info('seeding {} regions'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
        try:
            memo['seeder'].all_seedtypes['regions'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


    def seed(self, regions):
        logging.info('seeding regions')
        # seed parent regions
        for region in regions:
            if 'parent_region' not in region:
                self._seed_region(region)
        # seed child regions
        for region in regions:
            if 'parent_region' in region:
                self._seed_region(region)


    def _seed_region(self, region):
        """ seed a keystone region """
        logging.debug("seeding region %s" % region)

        region = self.openstack.sanitize(region,
                        ('id', 'description', 'parent_region'))
        if 'id' not in region or not region['id']:
            logging.warn(
                "skipping region '%s', since it is misconfigured" % region)
            return

        try:
            result = self.openstack.get_keystoneclient().regions.get(region['id'])
        except self.openstack.get_keystoneclient().exception.NotFound:
            result = None

        if not result:
            logging.info("create region '%s'" % region['id'])
            if not self.dry_run:
                self.openstack.get_keystoneclient().regions.create(**region)
        else:  # wtf: why can't they deal with parent_region(_id) consistently
            wtf = region.copy()
            if 'parent_region' in wtf:
                wtf['parent_region_id'] = wtf.pop('parent_region')

            diff = DeepDiff(result, wtf)
            if len(diff.keys()) > 0:
                logging.debug("region %s differs: '%s'" % (region['name'], diff))
                if not self.dry_run:
                    self.openstack.get_keystoneclient().regions.update(result.id, **region)