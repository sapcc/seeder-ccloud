import copy
from datetime import datetime, timedelta
import threading, operator

from cachetools import TTLCache, cachedmethod
from cachetools.keys import hashkey
from functools import partial
from keystoneclient.v3 import client as keystoneclient
from neutronclient.v2_0 import client as neutronclient
from designateclient.v2 import client as designateclient
from cinderclient.v3 import client as cinderclient
from manilaclient.v2 import client as manilaclient
from manilaclient import api_versions
from novaclient import client as novaclient
from osc_placement.http import SessionClient as placementclient
from keystoneauth1.loading import cli
from keystoneauth1 import session

lock = threading.RLock()

class OpenstackHelper:
    _singleton = None
    args = None
    session = None

    def __new__(cls, args):
        if not cls._singleton:
            cls._singleton = super(OpenstackHelper, cls).__new__(cls)
            cls.args = args
            cls.id_cache = TTLCache(maxsize=5000, ttl=timedelta(days=30), timer=datetime.now)
            cls.client_cache = TTLCache(maxsize=10, ttl=timedelta(minutes=5), timer=datetime.now)

        return cls._singleton
    

    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'keystone'))
    def get_keystoneclient(self):
        session = self.get_session(self.args)
        return keystoneclient.Client(session=session,
                                     interface=self.args.interface)


    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'neutron'))
    def get_neutronclient(self):
        session = self.get_session(self.args)
        return neutronclient.Client(session=session,
                                    interface=self.args.interface)


    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'nova'))
    def get_novaclient(self):
        session = self.get_session(self.args)
        return novaclient.Client('2.1', session=session,
                                 endpoint_type=self.args.interface + 'URL')

    
    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'cinder'))
    def get_cinderclient(self, api_version='3.50'):
        session = self.get_session(self.args)
        return cinderclient.Client(session=session, 
                                   interface=self.args.interface, api_version=api_version)

                            
    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'manila'))
    def get_manilaclient(self, api_version='2.40'):
        session = self.get_session(self.args)
        api_version = api_versions.APIVersion(api_version)
        return manilaclient.Client(session=session, api_version=api_version)

    
    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'placement'))
    def get_placementclient(self, api_version='1.6'):
        session = self.get_session(self.args)
        ks_filter = {'service_type': 'placement', 'interface': self.args.interface}
        return placementclient(session=session, ks_filter=ks_filter, api_version=api_version)


    @cachedmethod(operator.attrgetter('client_cache'), partial(hashkey, 'designate'))
    def get_designateclient(self, project_id):
        # the designate client needs a token scoped to a project.id
        # due to a crappy bugfix in https://review.openstack.org/#/c/187570/
        designate_args = copy.copy(self.args)
        designate_args.os_project_id = project_id
        designate_args.os_domain_id = None
        designate_args.os_domain_name = None
        plugin = cli.load_from_argparse_arguments(designate_args)
        sess = session.Session(auth=plugin,
                            user_agent='openstack-seeder',
                            verify=not self.args.insecure)

        return designateclient.Client(session=sess,
                                        endpoint_type=self.args.interface + 'URL',
                                        all_projects=True)


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'role'))
    def get_role_id(self, name):
        """ get a (cached) role-id for a role name """
        roles = self.get_keystoneclient().roles.list(name=name)
        if roles:
            return roles[0].id
        else:
            # returning none would be saved in the cache as well
            raise Exception("role {0} not found".format(name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'domain'))
    def get_domain_id(self, name):
        """ get a (cached) domain-id for a domain name """
        domains = self.get_keystoneclient().domains.list(name=name)
        if domains:
            return domains[0].id
        else:
            raise Exception("domain {0} not found".format(name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'project'))
    def get_project_id(self, domain, name):
        """ get a (cached) project-id for a domain and project name """
        projects = self.get_keystoneclient().projects.list(
            domain=self.get_domain_id(domain),
            name=name)
        if projects:
            return projects[0].id
        else:
            raise Exception("project {0}/{1} not found".format(domain, name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'user'))
    def get_user_id(self, domain, name):
        """ get a (cached) user-id for a domain and user name """
        users = self.get_keystoneclient().users.list(
            domain=self.get_domain_id(domain),
            name=name)
        if users:
            return users[0].id
        else:
            raise Exception("user {0}/{1} not found".format(domain, name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'group'))
    def get_group_id(self, domain, name):
        """ get a (cached) group-id for a domain and group name """
        groups = self.get_keystoneclient().groups.list(
            domain=self.get_domain_id(domain),
            name=name)
        if groups:
           return groups[0].id
        else:
           raise Exception("group {0}/{1} not found".format(domain, name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'subnetpool'))
    def get_subnetpool_id(self, project_id, name):
        """ get a (cached) subnetpool-id for a project-id and subnetpool name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.get_neutronclient().list_subnetpools(retrieve_all=True, **query)
        if result and result['subnetpools']:
            return result['subnetpools'][0]['id']
        else:
            raise Exception("subnetpool {0}/{1} not found".format(project_id, name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'network'))
    def get_network_id(self, project_id, name):
        """ get a (cached) network-id for a project-id and network name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.get_neutronclient().list_networks(retrieve_all=True, **query)
        if result and result['networks']:
            return result['networks'][0]['id']     
        else:
            raise Exception("network {0}/{1} not found".format(project_id, name))


    @cachedmethod(operator.attrgetter('id_cache'), partial(hashkey, 'subnet'))
    def get_subnet_id(self, project_id, name):
        """ get a (cached) subnet-id for a project-id and subnet name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.get_neutronclient().list_subnets(retrieve_all=True, **query)
        if result and result['subnets']:
            return result['subnets'][0]['id']
        else:
            raise Exception("subnet {0}/{1} not found".format(project_id, name))


    @staticmethod
    def sanitize(source, keys):
        result = {}
        for attr in keys:
            if attr in source:
                if isinstance(source[attr], str):
                    result[attr] = source[attr].strip()
                else:
                    result[attr] = source[attr]
        return result


    @staticmethod
    def redact(source, keys=('password', 'secret', 'userPassword', 'cam_password')):
        def _blankout(data, k):
            if isinstance(data, list):
                for item in data:
                    _blankout(item, k)
            elif isinstance(data, dict):
                for attr in keys:
                    if attr in data:
                        if isinstance(data[attr], str):
                            data[attr] = '********'
                for k, v in data.items():
                    _blankout(v, keys)

        result = copy.deepcopy(source)
        _blankout(result, keys)
        return result


    @staticmethod
    def get_session(args):
        plugin = cli.load_from_argparse_arguments(args)
        return session.Session(auth=plugin,
                            user_agent='openstack-seeder',
                            verify=not args.insecure)
