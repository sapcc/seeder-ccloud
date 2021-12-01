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

class Users(args):
    def __init__(self, args):
        self.openstack = OpenstackHelper(args)

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

            if 'name' not in user or not user['name']:
                logging.warn(
                    "skipping user '%s/%s', since it is misconfigured" % (
                        domain.name, self.openstack.redact(user)))
                return

            result = keystone.users.list(domain=domain.id,
                                        name=user['name'])
            if not result:
                logging.info(
                    "create user '%s/%s'" % (domain.name, user['name']))
                resource = keystone.users.create(domain=domain, **user)
            else:
                resource = result[0]
                for attr in list(user.keys()):
                    if attr == 'password':
                        continue
                    if user[attr] != resource._info.get(attr, ''):
                        logging.info(
                            "%s differs. update user '%s/%s' (%s)" % (
                                attr, domain.name, user['name'], attr))
                        keystone.users.update(resource.id, **user)
                        break
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