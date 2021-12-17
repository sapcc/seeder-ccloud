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
# Here we import the seed_types for the SeedTypeRegistry.
# The order of importing => order of execution 
from seeder_ccloud.seed_types.regions import Regions
from seeder_ccloud.seed_types.flavors import Flavors
from seeder_ccloud.seed_types.domains import Domains

from seeder_ccloud.seed_type_registry import SeedTypeRegistryBase


class Seeder:
    def __init__(self, args):
        self.args = args

        self.all_seedtypes = dict()
        for seedtype_name in SeedTypeRegistryBase.SEED_TYPE_REGISTRY:
            seedtype_class = SeedTypeRegistryBase.SEED_TYPE_REGISTRY[seedtype_name]
            seedtype_instance = seedtype_class(self.args, self, self.args.dry_run)
            self.all_seedtypes[seedtype_name] = seedtype_instance


    def seed_spec(self, spec):
        self.spec = spec
        for seedtype_name, seedtype_instance in self.all_seedtypes.items():
            try:
                if seedtype_name in spec:
                    seedtype_instance.seed(spec[seedtype_name])
            except NotImplementedError as e:
                logging.error('seed_type %s: method "seed" not implemented' %seedtype_name)


    def get_spec(self):
        return self.spec