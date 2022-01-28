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

import logging, re, kopf
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from keystoneclient import exceptions

config = utils.Config()

object_name_regex = r"^([^@]+)@([^@]+)@([^@]+)$"
target_name_regex = r"^([^@]+)@([^@]+)$"


@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.rbac_policies')
def validate_rbac_policies(spec, dryrun, **_):
    rbac_policies = spec.get('rbac_policies', [])
    for rbac_policy in rbac_policies:
        if 'object_type' not in rbac_policy or not rbac_policy['object_type']:
            raise kopf.AdmissionError("Rbac-Policy must have a 'object_type' if present.")
        if rbac_policy['object_type'] != 'network':
            raise kopf.AdmissionError("Rbac-Policy 'object_type' must be set to 'network'.")
        if 'object_name' not in rbac_policy or not rbac_policy['object_name']:
            raise kopf.AdmissionError("Rbac-Policy must have a 'object_name' if present.")
        if 'target_tenant_name' not in rbac_policy or not rbac_policy['target_tenant_name']:
            raise kopf.AdmissionError("Rbac-Policy must have a 'target_tenant_name' if present.")

        match = re.match(target_name_regex, rbac_policy['target_tenant_name'])
        if match is None:
            raise kopf.AdmissionError("Rbac-Policy 'target_tenant_name' invalid value.")
        match = re.match(object_name_regex, rbac_policy['object_name'])
        if match is None:
            raise kopf.AdmissionError("Rbac-Policy 'object_name' invalid value.")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.rbac_policies')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.rbac_policies')
def seed_rbac_policies_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} rbac_policies'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        changed = utils.get_changed_seeds(old, new)
        Rbac_Policies(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Rbac_Policies():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


    def seed(self, rbac_policies):
        for rbac_policy in rbac_policies:
            self._seed_rbac_policy(rbac_policy)


    def _seed_rbac_policy(self, rbac):
        """ seed a neutron rbac-policy """

        logging.debug("seeding rbac-policy %s" % rbac)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()
        rbac = self.openstack.sanitize(rbac, ('object_type', 'object_name', 'object_id', 'action', 'target_tenant_name', 'target_tenant'))

        try:
            # network@project@domain ?
            network_id = None
            match = re.match(object_name_regex, rbac['object_name'])
            if match:
                project_id = self.openstack.get_project_id(match.group(3), match.group(2))
                if project_id:
                    network_id = self.openstack.get_network_id(project_id, match.group(1))
            if not network_id:
                logging.warn("skipping rbac-policy '%s': could not locate object_name" % rbac)
                return
            rbac['object_id'] = network_id
            rbac.pop('object_name', None)

            # project@domain ?
            project_id = None
            match = re.match(target_name_regex, rbac['target_tenant_name'])
            if match:
                project_id = self.openstack.get_project_id(match.group(2), match.group(1))
            if not project_id:
                logging.warn("skipping rbac-policy '%s': could not locate target_tenant_name" % rbac)
                return
            rbac['target_tenant'] = project_id
            rbac.pop('target_tenant_name', None)

            try:
                query = {'object_id': rbac['object_id'], 'object_type': rbac['object_type'], 'action': rbac['action'],
                        'target_tenant': rbac['target_tenant']}
                result = neutron.list_rbac_policies(retrieve_all=True, **query)
            except exceptions.NotFound:
                result = None

            if not result or not result['rbac_policies']:
                body = {'rbac_policy': rbac.copy()}

                logging.info("create rbac-policy '%s'" % rbac)
                if not self.dry_run:
                    neutron.create_rbac_policy(body=body)

        except Exception as e:
            logging.error("could not seed rbac-policy %s: %s" % (rbac, e))
            raise