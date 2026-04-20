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

import json, logging, kopf, time
from datetime import timedelta, datetime
from deepdiff import DeepDiff
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils

config = utils.Config()


@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.federation_mappings')
def validate_federation_mappings(spec, dryrun, **_):
    mappings = spec.get('federation_mappings', [])
    for mapping in mappings:
        if 'id' not in mapping or not mapping['id']:
            raise kopf.AdmissionError("Federation mapping must have an id.")
        if 'rules' not in mapping or not mapping['rules']:
            raise kopf.AdmissionError("Federation mapping must have rules.")
        rules = mapping['rules']
        if isinstance(rules, str):
            try:
                parsed = json.loads(rules)
                if not isinstance(parsed, list):
                    raise kopf.AdmissionError("Federation mapping rules must be a JSON array.")
            except json.JSONDecodeError as e:
                raise kopf.AdmissionError("Federation mapping rules must be valid JSON: %s" % e)


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.federation_mappings')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.federation_mappings')
def seed_federation_mappings_handler(memo: kopf.Memo, patch: kopf.Patch, new, old, name, annotations, **_):
    logging.info('seeding {} federation_mappings'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        starttime = time.perf_counter()
        changed = utils.get_changed_seeds(old, new)
        diffs = FederationMappings(memo['args'], memo['dry_run']).seed(changed)
        duration = timedelta(seconds=time.perf_counter()-starttime)
        utils.setStatusFields('federation_mappings', patch, 'seeded', duration=duration, diffs=diffs)
    except Exception as error:
        utils.setStatusFields('federation_mappings', patch, 'error', 0, latest_error=str(error))
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
    finally:
        patch.status['latest_reconcile'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')


class FederationMappings():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)
        self.diffs = {}

    def seed(self, federation_mappings):
        logging.info('seeding federation mappings')
        for mapping in federation_mappings:
            self._seed_mapping(mapping)
        return self.diffs

    @staticmethod
    def _parse_rules(rules):
        """Parse mapping rules from JSON string to Python list.

        Mapping rules are always stored and transmitted as a JSON string.
        They are only parsed to a Python list at the point of calling the
        Keystone API (which expects a Python list).
        """
        if isinstance(rules, str):
            return json.loads(rules)
        return rules

    def _seed_mapping(self, mapping):
        """Seed a Keystone federation mapping."""
        mapping_id = mapping['id']
        rules = self._parse_rules(mapping['rules'])
        schema_version = mapping.get('schema_version', '2.0')
        logging.debug("seeding federation mapping %s" % mapping_id)

        keystone = self.openstack.get_keystoneclient()

        try:
            resource = keystone.federation.mappings.get(mapping_id)
            # Mapping exists, check if rules or schema_version changed
            existing_rules = getattr(resource, 'rules', [])
            existing_sv = getattr(resource, 'schema_version', '')
            diff = DeepDiff(existing_rules, rules, threshold_to_diff_deeper=0)
            if diff or existing_sv != schema_version:
                logging.info("update federation mapping '%s': %s" % (mapping_id, diff))
                self.diffs[mapping_id] = str(diff)
                if not self.dry_run:
                    keystone.federation.mappings.update(
                        mapping_id, rules=rules, schema_version=schema_version)
        except Exception:
            # Mapping does not exist, create it
            logging.info("create federation mapping '%s'" % mapping_id)
            self.diffs[mapping_id] = 'created'
            if not self.dry_run:
                keystone.federation.mappings.create(
                    mapping_id, rules=rules, schema_version=schema_version)
