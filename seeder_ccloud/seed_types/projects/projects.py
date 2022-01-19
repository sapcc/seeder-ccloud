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
from keystoneauth1 import exceptions as keystoneauthexceptions
from designateclient.v2 import client as designateclient
from deepdiff import DeepDiff
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seeder_operator import SEED_CRD, OPERATOR_ANNOTATION


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.projects')
def validate(spec, dryrun, **_):
    projects = spec.get('projects', [])
    for project in projects:
        if 'name' not in project or not project['name']:
            raise kopf.AdmissionError("Projects must have a name if present..")


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.projects')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.projects')
def seed_projects_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} flavor'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Projects(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Projects():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, projects):
        for project in projects:
            self._seed_projects(project)


    def _seed_projects(self, project):
            """
            seed keystone projects and their dependant objects
            """
            domain_name = project['domain']
            domain_id = self.openstack.get_domain_id(domain_name)
            logging.debug("seeding project %s %s" % (domain_name, project))

            keystone = self.openstack.get_keystoneclient()
            
            dns_quota = project.pop('dns_quota', None)
            
            dns_tsig_keys = project.pop('dns_tsigkeys', None)
            
            ec2_creds = project.pop('ec2_creds', None)
            
            flavors = project.pop('flavors', None)

            project = self.openstack.sanitize(project,
                            ('name', 'description', 'enabled', 'parent'))

            # resolve parent project if specified
            if 'parent' in project:
                parent_id = self.openstack.get_project_id(domain_name, project['parent'],
                                        keystone)
                if not parent_id:
                    logging.warn(
                        "skipping project '%s/%s', since its parent project is missing" % (
                            domain_name, project))
                    return
                else:
                    project['parent_id'] = parent_id

            project.pop('parent', None)

            result = keystone.projects.list(domain=domain_id,
                                            name=project['name'])
            if not result:
                logging.info(
                    "create project '%s/%s'" % (
                        domain_name, project['name']))
                if not self.dry_run:
                    resource = keystone.projects.create(domain=domain_id,
                                                    **project)
            else:
                resource = result[0]
                diff = DeepDiff(project, resource.to_dict())
                if 'values_changed' in diff:
                    logging.debug("project %s differs: '%s'" % (project['name'], diff))
                    if not self.dry_run:
                        keystone.projects.update(resource.id, **project)

            # seed designate quota
            if dns_quota:
                limes = keystone.services.list(name='limes')
                # only seed dns quota if limes is not available
                if not len(limes):
                    self.seed_project_designate_quota(resource, dns_quota)

            # seed designate tsig keys
            if dns_tsig_keys:
                self.seed_project_tsig_keys(resource, dns_tsig_keys)

            if ec2_creds:
                self.seed_project_ec2_creds(resource, domain_id, ec2_creds)

            # seed flavors
            if flavors:
                self.seed_project_flavors(resource, flavors)
    

    def seed_project_flavors(self, project, flavors):
        """
        seed a projects compute flavors
        """

        logging.debug("seeding flavors of project %s" % project.name)

        # grab a nova client
        nova = self.openstack.get_novaclient()
        for flavorid in flavors:
            try:
                # validate flavor-id
                nova.flavors.get(flavorid)
                # check if project has access
                access = set([a.tenant_id for a in
                            nova.flavor_access.list(flavor=flavorid)])
                if project.id not in access:
                    # add it
                    logging.info(
                        "adding flavor '%s' access to project '%s" % (flavorid, project.name))
                    nova.flavor_access.add_tenant_access(flavorid, project.id)
            except Exception as e:
                logging.error(
                    "could not add flavor-id '%s' access for project '%s': %s" % (
                        flavorid, project.name, e))
                raise


    def seed_project_designate_quota(self, project, config):
        """
        Seeds designate quota for a project
        :param project:
        :param config:
        :param args:
        :return:
        """

        # seed designate quota
        logging.debug(
            "seeding designate quota for project %s" % project.name)

        try:
            designate = self.openstack.get_designateclient(project.id)

            result = designate.quotas.list(project.id)
            new_quota = {}
            for attr in list(config.keys()):
                if int(config[attr]) > int(result.get(attr, '')):
                    logging.info(
                        "%s differs. set project %s designate quota to '%s'" % (
                            attr, project.name, config))
                    new_quota[attr] = config[attr]
            if len(new_quota) and not self.dry_run:
                designate.quotas.update(project.id, new_quota)

        except Exception as e:
            logging.error(
                "could not seed designate quota for project %s: %s" % (
                    project.name, e))


    def seed_project_tsig_keys(self, project, keys):
        """
        Seed a projects designate tsig keys
        :param project:
        :param keys:
        :return:
        """

        logging.debug("seeding dns tsig keys of project %s" % project.name)

        try:
            designate = self.openstack.get_designateclient(project.id)

            for key in keys:
                key = self.openstack.sanitize(key, (
                    'name', 'algorithm', 'secret', 'scope', 'resource_id'))

                if 'name' not in key or not key['name']:
                    logging.warn(
                        "skipping dns tsig key '%s/%s', since it is misconfigured" % (
                            project.name, key))
                    continue
                try:
                    resource = designate.tsigkeys.get(key['name'])
                    for attr in list(key.keys()):
                        if key[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update dns tsig key '%s/%s'" % (
                                    attr, project.name, key['name']))
                            designate.tsigkeys.update(resource['id'], key)
                            break
                except designateclient.exceptions.NotFound:
                    logging.info(
                        "create dns tsig key '%s/%s'" % (
                            project.name, key['name']))
                    designate.tsigkeys.create(key.pop('name'), **key)

        except Exception as e:
            logging.error("could not seed project dns tsig keys %s: %s" % (
                project.name, e))


    def seed_project_ec2_creds(self, project, domain_name, creds):
        """
        Seed a projects ec2 credentials
        :param user:
        :param access:
        :param key:
        :return:
        """

        logging.debug("seeding ec2 credentials of project %s" % project.name)

        try:
            # grab a keystone client
            keystone = self.openstack.get_keystoneclient()
        except Exception as e:
            logging.error("Couldn't get keystone client")
            return

        for cred in creds:
            cred = self.openstack.sanitize(cred, ('user', 'user_domain', 'access', 'key'))
            project_id = self.openstack.get_project_id(domain_name, project.name)
            user_id = self.openstack.get_user_id(cred['user_domain'], cred['user'])

            if cred.get('access') is None or cred.get('key') is None:
                logging.error(
                    "missing access or key for ec2 credentials"
                )
                return

            try:
                # Check if credential exsist - Update if exists
                keystone.credentials.create(user=user_id, type="ec2", project=project_id,
                                            blob='{"access":"' + cred['access'] +
                                                '", "secret":"' + cred['key'] + '"}')
            except keystoneauthexceptions.http.Conflict as e:
                logging.info("Ec2 credentials already exist")
                return
            except Exception as e:
                logging.error("Could not seed ec2 credentials")
