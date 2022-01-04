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
from designateclient.v2 import client as designateclient
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_operator import SEED_CRD, OPERATOR_ANNOTATION


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.dns_zones')
def validate(spec, dryrun, **_):
    dns_zones = spec.get('dns_zones', [])
    for dns_zone in dns_zones:
        if 'name' not in dns_zone or not dns_zone['name']:
            raise kopf.AdmissionError("dns_zone must have a name...")


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.dns_zones')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.dns_zones')
def seed_dns_zones_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} dns_zones'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        d = DNS_Zones(memo['args'])
        d.seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class DNS_Zones():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, dns_zones):
        for dns_zone in dns_zones:
            self._seed_endpoint(dns_zone)


    def _seed_dns_zone(self, zone):
        """
        Seed a projects designate zones and dependent objects
        :param project:
        :param zones:
        :param args:
        :return:
        """
        project_id = self.openstack.get_project_id(zone['domain'], zone['project'])
        project_name = zone['project']
        logging.debug("seeding dns zones of project %s" % project_name)

        designate = self.openstack.get_designateclient(project_id)
        recordsets = zone.pop('recordsets', None)

        zone = self.sanitize(zone, (
            'name', 'email', 'ttl', 'description', 'masters',
            'type'))

        try:
            resource = designate.zones.get(zone['name'])
            for attr in list(zone.keys()):
                if zone[attr] != resource.get(attr, ''):
                    logging.info(
                        "%s differs. update dns zone'%s/%s'" % (
                            attr, project_name, zone['name']))
                    designate.zones.update(resource['id'], zone)
                    break
        except designateclient.exceptions.NotFound:
            logging.info(
                "create dns zone '%s/%s'" % (
                    project_name, zone['name']))
            # wtf
            if 'type' in zone:
                zone['type_'] = zone.pop('type')
            if not self.dry_run:
                resource = designate.zones.create(zone.pop('name'),
                                            **zone)

        if recordsets:
            self.seed_dns_zone_recordsets(resource, recordsets)


    def seed_dns_zone_recordsets(self, zone, recordsets, project_id):
        """
        seed a designate zones recordsets
        :param zone:
        :param recordsets:
        :param designate:
        :return:
        """

        logging.debug("seeding recordsets of dns zones %s" % zone['name'])

        designate = self.openstack.get_designateclient(project_id)

        for recordset in recordsets:
            try:
                # records = recordset.pop('records', None)

                recordset = self.openstack.sanitize(recordset, (
                    'name', 'ttl', 'description', 'type', 'records'))

                if 'name' not in recordset or not recordset['name']:
                    logging.warn(
                        "skipping recordset %s of dns zone %s, since it is misconfigured" % (
                            recordset, zone['name']))
                    continue
                if 'type' not in recordset or not recordset['type']:
                    logging.warn(
                        "skipping recordset %s of dns zone %s, since it is misconfigured" % (
                            recordset, zone['name']))
                    continue

                query = {'name': recordset['name'],
                        'type': recordset['type']}
                result = designate.recordsets.list(zone['id'],
                                                criterion=query)
                if not result:
                    logging.info(
                        "create dns zones %s recordset %s" % (
                            zone['name'], recordset['name']))
                    designate.recordsets.create(zone['id'],
                                                recordset['name'],
                                                recordset['type'],
                                                recordset['records'],
                                                description=recordset.get(
                                                    'description'),
                                                ttl=recordset.get('ttl'))
                else:
                    resource = result[0]
                    for attr in list(recordset.keys()):
                        if attr == 'records':
                            for record in recordset['records']:
                                if record not in resource.get('records',
                                                            []):
                                    logging.info(
                                        "update dns zone %s recordset %s record %s" % (
                                            zone['name'], recordset['name'],
                                            record))
                                    designate.recordsets.update(zone['id'],
                                                                resource['id'],
                                                                recordset)
                                    break
                        elif recordset[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update dns zone'%s recordset %s'" % (
                                    attr, zone['name'], recordset['name']))
                            designate.recordsets.update(zone['id'],
                                                        resource['id'],
                                                        recordset)
                            break

            except Exception as e:
                logging.error(
                    "could not seed dns zone %s recordsets: %s" % (
                        zone['name'], e))