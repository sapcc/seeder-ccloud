"""
 Copyright 2022 SAP SE
 
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
from seeder_operator import SEED_CRD, OPERATOR_ANNOTATION


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.endpoints')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.endpoints')
def seed_endpoints_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} endpoints'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        e = Endpoints(memo['args'])
        e.seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Endpoints():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, endpoints):
        for endpoint in endpoints:
            self._seed_endpoint(endpoint)


    def _seed_endpoint(self, endpoint):
        """ seed a keystone projects endpoints (OS-EP-FILTER)"""
        logging.debug(
            "seeding project endpoint %s %s" % (endpoint.name, endpoint))

        project_name = endpoint['project']
        project_id = self.openstack.get_project_id(endpoint['domain'], project_name)
        keystone = self.openstack.get_keystoneclient()

        if 'endpoint_id' in endpoint:
            try:
                ep = keystone.endpoints.find(id=endpoint['endpoint_id'])
                try:
                    keystone.endpoint_filter.check_endpoint_in_project(
                        project_id,
                        ep)
                except exceptions.NotFound:
                    logging.info(
                        "add project endpoint '%s %s'" % (
                            project_name, ep))
                    keystone.endpoint_filter.add_endpoint_to_project(
                        project_id,
                        ep)
            except exceptions.NotFound as e:
                raise Exception(
                    'could not configure project endpoints for %s: endpoint %s not found: %s' % (
                        project_name, endpoint, e))
        else:
            try:
                svc = keystone.services.find(name=endpoint['service'])
                result = keystone.endpoints.list(service=svc.id,
                                                region_id=endpoint[
                                                    'region'])
                for ep in result:
                    try:
                        keystone.endpoint_filter.check_endpoint_in_project(
                            project_id, ep)
                    except exceptions.NotFound:
                        logging.info(
                            "add project endpoint '%s %s'" % (
                                project_name, ep))
                        keystone.endpoint_filter.add_endpoint_to_project(
                            project_id,
                            ep)
                    except Exception as e:
                        raise Exception(
                            'could not configure project endpoints for %s: endpoint %s not found: %s' % (
                                project_name, ep, e))
            except exceptions.NotFound as e:
                raise Exception(
                    'could not configure project endpoints for %s: service %s not found: %s' % (
                        project_name, endpoint, e))