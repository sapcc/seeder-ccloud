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
from typing import List
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from deepdiff import DeepDiff

config = utils.Config()


@kopf.on.validate(config.crd_info['plural'],
                  annotations={'operatorVersion': config.operator_version},
                  field='spec.openstack.network_quotas')
def validate_network_quotas(memo: kopf.Memo, dryrun, spec, old,
                            warnings: List[str], **_):
    network_quotas = spec['openstack'].get('network_quotas', [])

    if dryrun and network_quotas:
        old_network_quotas = None
        if old is not None:
            old_network_quotas = old['spec']['openstack'].get(
                'address_scopes', None)
        try:
            changed = utils.get_changed_seeds(old_network_quotas,
                                              network_quotas)
            diffs = Network_Quotas(memo['args'], dryrun).seed(changed)
            if diffs:
                warnings.append({'address_scopes': diffs})
        except Exception as e:
            raise kopf.AdmissionError(e)


@kopf.on.update(config.crd_info['plural'],
                annotations={'operatorVersion': config.operator_version},
                field='spec.openstack.network_quotas')
@kopf.on.create(config.crd_info['plural'],
                annotations={'operatorVersion': config.operator_version},
                field='spec.openstack.network_quotas')
def seed_network_quotas_handler(memo: kopf.Memo, new, old, name, annotations,
                                **_):
    logging.info('seeding {} network_quotas'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(
            name, 'dependencies error'),
                                  delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Network_Quotas(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error),
                                  delay=30)


class Network_Quotas():

    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run

    def seed(self, network_quotas):
        self.diffs = {}

        keystone = self.openstack.get_keystoneclient()
        limes = keystone.services.list(name='limes')
        # only seed network quota if limes is not available
        if len(limes):
            logging.info(
                "network_quotas will not be seeded when Limes service is available in that region"
            )
            return self.diffs

        for network_quota in network_quotas:
            try:
                self._seed_network_quota(network_quota)
            except Exception as e:
                raise Exception(f"network-quota. error: {e}")

        return self.diffs

    def _seed_network_quota(self, network_quota):
        """
        seed a projects network quota
        """
        project_id = self.openstack.get_project_id(network_quota['domain'],
                                                   network_quota['project'])
        project_name = network_quota['project']
        logging.debug("seeding network-quota of project %s" % project_name)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()
        self.diffs[network_quota['name']] = []

        quota = self.openstack.sanitize(
            network_quota,
            ('floatingip', 'healthmonitor', 'l7policy', 'listener',
             'loadbalancer', 'network', 'pool', 'port', 'rbac_policy',
             'router', 'security_group', 'security_group_rule', 'subnet',
             'subnetpool', 'bgpvpn'))

        body = {'quota': quota.copy()}
        result = neutron.show_quota(project_id)
        if not result or not result['quota']:
            logging.info("set project %s network quota to '%s'" %
                         (project_name, quota))
            self.diffs[network_quota['name']].append('create')
            if not self.dry_run:
                neutron.update_quota(project_id, body)
        else:
            resource = result['quota']
            new_quota = {}
            diff = DeepDiff(resource, quota, threshold_to_diff_deeper=0)
            if 'values_changed' in diff or 'dictionary_item_added' in diff:
                self.diffs[network_quota['name']].append(
                    diff['values_changed'])
                logging.info(
                    f"network_quotas {network_quota['domain']}/{network_quota['project']} differs."
                )
                for attr in list(quota.keys()):
                    if int(quota[attr]) > int(resource.get(attr, '')):
                        logging.info(
                            "%s differs. set project %s network quota to '%s'"
                            % (attr, project_name, quota[attr]))
                        new_quota[attr] = quota[attr]

                self.diffs[network_quota['name']].append(
                    diff.get('values_changed', {}))
                self.diffs[network_quota['name']].append(
                    diff.get('dictionary_item_added', {}))
                if len(new_quota) and not self.dry_run:
                    neutron.update_quota(project_id, {'quota': new_quota})
