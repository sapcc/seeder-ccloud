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
from deepdiff import DeepDiff
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


class Users():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run

    def seed(self, domain, users):
        self.role_assignments = []
        for user in users:
            self._seed_user(domain, user)

        return self.role_assignments

    def _seed_user(self, domain, user):
        """ seed keystone users and their role-assignments """
        logging.debug("seeding users %s %s" % (domain.name, user))

        keystone = self.openstack.get_keystoneclient()

        ra = None
        if 'role_assignments' in user:
            ra = user.pop('role_assignments')

        if '@' not in user['name']:
            user = self.openstack.sanitize(user, (
                'name', 'email', 'description', 'password', 'enabled',
                'default_project'))

            result = keystone.users.list(domain=domain.id,
                                        name=user['name'])
            if not result:
                logging.info(
                    "create user '%s/%s'" % (domain.name, user['name']))
                if not self.dry_run:
                    resource = keystone.users.create(domain=domain, **user)
            else:
                resource = result[0]
                # no need to diff, since we only work on the users that
                # changed in kubernetes. Will leave it for logging reasons
                diff = DeepDiff(user, resource.to_dict(), exclude_obj_callback=utils.diff_exclude_password_callback)
                if 'values_changed' in diff:
                    logging.debug("user %s differs: '%s'" % (user['name'], diff))

                if not self.dry_run:
                    keystone.users.update(resource.id, **user)

        # add the users role assignments to the list to be resolved later on
        if ra:
            for role in ra:
                assignment = dict()
                assignment['role'] = role['role']
                assignment['user'] = '%s@%s' % (
                    user['name'], domain.name)
                if 'system' in role:
                    assignment['system'] = role['system']
                else:
                    if 'project' in role:
                        if '@' in role['project']:
                            assignment['project'] = role['project']
                        else:
                            assignment['project'] = '%s@%s' % (
                                role['project'], domain.name)
                    elif 'project_id' in role:
                        assignment['project_id'] = role['project_id']
                    elif 'domain' in role:
                        assignment['domain'] = role['domain']
                    if 'inherited' in role:
                        assignment['inherited'] = role['inherited']

                self.role_assignments.append(assignment)