import copy
from datetime import datetime, timedelta
import threading 

from cachetools import cached, TTLCache
from keystoneclient.v3 import client as keystoneclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient
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

        return cls._singleton
    

    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_keystoneclient(self):
        session = self.get_session(self.args)
        return keystoneclient.Client(session=session,
                                     interface=self.args.interface)


    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_neutronclient(self):
        session = self.get_session(self.args)
        return neutronclient.Client(session=session,
                                    interface=self.args.interface)


    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_novaclient(self):
        session = self.get_session(self.args)
        return novaclient.Client("2.1", session=session,
                                 endpoint_type=self.args.interface + 'URL')

    
    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_cinderclient(self, api_version="3.50"):
        session = self.get_session(self.args)
        return cinderclient.Client(session=session, 
                                   interface=self.args.interface, api_version=api_version)

                            
    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_manilaclient(self, api_version="2.40"):
        session = self.get_session(self.args)
        api_version = api_versions.APIVersion(api_version)
        return manilaclient.Client(session=session, api_version=api_version)

    
    def get_placementclient(self, api_version='1.6'):
        session = self.get_session(self.args)
        ks_filter = {'service_type': 'placement', 'interface': self.args.interface}
        return placementclient(session=session, ks_filter=ks_filter, api_version=api_version)


    @cached(cache=TTLCache(maxsize=1, ttl=300))
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

        designate = designateclient.Client(session=sess,
                                        endpoint_type=args.interface + 'URL',
                                        all_projects=True)

    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def get_traits(self, only_associated=False):
        """
        Return the list of all traits that have been set on at least one resource provider.
        """
        try:
            params = {'associated': 'true'} if only_associated else {}
            url_params = '&'.join(f'{k}={v}' for k, v in params.items())
            result = self.get_placementclient().request('GET', f'/traits?{url_params}')
        except Exception as e:
            logging.error("Failed checking for trait resource providers: {}".format(e))
            return []
        return result.json().get("traits", [])


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_role_id(self, name):
        """ get a (cached) role-id for a role name """
        roles = self.get_keystoneclient().roles.list(name=name)
        if roles:
            return roles[0].id
        else:
            # returning none would be saved in the cache as well
            raise Exception("role {0} not found".format(name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_domain_id(self, name):
        """ get a (cached) domain-id for a domain name """
        domains = self.keystone.domains.list(name=name)
        if domains:
            return domains[0].id
        else:
            raise Exception("domain {0} not found".format(name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_project_id(self, domain, name):
        """ get a (cached) project-id for a domain and project name """
        projects = self.keystone.projects.list(
            domain=self.get_domain_id(domain),
            name=name)
        if projects:
            return projects[0].id
        else:
            raise Exception("project %s/%s not found".format(domain, name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_user_id(self, domain, name):
        """ get a (cached) user-id for a domain and user name """
        users = self.keystone.users.list(
            domain=self.get_domain_id(domain),
            name=name)
        if users:
            return users[0].id
        else:
            raise Exception("user %s/%s not found".format(domain, name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_group_id(self, domain, name):
        """ get a (cached) group-id for a domain and group name """
        groups = self.keystone.groups.list(
            domain=self.get_domain_id(domain),
            name=name)
        if groups:
           return groups[0].id
        else:
           raise Exception("group %s/%s not found".format(domain, name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_subnetpool_id(self, project_id, name):
        """ get a (cached) subnetpool-id for a project-id and subnetpool name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.neutron.list_subnetpools(retrieve_all=True, **query)
        if result and result['subnetpools']:
            return result['subnetpools'][0]['id']
        else:
            raise Exception("subnetpool %s/%s not found".format(project_id, name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_network_id(self, project_id, name):
        """ get a (cached) network-id for a project-id and network name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.neutron.list_networks(retrieve_all=True, **query)
        if result and result['networks']:
            return result['networks'][0]['id']     
        else:
            raise Exception("network %s/%s not found".format(project_id, name))


    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    def get_subnet_id(self, project_id, name):
        """ get a (cached) subnet-id for a project-id and subnet name """
        query = {'tenant_id': project_id, 'name': name}
        result = self.neutron.list_subnets(retrieve_all=True, **query)
        if result and result['subnets']:
            return result['subnets'][0]['id']
        else:
            raise Exception("subnet %s/%s not found".format(project_id, name))


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


    @staticmethod
    def redact(source,
           keys=('password', 'secret', 'userPassword', 'cam_password')):
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