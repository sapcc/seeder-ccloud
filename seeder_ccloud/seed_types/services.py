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
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils
from urllib.parse import urlparse
from deepdiff import DeepDiff

class Services(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update('kopfexamples', annotations={'operatorVersion': 'version2'}, field='spec.services')
    @kopf.on.create('kopfexamples', annotations={'operatorVersion': 'version2'}, field='spec.services')
    def seed_domains_handler(memo: kopf.Memo, old, new, spec, name, annotations, **kwargs):
        logging.info('seeding {} services'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

        try:
            memo['seeder'].all_seedtypes['services'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


    def seed(self, services):
        logging.info('seeding services')
        for service in services:
            self._seed_service(service)


    def _seed_service(self, service):
        """ seed a keystone service """
        logging.debug("seeding service %s" % service)
        endpoints = None
        if 'endpoints' in service:
            endpoints = service.pop('endpoints', None)

        service = self.openstack.sanitize(service,
                        ('type', 'name', 'enabled', 'description'))
        if 'name' not in service or not service['name'] \
                or 'type' not in service or not service['type']:
            logging.warn(
                "skipping service '%s', since it is misconfigured" % service)
            return

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
            diff = DeepDiff(resource, service)
            if len(diff.keys()) > 0:
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
            if 'interface' not in endpoint or not endpoint['interface']:
                logging.warn(
                    "skipping endpoint '%s/%s', since it is misconfigured" % (
                        service['name'], endpoint))
                continue

            if 'url' not in endpoint or not endpoint['url']:
                logging.warn(
                    "skipping endpoint '%s/%s', since it has no URL configured" % (
                        service.name, endpoint['interface']))
                continue
            try:
                parsed = urlparse(endpoint['url'])
                if not parsed.scheme or not parsed.netloc:
                    logging.warn(
                        "skipping endpoint '%s/%s', since its URL is misconfigured" % (
                            service.name, endpoint['interface']))
                    continue
            except Exception:
                logging.warn(
                    "skipping endpoint '%s/%s', since its URL is misconfigured" % (
                        service.name, endpoint['interface']))
                continue

            region = None
            if 'region' in endpoint:
                region = endpoint['region']
                if not region or not region.strip():
                    logging.warn(
                        "skipping endpoint '%s/%s', since its region is misconfigured" % (
                            service.name, endpoint['interface']))
                    continue

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