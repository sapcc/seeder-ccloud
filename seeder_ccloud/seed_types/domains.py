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
from functools import cmp_to_key
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


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.domains')
def validate(spec, dryrun, **_):
    domains = spec.get('domains', [])
    for domain in domains:
        if 'name' not in domain or not domain['name']:
            raise kopf.AdmissionError("Domains must have a name if present..")
        groups = domain.get('groups', [])
        for group in groups:
            if 'name' not in group or not group['name']:
                raise kopf.AdmissionError("Groups must have a name if present..")
        users = domain.get('users', [])
        for user in users:
            if 'name' not in user or not user['name']:
                raise kopf.AdmissionError("Users must have a name if present..")
        projects = domain.get('projects', [])
        for project in projects:
            if 'name' not in project or not project['name']:
                raise kopf.AdmissionError("Projects must have a name if present..")
            networks = project.get('networks', [])
            for network in networks:
                if 'name' not in network or not network['name']:
                    raise kopf.AdmissionError("Networks must have a name if present..")
                tags = network.get('tags', [])
                for tag in tags:
                    if not tag or len(tag) > 60:
                        raise kopf.AdmissionError("Tags size must not be > 60 if present..")



class Domains(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(args)


    @staticmethod
    @kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.domains')
    @kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.domains')
    def seed_domains_handler(memo: kopf.Memo, new, old, name, annotations, **_):
        logging.info('seeding {} == > domains'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
        domains = []
        # we cannot alter the lists from the operator
        new_copy = copy.deepcopy(new)
        old_copy = copy.deepcopy(old)
        if old is None:
            domains = new_copy
        else:
            for index, domain in enumerate(new_copy):
                try:
                    if domain != old_copy[index]:
                        domains.append((old_copy[index], domain))
                except IndexError:
                    domains.append((None,domain))
        try:
            memo['seeder'].all_seedtypes['domains'].seed(domains)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
        logging.info('DONE seeding {} == > domains'.format(name))
   
    def seed(self, domains):
        assignment = Role_Assignments(self.args, self.dry_run)
        self.role_assignments = []
        for domain in domains:
            self._seed_domain(domain)

        assignment.seed(self.role_assignments)


    def _seed_domain(self, domain_tuple):
        logging.debug('seeding domain {}'.format(domain_tuple[1]['name']))
        old_domain = domain_tuple[0]
        new_domain = domain_tuple[1]

        #get all changed sub_seeds
        users = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'users')
        groups = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'groups')
        projects = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'projects')
        driver = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'config')
        roles = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'roles')
        ra = self.openstack.get_changed_sub_seeds(old_domain, new_domain, 'role_assignments')

        # grab a keystone client
        keystone = self.openstack.get_keystoneclient()
        domain = self.openstack.sanitize(new_domain, ('name', 'description', 'enabled'))

        result = keystone.domains.list(name=domain['name'])
        if not result:
            if not self.dry_run:
                logging.debug("create domain '%s'" % domain['name'])
                resource = keystone.domains.create(**domain)
        else:
            resource = result[0]
            diff = DeepDiff(domain, resource.to_dict())
            if 'values_changed' in diff:
                if not self.dry_run:
                    logging.debug("domain %s differs: '%s'" % (domain['name'], diff))
                    keystone.domains.update(resource.id, **domain)

        if driver:
            self._seed_domain_config(resource, driver)
        if projects:
            pr = Projects(self.args, self.dry_run)
            role_assignments = pr.seed(resource, projects)
            self.role_assignments.append(role_assignments)
        if users:
            usr = Users(self.args, self.dry_run)
            role_assignments = usr.seed(resource, users)
            self.role_assignments.append(role_assignments)
        if groups:
            gr = Groups(self.args, self.dry_run)
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


    def _get_sub_seeds(self, old_domain, new_domain, key):
        """
        compares the values from the key and returns a list of
        changed values
        """
        new = new_domain.pop(key, [])
        old = old_domain.pop(key, [])
        return [i for i in new if i not in old]


    def _seed_domain_config(self, domain, driver):
        logging.debug(
            "seeding domain config %s %s" % (domain.name, self.openstack.redact(driver)))

        keystone = self.openstack.get_keystoneclient()
        # get the current domain configuration
        try:
            result = keystone.domain_configs.get(domain)
            diff = DeepDiff(driver, result.to_dict(), exclude_obj_callback=utils.diff_exclude_password_callback)
            if 'values_changed' in diff:
                logging.debug("domain %s differs: '%s'" % (domain['name'], diff))
            if not self.dry_run:
                keystone.domain_configs.update(domain, driver)
        except exceptions.NotFound:
             if not self.dry_run:
                logging.debug('creating domain config %s' % domain.name)
                keystone.domain_configs.create(domain, driver)
        except Exception as e:
            logging.error(
                'could not configure domain %s: %s' % (domain.name, e))