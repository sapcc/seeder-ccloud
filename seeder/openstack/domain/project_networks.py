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
import re

from seeder.openstack.openstack_helper import OpenstackHelper

class Project_Networks:
    def __init__(self, args):
        self.opentack = OpenstackHelper(args)


    def seed_project_networks(self, project, networks):
        """
        seed a projects neutron networks and dependent objects
        :param project:
        :param networks:
        :param args:
        :param sess:
        :return:
        """

        # network attribute name mappings
        rename = {'router_external': 'router:external',
                'provider_network_type': 'provider:network_type',
                'provider_physical_network': 'provider:physical_network',
                'provider_segmentation_id': 'provider:segmentation_id'}

        logging.debug("seeding networks of project %s" % project.name)

        neutron = self.openstack.get_neutronclient()

        for network in networks:
            try:
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

                if 'name' not in network or not network['name']:
                    logging.warn(
                        "skipping network '%s/%s', since it is misconfigured" % (
                            project.name, network))
                    continue

                body = {'network': network.copy()}
                body['network']['tenant_id'] = project.id
                query = {'tenant_id': project.id, 'name': network['name']}
                result = neutron.list_networks(retrieve_all=True, **query)
                if not result or not result['networks']:
                    logging.info(
                        "create network '%s/%s'" % (
                            project.name, network['name']))
                    result = neutron.create_network(body)
                    resource = result['network']
                else:
                    resource = result['networks'][0]
                    for attr in list(network.keys()):
                        if network[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update network'%s/%s'" % (
                                    attr, project.name, network['name']))
                            # drop read-only attributes
                            body['network'].pop('tenant_id', None)
                            neutron.update_network(resource['id'], body)
                            break

                if tags:
                    self.seed_network_tags(resource, tags)

                if subnets:
                    self.seed_network_subnets(resource, subnets)
            except Exception as e:
                logging.error("could not seed network %s/%s: %s" % (
                    project.name, network['name'], e))

    def seed_network_tags(self, network, tags):
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
            if not tag or len(tag) > 60:
                logging.warn(
                    "skipping tag '%s/%s', since it is invalid" % (
                        network['name'], tag))
                continue

            if tag not in network['tags']:
                logging.info(
                    "adding tag %s to network '%s'" % (
                        tag, network['name']))
                neutron.add_tag('networks', network['id'], tag)


    def seed_project_subnet_pools(self, project, subnet_pools, **kvargs):
        logging.debug(
            "seeding subnet-pools of project %s" % project.name)

        neutron = self.openstack.get_neutronclient()

        for subnet_pool in subnet_pools:
            try:
                subnet_pool = self.openstack.sanitize(subnet_pool, (
                    'name', 'default_quota', 'prefixes', 'min_prefixlen',
                    'shared',
                    'default_prefixlen', 'max_prefixlen', 'description',
                    'address_scope_id', 'is_default'))

                if 'name' not in subnet_pool or not subnet_pool['name']:
                    logging.warn(
                        "skipping subnet-pool '%s/%s', since it is misconfigured" % (
                            project.name, subnet_pool))
                    continue

                if kvargs:
                    subnet_pool = dict(list(subnet_pool.items()) + list(kvargs.items()))

                body = {'subnetpool': subnet_pool.copy()}
                body['subnetpool']['tenant_id'] = project.id

                query = {'tenant_id': project.id,
                        'name': subnet_pool['name']}
                result = neutron.list_subnetpools(retrieve_all=True,
                                                **query)
                if not result or not result['subnetpools']:
                    logging.info(
                        "create subnet-pool '%s/%s'" % (
                            project.name, subnet_pool['name']))
                    result = neutron.create_subnetpool(body)
                    # cache the subnetpool-id
                    #if project.id not in subnetpool_cache:
                    #    subnetpool_cache[project.id] = {}
                    # subnetpool_cache[project.id][subnet_pool['name']] = \
                    #    result['subnetpool']['id']
                else:
                    resource = result['subnetpools'][0]
                    # cache the subnetpool-id
                    #if project.id not in subnetpool_cache:
                    #    subnetpool_cache[project.id] = {}
                    #subnetpool_cache[project.id][subnet_pool['name']] = \
                    #    resource['id']

                    for attr in list(subnet_pool.keys()):
                        if attr == 'prefixes':
                            for prefix in subnet_pool['prefixes']:
                                if prefix not in resource.get('prefixes',
                                                            []):
                                    logging.info(
                                        "update subnet-pool prefixes '%s/%s'" % (
                                            project.name,
                                            subnet_pool['name']))
                                    # drop read-only attributes
                                    body['subnetpool'].pop('tenant_id',
                                                        None)
                                    body['subnetpool'].pop('shared', None)
                                    neutron.update_subnetpool(
                                        resource['id'], body)
                                    break
                        else:
                            # a hacky comparison due to the neutron api not dealing with string/int attributes consistently
                            if str(subnet_pool[attr]) != str(
                                    resource.get(attr, '')):
                                logging.info(
                                    "%s differs. update subnet-pool'%s/%s'" % (
                                        attr, project.name,
                                        subnet_pool['name']))
                                # drop read-only attributes
                                body['subnetpool'].pop('tenant_id', None)
                                body['subnetpool'].pop('shared', None)
                                neutron.update_subnetpool(resource['id'],
                                                        body)
                                break
            except Exception as e:
                logging.error("could not seed subnet pool %s/%s: %s" % (
                    project.name, subnet_pool['name'], e))
                raise


    def seed_project_subnet_pools(self, project, subnet_pools, **kvargs):
        logging.debug(
            "seeding subnet-pools of project %s" % project.name)

        neutron = self.openstack.get_neutronclient()

        for subnet_pool in subnet_pools:
            try:
                subnet_pool = self.openstack.sanitize(subnet_pool, (
                    'name', 'default_quota', 'prefixes', 'min_prefixlen',
                    'shared',
                    'default_prefixlen', 'max_prefixlen', 'description',
                    'address_scope_id', 'is_default'))

                if 'name' not in subnet_pool or not subnet_pool['name']:
                    logging.warn(
                        "skipping subnet-pool '%s/%s', since it is misconfigured" % (
                            project.name, subnet_pool))
                    continue

                if kvargs:
                    subnet_pool = dict(list(subnet_pool.items()) + list(kvargs.items()))

                body = {'subnetpool': subnet_pool.copy()}
                body['subnetpool']['tenant_id'] = project.id

                query = {'tenant_id': project.id,
                        'name': subnet_pool['name']}
                result = neutron.list_subnetpools(retrieve_all=True,
                                                **query)
                if not result or not result['subnetpools']:
                    logging.info(
                        "create subnet-pool '%s/%s'" % (
                            project.name, subnet_pool['name']))
                    result = neutron.create_subnetpool(body)
                    # cache the subnetpool-id
                    #if project.id not in subnetpool_cache:
                    #    subnetpool_cache[project.id] = {}
                    # subnetpool_cache[project.id][subnet_pool['name']] = \
                    #    result['subnetpool']['id']
                else:
                    resource = result['subnetpools'][0]
                    # cache the subnetpool-id
                    #if project.id not in subnetpool_cache:
                    #    subnetpool_cache[project.id] = {}
                    #subnetpool_cache[project.id][subnet_pool['name']] = \
                    #    resource['id']

                    for attr in list(subnet_pool.keys()):
                        if attr == 'prefixes':
                            for prefix in subnet_pool['prefixes']:
                                if prefix not in resource.get('prefixes',
                                                            []):
                                    logging.info(
                                        "update subnet-pool prefixes '%s/%s'" % (
                                            project.name,
                                            subnet_pool['name']))
                                    # drop read-only attributes
                                    body['subnetpool'].pop('tenant_id',
                                                        None)
                                    body['subnetpool'].pop('shared', None)
                                    neutron.update_subnetpool(
                                        resource['id'], body)
                                    break
                        else:
                            # a hacky comparison due to the neutron api not dealing with string/int attributes consistently
                            if str(subnet_pool[attr]) != str(
                                    resource.get(attr, '')):
                                logging.info(
                                    "%s differs. update subnet-pool'%s/%s'" % (
                                        attr, project.name,
                                        subnet_pool['name']))
                                # drop read-only attributes
                                body['subnetpool'].pop('tenant_id', None)
                                body['subnetpool'].pop('shared', None)
                                neutron.update_subnetpool(resource['id'],
                                                        body)
                                break
            except Exception as e:
                logging.error("could not seed subnet pool %s/%s: %s" % (
                    project.name, subnet_pool['name'], e))
                raise

    def seed_network_subnets(self, network, subnets):
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

            if 'name' not in subnet or not subnet['name']:
                logging.warn(
                    "skipping subnet '%s/%s', since it is misconfigured" % (
                        network['name'], subnet))
                continue

            if 'gateway_ip' in subnet and subnet['gateway_ip'] == 'null':
                subnet['gateway_ip'] = None

            body = {'subnet': subnet.copy()}
            body['subnet']['network_id'] = network['id']
            body['subnet']['tenant_id'] = network['tenant_id']

            query = {'network_id': network['id'], 'name': subnet['name']}
            result = neutron.list_subnets(retrieve_all=True, **query)
            if not result or not result['subnets']:
                logging.info(
                    "create subnet '%s/%s'" % (
                        network['name'], subnet['name']))
                neutron.create_subnet(body)
            else:
                resource = result['subnets'][0]
                for attr in list(subnet.keys()):
                    if subnet[attr] != resource.get(attr, ''):
                        logging.info(
                            "%s differs. update subnet'%s/%s'" % (
                                attr, network['name'], subnet['name']))
                        # drop read-only attributes
                        body['subnet'].pop('cidr', None)
                        body['subnet'].pop('segment_id', None)
                        body['subnet'].pop('tenant_id', None)
                        body['subnet'].pop('network_id', None)
                        body['subnet'].pop('subnetpool_id', None)
                        body['subnet'].pop('ip_version', None)
                        body['subnet'].pop('prefixlen', None)
                        neutron.update_subnet(resource['id'], body)
                        break

    def seed_project_network_quota(self, project, quota):
        """
        seed a projects network quota
        """

        logging.debug("seeding network-quota of project %s" % project.name)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        quota = self.openstack.sanitize(quota, (
            'floatingip', 'healthmonitor', 'l7policy', 'listener',
            'loadbalancer',
            'network', 'pool', 'port', 'rbac_policy', 'router',
            'security_group',
            'security_group_rule', 'subnet', 'subnetpool', 'bgpvpn'))

        body = {'quota': quota.copy()}
        result = neutron.show_quota(project.id)
        if not result or not result['quota']:
            logging.info(
                "set project %s network quota to '%s'" % (
                    project.name, quota))
            neutron.update_quota(project.id, body)
        else:
            resource = result['quota']
            new_quota = {}
            for attr in list(quota.keys()):
                if int(quota[attr]) > int(resource.get(attr, '')):
                    logging.info(
                        "%s differs. set project %s network quota to '%s'" % (
                            attr, project.name, quota[attr]))
                    new_quota[attr] = quota[attr]
            if len(new_quota):
                neutron.update_quota(project.id, {'quota': new_quota})

    
    def seed_project_address_scopes(self, project, address_scopes):
        """
        seed a projects neutron address scopes and dependent objects
        :param project: 
        :param address_scopes: 
        :param args: 
        :param sess: 
        :return: 
        """
        logging.debug("seeding address-scopes of project %s" % project.name)

        neutron = self.openstack.get_neutronclient()

        for scope in address_scopes:
            try:
                subnet_pools = None
                if 'subnet_pools' in scope:
                    subnet_pools = scope.pop('subnet_pools', None)

                scope = self.openstack.sanitize(scope, ('name', 'ip_version', 'shared'))

                if 'name' not in scope or not scope['name']:
                    logging.warn(
                        "skipping address-scope '%s/%s', since it is misconfigured" % (
                            project.name, scope))
                    continue

                body = {'address_scope': scope.copy()}
                body['address_scope']['tenant_id'] = project.id
                query = {'tenant_id': project.id, 'name': scope['name']}
                result = neutron.list_address_scopes(retrieve_all=True,
                                                    **query)
                if not result or not result['address_scopes']:
                    logging.info(
                        "create address-scope '%s/%s'" % (
                            project.name, scope['name']))
                    result = neutron.create_address_scope(body)
                    resource = result['address_scope']
                else:
                    resource = result['address_scopes'][0]
                    for attr in list(scope.keys()):
                        if scope[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update address-scope '%s/%s'" % (
                                    attr, project.name, scope['name']))
                            # drop read-only attributes
                            body['address_scope'].pop('tenant_id', None)
                            body['address_scope'].pop('ip_version', None)
                            neutron.update_address_scope(resource['id'],
                                                        body)
                            break

                if subnet_pools:
                    kvargs = {'address_scope_id': resource['id']}
                    self.seed_project_subnet_pools(project, subnet_pools, **kvargs)
            except Exception as e:
                logging.error("could not seed address scope %s/%s: %s" % (
                    project.name, scope['name'], e))
                raise


    def seed_project_routers(self, project, routers):
        """
        seed a projects neutron routers and dependent objects
        :param project:
        :param routers:
        :param args:
        :param sess:
        :return:
        """

        def external_fixed_ip_subnets_differ(desired, actual):
            subnets = {}
            for subnet in actual:
                subnets[subnet['subnet_id']] = subnet['ip_address']

            for entry in desired:
                if 'subnet_id' in entry:
                    if not entry['subnet_id'] in subnets:
                        return True

            return False

        regex = r"^([^@]+)@([^@]+)@([^@]+)$"

        logging.debug("seeding routers of project %s" % project.name)
        neutron = self.openstack.get_neutronclient()

        for router in routers:
            try:
                interfaces = None
                if 'interfaces' in router:
                    interfaces = router.pop('interfaces', None)

                router = self.openstack.sanitize(router, (
                    'name', 'admin_state_up', 'description',
                    'external_gateway_info', 'distributed', 'ha',
                    'availability_zone_hints', 'flavor_id',
                    'service_type_id', 'routes'))

                if 'name' not in router or not router['name']:
                    logging.warn(
                        "skipping router '%s %s', since it is misconfigured" % (
                            project.name, router))
                    continue

                if 'external_gateway_info' in router:
                    # lookup network-id
                    if 'network' in router['external_gateway_info']:
                        network_id = None

                        # network@project@domain ?
                        match = re.match(regex,
                                        router['external_gateway_info'][
                                            'network'])
                        if match:
                            project_id = self.openstack.get_project_id(match.group(3),
                                                        match.group(2))
                            if project_id:
                                network_id = self.openstack.get_network_id(project_id,
                                                            match.group(1))
                        else:
                            # network of this project
                            network_id = self.openstack.get_network_id(project.id, router[
                                'external_gateway_info']['network'])
                        if not network_id:
                            logging.warn(
                                "skipping router '%s/%s': external_gateway_info.network %s not found" % (
                                    project.name, router['name'],
                                    router['external_gateway_info'][
                                        'network']))
                            continue
                        router['external_gateway_info'][
                            'network_id'] = network_id
                        router['external_gateway_info'].pop('network', None)

                    if 'external_fixed_ips' in router[
                        'external_gateway_info']:
                        for index, efi in enumerate(
                                router['external_gateway_info'][
                                    'external_fixed_ips']):
                            if 'subnet' in efi:
                                subnet_id = None

                                # subnet@project@domain ?
                                match = re.match(regex, efi['subnet'])
                                if match:
                                    project_id = self.openstack.get_project_id(
                                        match.group(3), match.group(2))
                                    if project_id:
                                        subnet_id = self.openstack.get_subnet_id(
                                            project_id, match.group(1))
                                else:
                                    # subnet of this project
                                    subnet_id = self.openstack.get_subnet_id(project.id,
                                                            efi['subnet'])
                                if not subnet_id:
                                    logging.warn(
                                        "skipping router '%s/%s': external_gateway_info.external_fixed_ips.subnet %s not found" % (
                                            project.name, router['name'],
                                            efi['subnet']))
                                    continue
                                efi['subnet_id'] = subnet_id
                                efi.pop('subnet', None)
                            router['external_gateway_info'][
                                'external_fixed_ips'][index] = self.openstack.sanitize(efi,
                                                                        ('subnet_id',
                                                                        'ip_address'))

                    router['external_gateway_info'] = self.openstack.sanitize(
                        router['external_gateway_info'],
                        ('network_id', 'enable_snat', 'external_fixed_ips'))

                body = {'router': router.copy()}
                body['router']['tenant_id'] = project.id
                query = {'tenant_id': project.id, 'name': router['name']}
                result = neutron.list_routers(retrieve_all=True, **query)
                if not result or not result['routers']:
                    logging.info(
                        "create router '%s/%s': %s" % (
                            project.name, router['name'], body))
                    result = neutron.create_router(body)
                    resource = result['router']
                else:
                    resource = result['routers'][0]
                    update = False

                    for attr in list(router.keys()):
                        if attr == 'external_gateway_info':
                            if 'network_id' in router[attr] and resource.get(attr, ''):
                                if router[attr]['network_id'] != \
                                        resource[attr]['network_id']:
                                    update = True

                            if ('external_fixed_ips' in router[
                                'external_gateway_info'] and
                                    external_fixed_ip_subnets_differ(
                                        router['external_gateway_info'][
                                            'external_fixed_ips'],
                                        resource['external_gateway_info'][
                                            'external_fixed_ips'])):
                                update = True
                        elif router[attr] != resource.get(attr, ''):
                            update = True

                    if update:
                        logging.info("update router '%s/%s': %s" % (
                            project.name, router['name'], body))
                        # drop read-only attributes
                        body['router'].pop('tenant_id', None)
                        result = neutron.update_router(resource['id'], body)
                        resource = result['router']

                if interfaces:
                    self.seed_router_interfaces(resource, interfaces)
            except Exception as e:
                logging.error("could not seed router %s/%s: %s" % (
                    project.name, router['name'], e))
                raise
    

    def seed_router_interfaces(self, router, interfaces):
        """
        seed a routers interfaces (routes)
        :param router:
        :param interfaces:
        :param args:
        :param sess:
        :return:
        """

        logging.debug("seeding interfaces of router %s" % router['name'])
        neutron = self.openstack.get_neutronclient()

        for interface in interfaces:
            if 'subnet' in interface:
                subnet_id = None
                # subnet@project@domain ?
                if '@' in interface['subnet']:
                    parts = interface['subnet'].split('@')
                    if len(parts) > 2:
                        project_id = self.openstack.get_project_id(parts[2], parts[1])
                        if project_id:
                            subnet_id = self.openstack.get_subnet_id(project_id, parts[0])
                else:
                    # lookup subnet-id
                    subnet_id = self.openstack.get_subnet_id(router['tenant_id'],
                                            interface['subnet'])

                if subnet_id:
                    interface['subnet_id'] = subnet_id

            interface = self.openstack.sanitize(interface, ('subnet_id', 'port_id'))

            if 'subnet_id' not in interface and 'port_id' not in interface:
                logging.warn(
                    "skipping router interface '%s/%s', since it is misconfigured" % (
                        router['name'], interface))
                continue

            # check if the interface is already configured for the router
            query = {'device_id': router['id']}
            result = neutron.list_ports(retrieve_all=True, **query)
            found = False
            for port in result['ports']:
                if 'port_id' in interface and port['id'] == interface['port_id']:
                    found = True
                    break
                elif 'subnet_id' in interface:
                    for ip in port['fixed_ips']:
                        if 'subnet_id' in ip and ip['subnet_id'] == \
                                interface['subnet_id']:
                            found = True
                            break
                if found:
                    break

            if found:
                continue

            # add router interface
            neutron.add_interface_router(router['id'], interface)
            logging.info("added interface %s to router'%s'" % (
                interface, router['name']))