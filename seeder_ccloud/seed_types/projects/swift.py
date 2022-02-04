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
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from swiftclient import client as swiftclient
from keystoneclient import exceptions

config = utils.Config()

@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.swifts')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.swifts')
def seed_swifts_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} swift containers'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Swift(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Swift():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, swifts):
        for swift in swifts:
            self._seed_swift(swift)
    
    
    def _seed_swift(self, swift):
        """
        Seeds swift account and containers for a project
        :param project:
        :param swift:
        :param args:
        :param sess:
        :return:
        """

        if 'enabled' in swift and swift['enabled']:
            logging.debug(
                "seeding swift account for project %s" % swift['project'])

            try:
                project_id = self.openstack.get_project_id(swift['project'])
                project_name = swift['project']
                session = self.openstack.get_session()
                service_token = session.get_token()

                # poor mans storage-url generation
                try:
                    swift_endpoint = session.get_endpoint(
                        service_type='object-store',
                        interface=self.openstack.args.interface)
                except exceptions.EndpointNotFound:
                    swift_endpoint = session.get_endpoint(
                        service_type='object-store',
                        interface='admin')

                storage_url = swift_endpoint.split('/AUTH_')[
                                0] + '/AUTH_' + project_id

                # Create swiftclient Connection
                conn = swiftclient.Connection(session=session,
                                            preauthurl=storage_url,
                                            preauthtoken=service_token,
                                            insecure=True)
                try:
                    # see if the account already exists
                    conn.head_account()
                except swiftclient.ClientException:
                    # nope, go create it
                    logging.info(
                        'creating swift account for project %s' % project_name)
                    if not self.dry_run:
                        swiftclient.put_object(storage_url, token=service_token)

                # seed swift containers
                if 'containers' in swift:
                    self.seed_swift_containers(project_name, swift['containers'],
                                        conn)

            except Exception as e:
                logging.error(
                    "could not seed swift account for project %s: %s" % (
                        project_name, e))
                raise

    
    def seed_swift_containers(self, project, containers, conn):
        """
        Creates swift containers for a project
        :param project:
        :param containers:
        :param conn:
        :return:
        """

        logging.debug(
            "seeding swift containers for project %s" % project)

        for container in containers:
            try:
                # prepare the container metadata
                headers = {}
                if 'metadata' in container:
                    for meta in list(container['metadata'].keys()):
                        header = 'x-container-%s' % meta
                        headers[header] = str(container['metadata'][meta])
                try:
                    # see if the container already exists
                    result = conn.head_container(container['name'])
                    for header in list(headers.keys()):
                        if headers[header] != result.get(header, ''):
                            logging.info(
                                "%s differs. update container %s/%s" % (
                                    header, project,
                                    container['name']))
                            if not self.dry_run:
                                conn.post_container(container['name'], headers)
                            break
                except swiftclient.ClientException:
                    # nope, go create it
                    logging.info(
                        'creating swift container %s/%s' % (
                            project, container['name']))
                    if not self.dry_run:
                        conn.put_container(container['name'], headers)
            except Exception as e:
                logging.error(
                    "could not seed swift container for project %s: %s" % (
                        project, e))
                raise