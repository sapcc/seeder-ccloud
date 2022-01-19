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

import copy
import difflib
import pprint
import kopf
import json
from seeder_ccloud.seeder_operator import PREFIX


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


def is_dependency_successful(annotations):
    dep = annotations.get(PREFIX + '/check_dependencies', None)

    if dep is None:
        return True
        
    depStatus = json.loads(dep)
    if not depStatus['success']:
        return False

    return True


def get_changed_seeds(old, new):
    new_copy = copy.deepcopy(new)
    old_copy = copy.deepcopy(old)
    changed = []
    if old is None:
        changed = new_copy
    else:
        changed = [i for i in new_copy if i not in old_copy]
    
    return changed


def get_changed_sub_seeds(old, new, key):
    """
    compares the values from the key and returns a list of
    changed values
    """
    new = new.pop(key, [])
    old = old.pop(key, [])
    return [i for i in new if i not in old]