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


class Volume_Types(BaseRegisteredSeedTypeClass):
    def __init__(self, args, spec):
        self.opentack = OpenstackHelper(args)
   
    def seed(self, volume_types, seeder):
        for volume_type in volume_types:
            self._seed_volume_type(volume_type)

    def _seed_volume_type(self, volume_type):
        """seed a cinder volume type"""
        logging.debug("seeding volume-type %s" % volume_type)
        # intialize cinder client
        try:
            cinder = self.openstack.get_cinderclient()
        except Exception as e:
            logging.error("Fail to initialize cinder client: %s" % e)
            raise

        def get_type_by_name(name):
            for t in cinder.volume_types.list(is_public=volume_type['is_public']):
                if t.name == name:
                    return t
            return None

        def update_type(vtype, volume_type):
            logging.debug("updating volume-type '%s'", volume_type['name'])
            cinder.volume_types.update(vtype, volume_type['name'], volume_type['description'], volume_type['is_public'])

        def create_type(volume_type):
            logging.debug("updating volume-type '%s'", volume_type['name'])
            vtype = cinder.volume_types.create(volume_type['name'], volume_type['description'], volume_type['is_public'])
            if 'extra_specs' in volume_type:
                extra_specs = volume_type.pop('extra_specs', None)
                if not isinstance(extra_specs, dict):
                    logging.warn("skipping volume-type '%s', since it has invalid extra_specs" % volume_type)
                else:
                    vtype.set_keys(extra_specs)

        vtype = get_type_by_name(volume_type['name'])
        if vtype:
            try:
                update_type(vtype, volume_type)
            except Exception as e:
                logging.error("Failed to update volume type %s: %s" % (volume_type, e))
                raise
        else:
            try:
                create_type(volume_type)
            except Exception as e:
                logging.error("Failed to create volume type %s: %s" % (volume_type, e))
                raise