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
from seeder_operator import OPERATOR_ANNOTATION, SEED_CRD
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.quota_class_sets')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.quota_class_sets')
def seed_quota_class_sets_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} quota_class_sets'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        changed = utils.get_changed_seeds(old, new)
        Quota_Class_Sets(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Quota_Class_Sets():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


    def seed(self, quota_class_sets):
        for quota_class, quotas in quota_class_sets.items():
            self._seed_quota_class_sets(quota_class, quotas)


    def _seed_quota_class_sets(self, quota_class, quotas):
        # this have been patched into Nova to create custom quotas (flavor based)
        logging.debug("seeding nova quota-class-set %s" % quota_class)

        try:
            if not self.dry_run:
                resp = self.openstack.get_session().post('/os-quota-class-sets/' + quota_class,
                                endpoint_filter={'service_type': 'compute',
                                                'interface': 'public'},
                                json=dict({"quota_class_set": quotas}))
                logging.debug("Create/Update os-quota-class-set : %s" % resp.text)
        except Exception as e:
            logging.error("could not seed quota-class-set %s: %s" % (quota_class, e))
            raise