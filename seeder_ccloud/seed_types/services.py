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
import logging, kopf
from seeder_operator import OPERATOR_ANNOTATION, SEED_CRD
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils
from urllib.parse import urlparse
from deepdiff import DeepDiff


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.services')
def validate(spec, dryrun, **_):
    services = spec.get('services', [])
    for service in services:
        if 'name' not in service or not service['name']:
            raise kopf.AdmissionError("Service must have a name if present..")
        if 'type' not in service or not service['type']:
            raise kopf.AdmissionError("Service must have a type if present..")
        endpoints = service.get('endpoints', [])
        for endpoint in endpoints:
            if 'interface' not in endpoint or not endpoint['interface']:
                raise kopf.AdmissionError("Endpoints must have an interface if present..")
            if 'url' not in endpoint or not endpoint['url']:
                raise kopf.AdmissionError("Endpoints must have a url if present..")
            if 'region' not in endpoint or not endpoint['region']:
                raise kopf.AdmissionError("Endpoints must have a region if present..")
            try:
                parsed = urlparse(endpoint['url'])
                if not parsed.scheme or not parsed.netloc:
                    raise kopf.AdmissionError("Endpoint url must be vaild if present..")
            except Exception:
                raise kopf.AdmissionError("Endpoint url must be vaild if present..")
            if 'region' in endpoint:
                region = endpoint['region']
                if not region or not region.strip():
                    raise kopf.AdmissionError("Endpoint region must be vaild if present..")


class Services(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.services')
    @kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.services')
    def seed_services_handler(memo: kopf.Memo, new, old, name, annotations, **_):
        logging.info('seeding {} services'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
        
        new_copy = copy.deepcopy(new)
        old_copy = copy.deepcopy(old)
        try:
            changed = []
            if old is None:
                changed = new_copy
            else:
                for index, domain in enumerate(new_copy):
                    try:
                        if domain != old_copy[index]:
                            changed.append((old_copy[index], domain))
                    except IndexError:
                        changed.append((None,domain))
                memo['seeder'].all_seedtypes['services'].seed(changed)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


    def seed(self, services):
        logging.info('seeding services')
        for service in services:
            self._seed_service(service)


    def _seed_service(self, service_tuple):
        """ seed a keystone service """
        old_service = service_tuple[0]
        new_service = service_tuple[1]
        logging.debug("seeding service %s" % new_service)
        endpoints = utils.get_changed_sub_seeds(old_service, new_service, 'endpoints')

        service = self.openstack.sanitize(new_service,
                        ('type', 'name', 'enabled', 'description'))
        result = self.openstack.get_keystoneclient().services.list(name=service['name'],
                                        type=service['type'])
        if not result:
            logging.info(
                "create service '%s/%s'" % (
                    service['name'], service['type']))
            if not self.dry_run:
                resource = self.openstack.get_keystoneclient().services.create(**service)
        else:
            resource = result[0]
            diff = DeepDiff(service, resource.to_dict())
            if 'values_changed' in diff:
                logging.debug("endpoint %s differs: '%s'" % (service['name'], diff))
                if not self.dry_run:
                    self.openstack.get_keystoneclient().services.update(resource.id, **service)

        if endpoints:
            self.seed_endpoints(resource, endpoints)


    def seed_endpoints(self, service, endpoints):
        """ seed a keystone service endpoints """
        logging.debug("seeding endpoints %s %s" % (service.name, endpoints))

        for endpoint in endpoints:
            endpoint = self.openstack.sanitize(endpoint, (
                'interface', 'region', 'url', 'enabled', 'name'))

            region = endpoint.get('region', None)
            result = self.openstack.get_keystoneclient().endpoints.list(service=service.id,
                                            interface=endpoint[
                                                'interface'],
                                            region_id=region)
            if not result:
                logging.info("create endpoint '%s/%s'" % (
                    service.name, endpoint['interface']))
                self.openstack.get_keystoneclient().endpoints.create(service.id, **endpoint)
            else:
                resource = result[0]
                diff = DeepDiff(resource, endpoint)
                if len(diff.keys()) > 0:
                    logging.debug("endpoint %s differs: '%s'" % (endpoint['interface'], diff))
                    if not self.dry_run:
                        self.openstack.get_keystoneclient().endpoints.update(resource.id, **endpoint)