"""
 Copyright 2025 SAP SE
 
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
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils

config = utils.Config()


@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.identity_providers')
def validate_identity_providers(spec, dryrun, **_):
    identity_providers = spec.get('identity_providers', [])
    for idp in identity_providers:
        if 'id' not in idp or not idp['id']:
            raise kopf.AdmissionError("Identity provider must have an id.")
        protocols = idp.get('protocols', [])
        for protocol in protocols:
            if 'id' not in protocol or not protocol['id']:
                raise kopf.AdmissionError("Protocol must have an id.")
            if 'mapping_id' not in protocol or not protocol['mapping_id']:
                raise kopf.AdmissionError("Protocol must have a mapping_id.")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.identity_providers')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.identity_providers')
def seed_identity_providers_handler(memo: kopf.Memo, patch: kopf.Patch, new, old, name, annotations, **_):
    logging.info('seeding {} identity_providers'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        starttime = time.perf_counter()
        changed = utils.get_changed_seeds(old, new)
        diffs = IdentityProviders(memo['args'], memo['dry_run']).seed(changed)
        duration = timedelta(seconds=time.perf_counter()-starttime)
        utils.setStatusFields('identity_providers', patch, 'seeded', duration=duration, diffs=diffs)
    except Exception as error:
        utils.setStatusFields('identity_providers', patch, 'error', 0, latest_error=str(error))
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
    finally:
        patch.status['latest_reconcile'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')


class IdentityProviders():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)
        self.diffs = {}

    def seed(self, identity_providers):
        logging.info('seeding identity providers')
        for idp in identity_providers:
            self._seed_identity_provider(idp)
        return self.diffs

    def _seed_identity_provider(self, idp):
        """Seed a Keystone identity provider with optional nested protocols."""
        logging.debug("seeding identity provider %s" % idp.get('id'))

        # Extract nested protocols before sanitizing the parent
        protocols = idp.get('protocols', [])

        idp_id = idp['id']
        idp_data = self.openstack.sanitize(idp,
                        ('description', 'enabled', 'remote_ids'))

        keystone = self.openstack.get_keystoneclient()

        try:
            resource = keystone.federation.identity_providers.get(idp_id)
            # IdP exists, check for differences
            existing = {
                'description': getattr(resource, 'description', ''),
                'enabled': getattr(resource, 'enabled', True),
                'remote_ids': getattr(resource, 'remote_ids', []),
            }
            diff = DeepDiff(existing, idp_data, threshold_to_diff_deeper=0)
            if diff:
                logging.info("update identity provider '%s': %s" % (idp_id, diff))
                self.diffs[idp_id] = str(diff)
                if not self.dry_run:
                    keystone.federation.identity_providers.update(idp_id, **idp_data)
        except Exception:
            # IdP does not exist, create it
            logging.info("create identity provider '%s'" % idp_id)
            self.diffs[idp_id] = 'created'
            if not self.dry_run:
                keystone.federation.identity_providers.create(idp_id, **idp_data)

        if protocols:
            self._seed_protocols(idp_id, protocols)

    def _seed_protocols(self, idp_id, protocols):
        """Seed federation protocols for an identity provider."""
        keystone = self.openstack.get_keystoneclient()

        for protocol in protocols:
            protocol_id = protocol['id']
            mapping_id = protocol['mapping_id']

            try:
                resource = keystone.federation.protocols.get(idp_id, protocol_id)
                # Protocol exists, check if mapping changed
                if getattr(resource, 'mapping_id', '') != mapping_id:
                    logging.info("update protocol '%s/%s' mapping to '%s'" % (
                        idp_id, protocol_id, mapping_id))
                    self.diffs['%s/%s' % (idp_id, protocol_id)] = 'mapping updated'
                    if not self.dry_run:
                        keystone.federation.protocols.update(
                            idp_id, protocol_id, mapping_id)
            except Exception:
                # Protocol does not exist, create it
                logging.info("create protocol '%s/%s' with mapping '%s'" % (
                    idp_id, protocol_id, mapping_id))
                self.diffs['%s/%s' % (idp_id, protocol_id)] = 'created'
                if not self.dry_run:
                    keystone.federation.protocols.create(
                        protocol_id, idp_id, mapping_id)
