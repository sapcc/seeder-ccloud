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
from deepdiff import DeepDiff
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_operator import SEED_CRD, OPERATOR_ANNOTATION


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.users')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.users')
def seed_domain_users_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} flavor'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        u = Users(memo['args'])
        u.seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Users():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, users):
        for user in users:
            self._seed_user(user)


    def _seed_user(self, user):
        """ seed keystone users and their role-assignments """
        logging.debug("seeding user %s" % (user))

        keystone = self.openstack.get_keystoneclient()

        if '@' in user['name']:
            user, domain_name = user['name'].split('@')
            user['name'] = user
            # throws exception when domain does not exist
            domain_id = self.openstack.get_domain_id(domain_name)
        else:
            domain_name = user['domain']
            domain_id = self.openstack.get_domain_id(domain_name)

        user = self.openstack.sanitize(user, (
            'name', 'email', 'description', 'password', 'enabled',
            'default_project'))

        result = keystone.users.list(domain=domain_id,
                                    name=user['name'])
        if not result:
            logging.info(
                "create user '%s/%s'" % (domain_name, user['name']))
            if not self.dry_run:
                resource = keystone.users.create(domain=domain_id, **user)
        else:
            resource = result[0]
            # no need to diff, since we only work on the users that
            # changed in kubernetes. Will leave it for logging reasons
            diff = DeepDiff(user, resource.to_dict(), exclude_obj_callback=utils.diff_exclude_password_callback)
            if 'values_changed' in diff:
                logging.debug("user %s differs: '%s'" % (user['name'], diff))

            if not self.dry_run:
                keystone.users.update(resource.id, **user)