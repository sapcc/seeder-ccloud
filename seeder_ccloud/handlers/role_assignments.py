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
from keystoneclient import exceptions
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.role_assignments')
def validate_role_assignments(spec, dryrun, **_):
    role_assignments = spec.get('role_assignments', [])
    for assignment in role_assignments:
        if not 'role' in assignment:
            raise kopf.AdmissionError("role name is mandatory")

        if any (k in assignment and '@' not in assignment[k] for k in ('user', 'group', 'project')):
            raise kopf.AdmissionError('group, user and project need the following format: [user,group,project]@domain')
        
        if 'system' in assignment:
            if assignment['system'] != 'all':
                raise kopf.AdmissionError('for system only "all" is allowed')
            if any (k in assignment for k in ('project', 'domain')):
                raise kopf.AdmissionError("with system: project or domain are not allowed")
        
        if all (k in assignment for k in ("group", "user")):
            raise kopf.AdmissionError("setting group and user at the same time is allowed")
        
        if all (k in assignment for k in ('domain', 'project')):
            raise kopf.AdmissionError("setting project and domain at the same time is not allowed")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.role_assignments')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.role_assignments')
def seed_role_assignments_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} role_assignments'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Role_Assignments(memo['args']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Role_Assignments():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, role_assignments):
        for role_assignment in role_assignments:
            self._seed_role_assignments(role_assignment)


    def _seed_role_assignments(self, assignment):
        logging.debug("resolving role assignment %s" % assignment)
        keystone = self.openstack.get_keystoneclient()
        role_assignment = dict()
        role = assignment.pop('role')
        role_id = self.openstack.get_role_id(role)
        if 'user' in assignment:
            user, domain = assignment['user'].split('@')
            id = self.openstack.get_user_id(domain, user)
            if not id:
                raise Exception(
                    "user %s not found, skipping role assignment.." %
                    assignment['user'])
            role_assignment['user'] = id
        elif 'group' in assignment:
            group, domain = assignment['group'].split('@')
            id = self.openstack.get_group_id(domain, group)
            if not id:
                raise Exception(
                    "group %s not found, skipping role assignment.." %
                    assignment['group'])
            role_assignment['group'] = id
        if 'system' in assignment:
            role_assignment['system'] = assignment['system']
        else:
            if 'domain' in assignment:
                id = self.openstack.get_domain_id(assignment['domain'])
                if not id:
                    raise Exception(
                        "domain %s not found, skipping role assignment.." %
                        assignment['domain'])
                role_assignment['domain'] = id
            if 'project' in assignment:
                project, domain = assignment['project'].split('@')
                id = self.openstack.get_project_id(domain, project)
                if not id:
                    raise Exception(
                        "project %s not found, skipping role assignment.." %
                        assignment['project'])
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
            if not self.dry_run:
                keystone.roles.grant(role_id, **role_assignment)