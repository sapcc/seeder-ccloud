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
from typing import List
from seeder_ccloud import utils
from deepdiff import DeepDiff
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.networks')
def validate(memo: kopf.Memo, dryrun, spec, old, warnings: List[str], **_):
    networks = spec['openstack'].get('networks', [])
    for network in networks:
        if 'name' not in networks or not networks['name']:
            raise kopf.AdmissionError("Network must have a name if present..")
        tags = network.get('tags', [])
        for tag in tags:
            if not tag or len(tag) > 60:
                raise kopf.AdmissionError("Tags size must not be > 60 if present..")
        subnets = subnets.get('subnets', [])
        for subnet in subnets:
            if 'name' not in subnet or not subnet['name']:
                raise kopf.AdmissionError("Subnet must have a name if present..")


    if dryrun and networks:
        old_networks = None
        if old is not None:
            old_networks = old['spec']['openstack'].get('networks', None)
        changed = utils.get_changed_seeds(old_networks, networks)
        diffs = Networks(memo['args'], dryrun).seed(changed)
        if diffs:
            warnings.append({'networks': diffs})


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.networks')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.networks')
def seed_networks_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} networks'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Networks(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Networks():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, networks):
        self.diffs = {}
        for network in networks:
            self._seed_network(network)
        return self.diffs


    def _seed_network(self, network):
        """
        seed a projects neutron networks and dependent objects
        :param networks:
        :return:
        """
        project_id = self.openstack.get_project_id(network['domain'], network['project'])
        project_name = network['project']
        # network attribute name mappings
        rename = {'router_external': 'router:external',
                'provider_network_type': 'provider:network_type',
                'provider_physical_network': 'provider:physical_network',
                'provider_segmentation_id': 'provider:segmentation_id'}

        logging.debug("seeding networks of project %s" % project_name)

        neutron = self.openstack.get_neutronclient()
        subnets = network.pop('subnets', None)
        tags = network.pop('tags', None)

        # rename some yaml unfriendly network attributes
        for key, value in list(rename.items()):
            if key in network:
                network[value] = network.pop(key)

        network = self.openstack.sanitize(network, (
            'name', 'admin_state_up', 'port_security_enabled',
            'provider:network_type', 'provider:physical_network',
            'provider:segmentation_id', 'qos_policy_id',
            'router:external',
            'shared', 'vlan_transparent', 'description'))
        self.diffs[network['name']] = []

        body = {'network': network.copy()}
        body['network']['tenant_id'] = project_id
        query = {'tenant_id': project_id, 'name': network['name']}
        result = neutron.list_networks(retrieve_all=True, **query)
        if not result or not result['networks']:
            self.diffs[network['name']].append('create')
            logging.info(
                "create network '%s/%s'" % (
                    project_name, network['name']))
            result = neutron.create_network(body)
            if not self.dry_run:
                resource = result['network']
        else:
            resource = result['networks'][0]
            diff = DeepDiff(resource.to_dict(), network)
            if 'values_changed' in diff:
                self.diffs[network['name']].append(diff['values_changed'])
                logging.debug("network %s differs: '%s'" % (network['name'], diff))
            
                body['network'].pop('tenant_id', None)
                if not self.dry_run:
                    neutron.update_network(resource['id'], body)

        if tags:
            self._seed_network_tags(resource, tags)

        if subnets:
            self._seed_network_subnets(resource, subnets)


    def _seed_network_tags(self, network, tags):
            """
            seed neutron tags of a network
            :param network:
            :param tags:
            :param args:
            :param sess:
            :return:
            """

            logging.debug("seeding tags of network %s" % network['name'])

            # grab a neutron client
            neutron = self.openstack.get_neutronclient()

            for tag in tags:
                if tag not in network['tags']:
                    self.diffs[network['name']].append('create tag: {}'.format(tag))
                    logging.info(
                        "adding tag %s to network '%s'" % (
                            tag, network['name']))
                    if not self.dry_run:
                        neutron.add_tag('networks', network['id'], tag)


    def _seed_network_subnets(self, network, subnets):
        """
        seed neutron subnets of a network
        :param network:
        :param subnets:
        :param args:
        :param sess:
        :return:
        """

        logging.debug("seeding subnets of network %s" % network['name'])

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        for subnet in subnets:
            # lookup subnetpool-id
            if 'subnetpool' in subnet:
                subnet['subnetpool_id'] = self.openstack.get_subnetpool_id(
                    network['tenant_id'],
                    subnet['subnetpool'])
                if not subnet['subnetpool_id']:
                    logging.warn(
                        "skipping subnet '%s/%s', since its subnetpool is invalid" % (
                            network['name'], subnet))
                    continue
                subnet.pop('subnetpool', None)

            subnet = self.openstack.sanitize(subnet, (
                'name', 'enable_dhcp', 'dns_nameservers',
                'allocation_pools', 'host_routes', 'ip_version',
                'gateway_ip', 'cidr', 'prefixlen', 'subnetpool_id',
                'description'))

            if 'gateway_ip' in subnet and subnet['gateway_ip'] == 'null':
                subnet['gateway_ip'] = None

            body = {'subnet': subnet.copy()}
            body['subnet']['network_id'] = network['id']
            body['subnet']['tenant_id'] = network['tenant_id']

            query = {'network_id': network['id'], 'name': subnet['name']}
            result = neutron.list_subnets(retrieve_all=True, **query)
            self.diffs[network['name'] + '_subnet'] = []
            if not result or not result['subnets']:
                self.diffs[network['name'] + '_subnet'].append('create subnet: {}'.format(subnet['name']))
                logging.info(
                    "create subnet '%s/%s'" % (
                        network['name'], subnet['name']))
                if not self.dry_run:
                    neutron.create_subnet(body)
            else:
                resource = result['subnets'][0]
                diff = DeepDiff(resource.to_dict(), subnet)
                if 'values_changed' in diff:
                    self.diffs[network['name'] + '_subnet'].append(diff['values_changed'])
                    logging.debug("network %s subnet % differs: '%s'" % (network['name'], subnet['name'], diff))
                    if not self.dry_run:
                        # drop read-only attributes
                        body['subnet'].pop('cidr', None)
                        body['subnet'].pop('segment_id', None)
                        body['subnet'].pop('tenant_id', None)
                        body['subnet'].pop('network_id', None)
                        body['subnet'].pop('subnetpool_id', None)
                        body['subnet'].pop('ip_version', None)
                        body['subnet'].pop('prefixlen', None)
                        neutron.update_subnet(resource['id'], body)