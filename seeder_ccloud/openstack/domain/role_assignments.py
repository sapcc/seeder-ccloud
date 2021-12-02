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

from keystoneclient import exceptions

from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


class Role_Assignments():
    def __init__(self, args):
        self.openstack = OpenstackHelper(args)
   
    def seed(self, role_assignments):
        for role_assignment in role_assignments:
            self._role_assignments(role_assignment)


    def seed_role_assignments(self, assignment):
        logging.debug("resolving role assignment %s" % assignment)
        keystone = self.opentrack.get_keystoneclient()
        try:
            role_assignment = dict()
            role = assignment.pop('role')
            role_id = self.openstack.get_role_id(role)
            if 'user' in assignment:
                user, domain = assignment['user'].split('@')
                id = self.openstack.get_user_id(domain, user)
                if not id:
                    logging.warn(
                        "user %s not found, skipping role assignment.." %
                        assignment['user'])
                    return
                role_assignment['user'] = id
            elif 'group' in assignment:
                group, domain = assignment['group'].split('@')
                id = self.openstack.get_group_id(domain, group)
                if not id:
                    logging.warn(
                        "group %s not found, skipping role assignment.." %
                        assignment['group'])
                    return
                role_assignment['group'] = id
            if 'system' in assignment:
                role_assignment['system'] = assignment['system']
            else:
                if 'domain' in assignment:
                    id = self.openstack.get_domain_id(assignment['domain'])
                    if not id:
                        logging.warn(
                            "domain %s not found, skipping role assignment.." %
                            assignment['domain'])
                        return
                    role_assignment['domain'] = id
                if 'project' in assignment:
                    project, domain = assignment['project'].split('@')
                    id = self.openstack.get_project_id(domain, project)
                    if not id:
                        logging.warn(
                            "project %s not found, skipping role assignment.." %
                            assignment['project'])
                        return
                    role_assignment['project'] = id
                elif 'project_id' in assignment:
                    role_assignment['project'] = assignment['project_id']

                if 'inherited' in assignment:
                    role_assignment['os_inherit_extension_inherited'] = \
                        assignment['inherited']

            try:
                keystone.roles.check(role_id, **role_assignment)
            except exceptions.NotFound:
                logging.info("grant '%s' to '%s'" % (role, assignment))
                keystone.roles.grant(role_id, **role_assignment)
        except ValueError as e:
            logging.error(
                "skipped role assignment %s since it is invalid: %s" % (
                    assignment, e))