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

import copy, sys, os
import difflib
import pprint
import json
from configparser import ConfigParser
import argparse
from keystoneauth1.loading import cli


class Config:
    _singleton = None
    crd_info = None
    prefix = None
    args = None
    operator_version = None

    def __new__(cls):
        if not cls._singleton:
            cls._singleton = super(Config, cls).__new__(cls)
            
            config = ConfigParser()
            cls.args = cls.get_args(cls)
            config.read(cls.args.config_file)
            
            cls.prefix = 'seeder.ccloud'
            cls.operator_version = config.get('operator', 'version')
            cls.crd_info = {
                'version': config.get('crd_names', 'version'),
                'group': config.get('crd_names', 'group'),
                'kind': config.get('crd_names', 'kind'),
                'plural': config.get('crd_names', 'plural'),
            }
        return cls._singleton

    def get_args(self):
        if self.args is not None:
            return self.args
        parser = argparse.ArgumentParser()
        parser.add_argument('--config-file',
                            help='operator config file path', default='./etc/config.ini', dest='config_file')
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
        parser.add_argument('--max-workers', default=1, dest="max_workers",
                            help='Max workers for the kopf operator.')
        parser.add_argument("--namespace-patterns", dest="namespaces",
                            help="list of namespace patterns. default is cluster wide",
                            default='')
        cli.register_argparse_arguments(parser, sys.argv[1:])
        self.args = parser.parse_args()
        return self.args

    def is_dependency_successful(self, annotations):
        dep = annotations.get(self.prefix + '/check_dependencies', None)

        if dep is None:
            return True
            
        depStatus = json.loads(dep)
        if not depStatus['success']:
            return False

        return True


# https://github.com/python/cpython/blob/3.8/Lib/unittest/case.py#L1201
def get_dict_diff(d1, d2):
    return ('\n' + '\n'.join(difflib.ndiff(
                   pprint.pformat(d1).splitlines(),
                   pprint.pformat(d2).splitlines())))


def diff_exclude_password_callback(obj, path):
    return True if "password" in path else False


def sanitize_dict(source, keys):
    result = {}
    for attr in keys:
        if attr in source:
            if isinstance(source[attr], str):
                result[attr] = source[attr].strip()
            else:
                result[attr] = source[attr]
    return result


def get_changed_seeds(old, new):
    new_copy = copy.deepcopy(new)
    old_copy = copy.deepcopy(old)
    changed = []
    if old is None:
        changed = new_copy
    else:
        changed = [i for i in new_copy if i not in old_copy]
    
    return changed