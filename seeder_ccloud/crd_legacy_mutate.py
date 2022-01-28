import kopf
from seeder_ccloud import utils


config = utils.Config()

@kopf.on.mutate(config.crd_info['plural'], annotations={'legacy': 'True', 'operatorVersion': config.operator_version}, field='spec.domains')
def mutate_domains(patch: kopf.Patch, spec, **kwargs):
    groups = []
    projects = []
    role_assignments = []
    users = []
    for domain in spec['domains']:
        _groups = domain.pop('groups', [])
        _projects = domain.pop('projects', [])
        _users = domain.pop('users', [])
        
        for user in _users:
            if '@' not in user['name']:
                user['name'] = '{}@{}'.format(user['name'], domain['name'])
            else:
                user['domain'] = domain['name']
        users = users + _users
        
        for group in _groups:
            group['domain'] = domain['name']
            _role_assigns = group.pop('role_assignments', [])
            for role_assign in _role_assigns:
                role_assign['group'] = '{}@{}'.format(group['name'], domain['name'])
                if 'project' in role_assign:
                    if '@' not in role_assign['project']:
                        role_assign['project'] = '{}@{}'.format(role_assign['project'], domain['name'])
            role_assignments = role_assignments + _role_assigns
        groups = groups + _groups
        
        for project in _projects:
            project['domain'] = domain['name']      
        projects = projects + _projects

    patch.spec['domains'] = spec['domains']
    patch.spec['projects'] = projects
    patch.spec['groups'] = groups
    patch.spec['role_assignments'] = role_assignments
    # make sure we do not mutate again!
    patch.metadata.annotations['legacy'] = 'False'


def mutate_project():
    #address_scopes
    #bgpvpns
    #dns_zones
    #endpoints
    #network_quotes
    #networks
    #projects
    #routers
    #subnet_pools
    #swift
    pass