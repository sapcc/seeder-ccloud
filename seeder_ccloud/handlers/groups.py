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
import logging, kopf, time
from datetime import timedelta, datetime
from deepdiff import DeepDiff
from keystoneclient import exceptions
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.groups')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.groups')
def seed_groups_handler(memo: kopf.Memo, patch: kopf.Patch, new, old, name, annotations, **_):
    logging.info('seeding {} groups'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        starttime = time.perf_counter()
        changed = utils.get_changed_seeds(old, new)
        diffs = Groups(memo['args'], memo['dry_run']).seed(changed)
        duration = timedelta(seconds=time.perf_counter()-starttime)
        utils.setStatusFields('groups', patch, 'seeded', duration=duration, diffs=diffs)
        logging.info('seeding {} groups done'.format(name))
    except Exception as error:
        logging.error('error seeding {}: {}'.format(name, error))
        utils.setStatusFields('groups', patch, 'error', 0, latest_error=str(error))
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
    finally:
        patch.status['latest_reconcile'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

class Groups():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.group_members = {}
        self.dry_run = dry_run


    def seed(self, groups):
        self.diffs = {}
        for group in groups:
            self._seed_groups(group)
        self.resolve_group_members()
        return self.diffs


    def _seed_groups(self, group):
        """ seed keystone groups """
        self.diffs[group['name']] = []
        domain_name = group['domain']
        domain_id = self.openstack.get_domain_id(domain_name)
        
        logging.debug("seeding groups %s %s" % (domain_name, group))

        keystone = self.openstack.get_keystoneclient()

        users = group.get('users', [])

        group = self.openstack.sanitize(group, ('name', 'description'))
        result = keystone.groups.list(domain=domain_id,
                                    name=group['name'])
        if not result:
            logging.info(
                "create group '%s/%s'" % (domain_name, group['name']))
            if not self.dry_run:
                self.diffs[group['name']].append('create')
                resource = keystone.groups.create(domain=domain_id, **group)
        else:
            resource = result[0]
            diff = DeepDiff(group, resource.to_dict(), threshold_to_diff_deeper=0)
            if 'values_changed' in diff:
                logging.debug("group %s differs: '%s'" % (group['name'], diff))
                if not self.dry_run:
                    self.diffs[group['name']].append(diff['values_changed'])
                    keystone.groups.update(resource.id, **group)

        if users:
            for user in users:
                if resource.id not in self.group_members:
                    self.group_members[resource.id] = []
                if '@' in user:
                    self.group_members[resource.id].append(user)
                else:
                    self.group_members[resource.id].append(
                        '%s@%s' % (user, domain_name))


    def resolve_group_members(self):
        for group, users in self.group_members.items():
            logging.debug("resolving group members %s %s" % (group, users))
            keystoneclient = self.get_keystoneclient()
            for uid in users:
                username, domain = uid.split('@')
                user = self.get_user_id(domain, username, keystoneclient)
                if user:
                    try:
                        keystoneclient.users.check_in_group(user, group)
                    except exceptions.NotFound:
                        logging.info(
                            "add user '%s' to group '%s'" % (uid, group))
                        keystoneclient.users.add_to_group(user, group)
                else:
                    logging.warn(
                        "could not add user '%s' to group '%s'" % (
                            uid, group))
