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
from keystoneclient import exceptions
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


class Groups():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, domain, groups):
        self.role_assignments = []
        self.group_members = {}
        for group in groups:
            self._seed_groups(domain, group)
        
        return self.role_assignments


    def _seed_groups(self, domain, group):
        """ seed keystone groups """
        logging.debug("seeding groups %s %s" % (domain.name, group))

        keystone = self.openstack.get_keystoneclient()

        users = None
        if 'users' in group:
            users = group.pop('users')
        ra = None
        if 'role_assignments' in group:
            ra = group.pop('role_assignments')

        group = self.openstack.sanitize(group, ('name', 'description'))
        result = keystone.groups.list(domain=domain.id,
                                    name=group['name'])
        if not result:
            logging.info(
                "create group '%s/%s'" % (domain.name, group['name']))
            if not self.dry_run:
                resource = keystone.groups.create(domain=domain, **group)
        else:
            resource = result[0]
            diff = DeepDiff(group, resource.to_dict())
            if 'values_changed' in diff:
                logging.debug("group %s differs: '%s'" % (group['name'], diff))
                if not self.dry_run:
                    keystone.groups.update(resource.id, **group)

        # cache the group id
        #if domain.name not in group_cache:
        #    group_cache[domain.name] = {}
        #group_cache[domain.name][resource.name] = resource.id
        if users:
            for user in users:
                if resource.id not in self.group_members:
                    self.group_members[resource.id] = []
                if '@' in user:
                    self.group_members[resource.id].append(user)
                else:
                    self.group_members[resource.id].append(
                        '%s@%s' % (user, domain.name))

        # add the groups role assignments to the list to be resolved later on
        if ra:
            for role in ra:
                assignment = dict()
                assignment['role'] = role['role']
                assignment['group'] = '%s@%s' % (group['name'], domain.name)
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