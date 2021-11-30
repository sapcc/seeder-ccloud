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
from seeder.openstack.domain.groups import Groups
from seeder.openstack.domain.projects import Projects
from seeder.openstack.domain.role_assignments import Role_Assignments
from seeder.openstack.domain.users import Users

from seeder.openstack.openstack_helper import OpenstackHelper
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass


class Domains(BaseRegisteredSeedTypeClass):
    def __init__(self, args):
        self.opentack = OpenstackHelper(args)
        self.assignment = Role_Assignments(args)
        self.args = args
   
    def seed(self, domains, seeder):
        self.role_assignments = []
        for domain in domains:
            self._seed_domain(domain, seeder)

        self.assignment.seed(self.role_assignments)


    def _seed_domain(self, domain, seeder):
        logging.debug("seeding domain %s" % domain)

        # grab a keystone client
        keystone = self.opentack.get_keystoneclient()

        users = None
        if 'users' in domain:
            users = domain.pop('users', None)
        groups = None
        if 'groups' in domain:
            groups = domain.pop('groups', None)
        projects = None
        if 'projects' in domain:
            projects = domain.pop('projects', None)
        driver = None
        if 'config' in domain:
            driver = domain.pop('config', None)
        roles = None
        if 'roles' in domain:
            roles = domain.pop('roles', None)
        ra = None
        if 'role_assignments' in domain:
            ra = domain.pop('role_assignments', None)

        domain = self.opentack.sanitize(domain, ('name', 'description', 'enabled'))

        if 'name' not in domain or not domain['name']:
            logging.warn(
                "skipping domain '%s', since it is misconfigured" % domain)
            return

        result = keystone.domains.list(name=domain['name'])
        if not result:
            logging.info("create domain '%s'" % domain['name'])
            resource = keystone.domains.create(**domain)
        else:
            resource = result[0]
            for attr in list(domain.keys()):
                if domain[attr] != resource._info.get(attr, ''):
                    logging.info(
                        "%s differs. update domain '%s'" % (
                            attr, domain['name']))
                    keystone.domains.update(resource.id, **domain)
                    break

        # cache the domain id
        #if resource.name not in domain_cache:
        #   domain_cache[resource.name] = resource.id

        if driver:
            self._seed_domain_config(resource, driver)
        if projects:
            pr = Projects(self.args)
            role_assignments = pr.seed(resource, projects)
            self.role_assignments.append(role_assignments)
        if users:
            usr = Users(self.args)
            role_assignments = usr.seed(resource, users)
            self.role_assignments.append(role_assignments)
        if groups:
            gr = Groups(self.args)
            role_assignments = gr.seed(resource, groups)
            self.role_assignments.append(role_assignments)
        if roles:
            for role in roles:
                role['domainId'] = resource.id
                seeder.all_seedtypes['roles'].seed([role])
        if ra:
            for role in ra:
                assignment = dict()
                assignment['role'] = role['role']
                assignment['domain'] = domain['name']
                if 'user' in role:
                    if '@' in role['user']:
                        assignment['user'] = role['user']
                    else:
                        assignment['user'] = '%s@%s' % (
                            role['user'], domain['name'])
                elif 'group' in role:
                    if '@' in role['group']:
                        assignment['group'] = role['group']
                    else:
                        assignment['group'] = '%s@%s' % (
                            role['group'], domain['name'])
                if 'inherited' in role:
                    assignment['inherited'] = role['inherited']
                self.role_assignments.append(assignment)


    def _seed_domain_config(self, domain, driver):
        logging.debug(
            "seeding domain config %s %s" % (domain.name, self.openstack.redact(driver)))

        keystone = self.openstack.get_keystoneclient()
        # get the current domain configuration
        try:
            result = keystone.domain_configs.get(domain)
            if not self._domain_config_equal(driver, result.to_dict()):
                logging.info('updating domain config %s' % domain.name)
                keystone.domain_configs.update(domain, driver)
        except exceptions.NotFound:
            logging.info('creating domain config %s' % domain.name)
            keystone.domain_configs.create(domain, driver)
        except Exception as e:
            logging.error(
                'could not configure domain %s: %s' % (domain.name, e))

    def _domain_config_equal(self, new, current):
        """
        compares domain configurations (and ignores passwords in the comparison)
        :param new:
        :param current:
        :return:
        """
        for key, value in list(new.items()):
            if key in current:
                if isinstance(value, dict):
                    if not self._domain_config_equal(value, current[key]):
                        return False
                elif new[key] != current[key]:
                    return False
            elif 'password' in key:
                continue  # ignore, since it is supressed during config get
            else:
                return False
        return True