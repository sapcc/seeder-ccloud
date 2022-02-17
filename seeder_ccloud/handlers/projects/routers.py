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
import re
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.routers')
def validate(spec, dryrun, **_):
    routers = spec.get('routers', [])
    for router in routers:
        if 'name' not in router or not router['name']:
            raise kopf.AdmissionError("Router must have a name...")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.routers')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.routers')
def seed_routers_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} routers'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Routers(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Routers():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, routers):
        for router in routers:
            self._seed_router(router)


    def _seed_router(self, router):
        """
        seed a projects neutron routers and dependent objects
        :param project:
        :param routers:
        :param args:
        :param sess:
        :return:
        """

        project_id = self.openstack.get_project_id(router['domain'], router['project'])
        project_name = router['project']

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

        logging.debug("seeding routers of project %s" % project_name)
        neutron = self.openstack.get_neutronclient()

        try:
            interfaces = None
            if 'interfaces' in router:
                interfaces = router.pop('interfaces', None)

            router = self.openstack.sanitize(router, (
                'name', 'admin_state_up', 'description',
                'external_gateway_info', 'distributed', 'ha',
                'availability_zone_hints', 'flavor_id',
                'service_type_id', 'routes'))

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
                        network_id = self.openstack.get_network_id(project_id, router[
                            'external_gateway_info']['network'])
                    if not network_id:
                        logging.warn(
                            "skipping router '%s/%s': external_gateway_info.network %s not found" % (
                                project_name, router['name'],
                                router['external_gateway_info'][
                                    'network']))
                        raise Exception("skipping router '%s/%s': external_gateway_info.network %s not found" % (
                                project_name, router['name'],
                                router['external_gateway_info'][
                                    'network']))
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
                                subnet_id = self.openstack.get_subnet_id(project_id,
                                                        efi['subnet'])
                            if not subnet_id:
                                logging.warn(
                                    "skipping router '%s/%s': external_gateway_info.external_fixed_ips.subnet %s not found" % (
                                        project_name, router['name'],
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
            body['router']['tenant_id'] = project_id
            query = {'tenant_id': project_id, 'name': router['name']}
            result = neutron.list_routers(retrieve_all=True, **query)
            if not result or not result['routers']:
                logging.info(
                    "create router '%s/%s': %s" % (
                        project_name, router['name'], body))
                if not self.dry_run:
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
                        project_name, router['name'], body))
                    # drop read-only attributes
                    body['router'].pop('tenant_id', None)
                    if not self.dry_run:
                        result = neutron.update_router(resource['id'], body)
                        resource = result['router']

            if interfaces:
                self.seed_router_interfaces(resource, interfaces)
        except Exception as e:
            logging.error("could not seed router %s/%s: %s" % (
                project_name, router['name'], e))
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
                raise Exception("router interface '%s/%s', is misconfigured" % (
                        router['name'], interface))

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
            if not self.dry_run:
                neutron.add_interface_router(router['id'], interface)
            logging.info("added interface %s to router'%s'" % (
                interface, router['name']))