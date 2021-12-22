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
from seeder_ccloud.openstack.domain.groups import Groups
from seeder_ccloud.openstack.domain.projects import Projects
from seeder_ccloud.openstack.domain.role_assignments import Role_Assignments
from seeder_ccloud.openstack.domain.users import Users

from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass

from deepdiff import DeepDiff
from keystoneclient import exceptions


class Domains(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(args)

    @staticmethod
    @kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.domains')
    @kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.domains')
    def seed_domains_handler(memo: kopf.Memo, old, new, spec, name, annotations, **kwargs):
        logging.info('seeding {} domains'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
        try:
            memo['seeder'].all_seedtypes['domains'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)

   
    def seed(self, domains):
        assignment = Role_Assignments(self.args)
        self.role_assignments = []
        for domain in domains:
            self._seed_domain(domain)

        assignment.seed(self.role_assignments)


    def _seed_domain(self, domain):
        logging.debug("seeding domain %s" % domain)

        # grab a keystone client
        keystone = self.openstack.get_keystoneclient()

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

        domain = self.openstack.sanitize(domain, ('name', 'description', 'enabled'))

        if 'name' not in domain or not domain['name']:
            logging.warn(
                "skipping domain '%s', since it is misconfigured" % domain)
            return

        result = keystone.domains.list(name=domain['name'])
        if not result:
            if not self.dry_run:
                logging.debug("create domain '%s'" % domain['name'])
                resource = keystone.domains.create(**domain)
        else:
            resource = result[0]
            diff = DeepDiff(resource, domain)
            if len(diff.keys()) > 0:
                if not self.dry_run:
                #if not self._domain_config_equal(driver, result.to_dict()):
                    logging.debug("domain %s differs: '%s'" % (domain['name'], diff))
                    keystone.domains.update(resource.id, **domain)

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
                self.seeder.all_seedtypes['roles'].seed([role])
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
            diff = DeepDiff(result, driver, exclude_obj_callback=utils.diff_exclude_password_callback)
            if len(diff.keys()) > 0:
                if not self.dry_run:
                #if not self._domain_config_equal(driver, result.to_dict()):
                    logging.debug("domain %s differs: '%s'" % (domain['name'], diff))
                    keystone.domain_configs.update(domain, driver)
        except exceptions.NotFound:
             if not self.dry_run:
                logging.debug('creating domain config %s' % domain.name)
                keystone.domain_configs.create(domain, driver)
        except Exception as e:
            logging.error(
                'could not configure domain %s: %s' % (domain.name, e))