import kopf
from seeder_ccloud import utils


config = utils.Config()
project_extract_types = [
    'address_scopes',
    'bgpvpns',
    'dns_zones',
    'endpoints',
    'network_quota',
    'networks',
    'projects',
    'routers',
    'swift',
]
@kopf.on.mutate(config.crd_info['plural'], annotations={'legacy': 'True', 'operatorVersion': config.operator_version}, field='spec.domains')
def mutate_domains(patch: kopf.Patch, spec, **kwargs):
    groups = []
    projects = []
    role_assignments = []
    users = []
    project_seed_types = {}
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
            mutate_project(project, project_seed_types)     
        projects = projects + _projects

    patch.spec['domains'] = spec['domains']
    patch.spec['projects'] = projects
    patch.spec['groups'] = groups
    patch.spec['role_assignments'] = role_assignments

    patch.spec.update(project_seed_types)

    # make sure we do not mutate again!
    patch.metadata.annotations['legacy'] = 'False'


def mutate_project(project, project_seed_types):
    for name, seed_type in project.items():
        if name not in project_extract_types:
            continue
        for seed in seed_type:
            seed['domain'] = project['domain']
            seed['project'] = project['name']
        if name == 'address_scopes':
            mutate_address_scopes(seed_type, project_seed_types)
        if name == 'network_quota':
            name = 'network_quotas'
        if name not in project_seed_types:
            project_seed_types[name] = []
        project_seed_types[name] = project_seed_types[name] + project.get(name, [])

    for p in project_extract_types:
        project.pop(p, None)


def mutate_address_scopes(address_scope, project_seed_types):
    for name, seed_type in address_scope.items():
        if name != 'subnet_pools':
            continue
        for seed in seed_type:
            seed['domain'] = address_scope['domain']
            seed['project'] = address_scope['name']
        if name not in project_seed_types:
            project_seed_types[name] = []
        project_seed_types[name] = project_seed_types[name] + address_scope.get(name, [])

    for p in address_scope_extract_types:
        address_scope.pop(p, None)