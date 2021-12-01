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

from keystoneclient import exceptions
from keystoneauth1 import exceptions as keystoneauthexceptions
from designateclient.v2 import client as designateclient

from seeder.openstack.domain.project_networks import Project_Networks
from seeder.openstack.domain.swift import Swift


from seeder.openstack.openstack_helper import OpenstackHelper
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass


class Projects():
    def __init__(self, args):
        self.openstack = OpenstackHelper(args)
        self.networks = Project_Networks(args)
   
    def seed(self, projects, domain):
        self.role_assignments = []
        for project in projects:
            self._seed_projects(domain, project)

        return self.role_assignments


    def _seed_projects(self, domain, project):
            """
            seed keystone projects and their dependant objects
            """

            logging.debug("seeding project %s %s" % (domain.name, project))

            keystone = self.openstack.get_keystoneclient()
 
            ra = None
            if 'role_assignments' in project:
                ra = project.pop('role_assignments', None)
            endpoints = None
            if 'project_endpoints' in project:
                endpoints = project.pop('project_endpoints', None)

            network_quota = None
            if 'network_quota' in project:
                network_quota = project.pop('network_quota', None)

            address_scopes = None
            if 'address_scopes' in project:
                address_scopes = project.pop('address_scopes', None)

            subnet_pools = None
            if 'subnet_pools' in project:
                subnet_pools = project.pop('subnet_pools', None)

            networks = None
            if 'networks' in project:
                networks = project.pop('networks', None)

            routers = None
            if 'routers' in project:
                routers = project.pop('routers', None)

            swift = project.pop('swift', None)

            dns_quota = project.pop('dns_quota', None)

            dns_zones = project.pop('dns_zones', None)

            dns_tsig_keys = project.pop('dns_tsigkeys', None)

            ec2_creds = project.pop('ec2_creds', None)

            flavors = project.pop('flavors', None)

            share_types = project.pop('share_types', None)

            bgpvpns = project.pop('bgpvpns', None)

            project = self.openstack.sanitize(project,
                            ('name', 'description', 'enabled', 'parent'))

            if 'name' not in project or not project['name']:
                logging.warn(
                    "skipping project '%s/%s', since it is misconfigured" % (
                        domain.name, project))
                return

            # resolve parent project if specified
            if 'parent' in project:
                parent_id = self.openstack.get_project_id(domain.name, project['parent'],
                                        keystone)
                if not parent_id:
                    logging.warn(
                        "skipping project '%s/%s', since its parent project is missing" % (
                            domain.name, project))
                    return
                else:
                    project['parent_id'] = parent_id

            project.pop('parent', None)

            result = keystone.projects.list(domain=domain.id,
                                            name=project['name'])
            if not result:
                logging.info(
                    "create project '%s/%s'" % (
                        domain.name, project['name']))
                resource = keystone.projects.create(domain=domain,
                                                    **project)
            else:
                resource = result[0]
                for attr in list(project.keys()):
                    if project[attr] != resource._info.get(attr, ''):
                        logging.info(
                            "%s differs. update project '%s/%s'" % (
                                attr, domain.name, project['name']))
                        keystone.projects.update(resource.id, **project)
                        break

            # cache the project id
            #if domain.name not in project_cache:
            #    project_cache[domain.name] = {}
            #project_cache[domain.name][resource.name] = resource.id

            # seed the projects endpoints
            if endpoints:
                self.seed_project_endpoints(resource, endpoints)

            # add the projects role assignments to the list to be resolved later on
            if ra:
                for role in ra:
                    assignment = dict()
                    assignment['role'] = role['role']
                    assignment['project'] = '%s@%s' % (
                        project['name'], domain.name)
                    if 'user' in role:
                        if '@' in role['user']:
                            assignment['user'] = role['user']
                        else:
                            assignment['user'] = '%s@%s' % (
                                role['user'], domain.name)
                    elif 'group' in role:
                        if '@' in role['group']:
                            assignment['group'] = role['group']
                        else:
                            assignment['group'] = '%s@%s' % (
                                role['group'], domain.name)
                    if 'inherited' in role:
                        assignment['inherited'] = role['inherited']
                    self.role_assignments.append(assignment)

            # seed the projects network quota
            if network_quota:
                limes = keystone.services.list(name='limes')
                # only seed network quota if limes is not available
                if not len(limes):
                    self.network.seed_project_network_quota(resource, network_quota)

            # seed the projects network address scopes
            if address_scopes:
                 self.network.seed_project_address_scopes(resource, address_scopes)

            # seed the projects network subnet-pools
            if subnet_pools:
                self.network.seed_project_subnet_pools(resource, subnet_pools)

            # seed the projects networks
            if networks:
                self.network.seed_project_networks(resource, networks)

            # seed the projects routers
            if routers:
                self.network.seed_project_routers(resource, routers)

            # seed swift account
            if swift:
                sw = Swift(self.args)
                sw.seed(resource, swift)

            # seed designate quota
            if dns_quota:
                limes = keystone.services.list(name='limes')
                # only seed dns quota if limes is not available
                if not len(limes):
                    self.seed_project_designate_quota(resource, dns_quota)

            # seed designate zone
            if dns_zones:
                self.seed_project_dns_zones(resource, dns_zones)

            # seed designate tsig keys
            if dns_tsig_keys:
                self.seed_project_tsig_keys(resource, dns_tsig_keys)

            if ec2_creds:
                self.seed_project_ec2_creds(resource, domain, ec2_creds)

            # seed flavors
            if flavors:
                self.seed_project_flavors(resource, flavors)

            if share_types:
                self.seed_project_share_types(resource, share_types)

            if bgpvpns:
                self.seed_project_bgpvpns(resource, bgpvpns)


    def seed_project_endpoints(self, project, endpoints):
        """ seed a keystone projects endpoints (OS-EP-FILTER)"""
        logging.debug(
            "seeding project endpoint %s %s" % (project.name, endpoints))

        keystone = self.openstack.get_keystoneclient()
        for name, endpoint in endpoints.items():
            if 'endpoint_id' in endpoint:
                try:
                    ep = keystone.endpoints.find(id=endpoint['endpoint_id'])
                    try:
                        keystone.endpoint_filter.check_endpoint_in_project(
                            project,
                            ep)
                    except exceptions.NotFound:
                        logging.info(
                            "add project endpoint '%s %s'" % (
                                project.name, ep))
                        keystone.endpoint_filter.add_endpoint_to_project(
                            project,
                            ep)
                except exceptions.NotFound as e:
                    logging.error(
                        'could not configure project endpoints for %s: endpoint %s not found: %s' % (
                            project.name, endpoint, e))
            else:
                try:
                    svc = keystone.services.find(name=endpoint['service'])
                    result = keystone.endpoints.list(service=svc.id,
                                                    region_id=endpoint[
                                                        'region'])
                    for ep in result:
                        try:
                            keystone.endpoint_filter.check_endpoint_in_project(
                                project, ep)
                        except exceptions.NotFound:
                            logging.info(
                                "add project endpoint '%s %s'" % (
                                    project.name, ep))
                            keystone.endpoint_filter.add_endpoint_to_project(
                                project,
                                ep)
                        except Exception as e:
                            logging.error(
                                'could not configure project endpoints for %s: endpoint %s not found: %s' % (
                                    project.name, ep, e))
                except exceptions.NotFound as e:
                    logging.error(
                        'could not configure project endpoints for %s: service %s not found: %s' % (
                            project.name, endpoint, e))
                    raise

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
            if len(new_quota):
                designate.quotas.update(project.id, new_quota)

        except Exception as e:
            logging.error(
                "could not seed designate quota for project %s: %s" % (
                    project.name, e))

                
    def seed_project_dns_zones(self, project, zones):
        """
        Seed a projects designate zones and dependent objects
        :param project:
        :param zones:
        :param args:
        :return:
        """

        logging.debug("seeding dns zones of project %s" % project.name)

        try:
            designate = self.openstack.get_designateclient(project.id)

            for zone in zones:
                recordsets = zone.pop('recordsets', None)

                zone = self.sanitize(zone, (
                    'name', 'email', 'ttl', 'description', 'masters',
                    'type'))

                if 'name' not in zone or not zone['name']:
                    logging.warn(
                        "skipping dns zone '%s/%s', since it is misconfigured" % (
                            project.name, zone))
                    continue

                try:
                    resource = designate.zones.get(zone['name'])
                    for attr in list(zone.keys()):
                        if zone[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update dns zone'%s/%s'" % (
                                    attr, project.name, zone['name']))
                            designate.zones.update(resource['id'], zone)
                            break
                except designateclient.exceptions.NotFound:
                    logging.info(
                        "create dns zone '%s/%s'" % (
                            project.name, zone['name']))
                    # wtf
                    if 'type' in zone:
                        zone['type_'] = zone.pop('type')
                    resource = designate.zones.create(zone.pop('name'),
                                                    **zone)

                if recordsets:
                    self.seed_dns_zone_recordsets(resource, recordsets)
        
        except Exception as e:
            logging.error("could not seed project dns zones %s: %s" % (
                project.name, e))


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


    def seed_project_ec2_creds(self, project, domain, creds):
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
            project_id = self.openstack.get_project_id(domain.name, project.name)
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


    def seed_project_share_types(self, project, share_types):
        """
        seed a project share types
        """
        # intialize manila client
        try:
            client = self.openstack.get_manilaclient("2.40")
            shareTypeManager = client.share_types
            shareTypeAccessManager = client.share_type_access
        except Exception as e:
            logging.error("Fail to initialize manila client: %s" % e)
            raise

        all_private_share_types = [t for t in shareTypeManager.list()
                                if t.is_public is False]
        validated_types = [t for t in all_private_share_types
                        if t.name in share_types]
        validated_type_names = [t.name for t in validated_types]

        for t in share_types:
            if t not in validated_type_names:
                logging.warn('Share type `%s` does not exists or is not private', t)

        logging.info('Assign %s to project %s', validated_types, project.id)

        def list_type_projects(stype):
            return [l.project_id for l in shareTypeAccessManager.list(stype)]

        current_types = [t for t in all_private_share_types
                        if project.id in list_type_projects(t)]

        logging.info(current_types)

        to_add = [t for t in validated_types if t not in current_types]
        to_remove = [t for t in current_types if t not in validated_types]

        logging.info('add share types %s' % to_add)
        logging.info('remove share types %s' % to_remove)

        for t in to_remove:
            shareTypeAccessManager.remove_project_access(t, project.id)
        for t in to_add:
            shareTypeAccessManager.add_project_access(t, project.id)


    def seed_project_bgpvpns(self, project, bgpvpns):
        """
        seed a projects neutron BGPVPNs and dependent objects
        :param project: the project for which the resources are being created
        :param bgpvpns: the list of resources that sould be created
        """

        logging.debug("seeding bgpvpns of project %s" % project.name)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        for bgpvpn in bgpvpns:
            try:
                bgpvpn = self.openstack.sanitize(bgpvpn, ('name', 'import_targets',
                                        'export_targets', 'route_targets'))
                # check required parameters
                if not bgpvpn.get('name'):
                    logging.warn(
                        "skipping bgpvpn '%s/%s', since it is misconfigured in "
                        "option 'name'" % (project.name, bgpvpn))
                    continue
                if isinstance(bgpvpn.get('import_targets', []), list):
                    logging.warn(
                        "skipping bgpvpn '%s/%s', since it is misconfigured in "
                        "option 'import_targets'" % (project.name, bgpvpn))
                    continue
                if isinstance(bgpvpn.get('export_targets', []), list):
                    logging.warn(
                        "skipping bgpvpn '%s/%s', since it is misconfigured in "
                        "option 'export_targets'" % (project.name, bgpvpn))
                    continue
                if isinstance(bgpvpn.get('route_targets', []), list):
                    logging.warn(
                        "skipping bgpvpn '%s/%s', since it is misconfigured in "
                        "option 'route_targets'" % (project.name, bgpvpn))
                    continue

                body = {'bgpvpn': bgpvpn.copy()}
                body['bgpvpn']['tenant_id'] = project.id

                # check if the bgpvpn already exists
                query = {'tenant_id': project.id, 'name': bgpvpn['name']}
                result = neutron.list_bgpvpns(retrieve_all=True, **query)
                if not result or not result['bgpvpns']:
                    logging.info(
                        "create bgpvpn '%s/%s'" % (project.name, bgpvpn['name']))
                    result = neutron.create_bgpvpn(body)
                    resource = result['bgpvpn']
                else:
                    resource = result['bgpvpn'][0]
                    for attr in list(bgpvpn.keys()):
                        if bgpvpn[attr] != resource.get(attr, ''):
                            logging.info(
                                "%s differs. update bgpvpn '%s/%s'" % (
                                    attr, project.name, bgpvpn['name']))
                            # drop read-only attributes
                            body['bgpvpn'].pop('tenant_id', None)
                            neutron.update_bgpvpn(resource['id'], body)
                            break
            except Exception as e:
                logging.error("could not seed bgpvpn %s/%s: %s" % (
                    project.name, bgpvpn['name'], e))
                raise
