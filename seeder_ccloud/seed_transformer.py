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

def transform(patch, spec):
    groups = []
    projects = []
    role_assignments = []
    users = []
    project_seed_types = {}
    if 'openstack' not in patch.spec:
        patch.spec['openstack'] = {}

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

    if spec['domains']:
        new_domains = [x for x in spec['domains'] if len(x.keys()) > 1 or not x.keys() >= {'name'}]
        if new_domains:
            patch.spec['openstack']['domains'] = new_domains
    if projects:
        new_projects = [x for x in projects if len(x.keys()) > 2 or not x.keys() >= {'name', 'domain'}]
        if new_projects:
            patch.spec['openstack']['projects'] = new_projects
    if groups:
        patch.spec['openstack']['groups'] = groups
    if role_assignments:
        patch.spec['openstack']['role_assignments'] = role_assignments

    if project_seed_types:
        patch.spec['openstack'].update(project_seed_types)


def mutate_project(project, project_seed_types):
    for name, seed_type in project.items():
        if name not in project_extract_types:
            continue
        if name == 'network_quota':
            rename = 'network_quotas'
            if rename not in project_seed_types:
                project_seed_types[rename] = []
            seed_type['domain'] = project['domain']
            seed_type['project'] = project['name']
            project_seed_types[rename].append(seed_type)
            continue

        for seed in seed_type:
            seed['domain'] = project['domain']
            seed['project'] = project['name']
            if name == 'address_scopes':
                mutate_address_scopes(seed, project_seed_types)
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

    address_scope.pop('subnet_pools', None)