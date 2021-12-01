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
import argparse
import sys
# Here we import the seed_types for the SeedTypeRegistry.
# The order of importing => order of execution 
from seeder.seed_types.roles import Roles
from seeder.seed_types.regions import Regions

from seeder.seed_type_registry import SeedTypeRegistryBase
from keystoneauth1.loading import cli


class Seeder:
    def __init__(self):
        self.args = get_args()
        setup_logging(self.args)

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


def setup_logging(args):
    logging.basicConfig(
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        level=getattr(logging, args.logLevel))


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',
                        help='the yaml file with the identity configuration')
    parser.add_argument('--interface',
                        help='the keystone interface-type to use',
                        default='internal',
                        choices=['admin', 'public', 'internal'])
    parser.add_argument('--insecure',
                        help='do not verify SSL certificates',
                        default=False,
                        action='store_true')
    parser.add_argument("-l", "--log", dest="logLevel",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                 'CRITICAL'],
                        help="Set the logging level",
                        default='INFO')
    parser.add_argument('--dry-run', default=False, action='store_true',
                        help='Only parse the seed, do no actual seeding.')
    cli.register_argparse_arguments(parser, sys.argv[1:])
    return parser.parse_args()