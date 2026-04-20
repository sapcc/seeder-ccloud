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

import json, unittest, kopf
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.handlers.federation_mappings import FederationMappings, validate_federation_mappings
from unittest.mock import Mock


os = OpenstackHelper({})

# Mapping rules are always a JSON string — never YAML, never a Python dict.
RULES_JSON = '[{"local": [{"user": {"name": "{0}", "domain": {"name": "test-domain"}}}], "remote": [{"type": "REMOTE_USER"}]}]'
RULES_JSON_UPDATED = '[{"local": [{"user": {"name": "{0}", "domain": {"name": "test-domain-updated"}}}], "remote": [{"type": "REMOTE_USER"}]}]'

# The parsed form is what keystoneclient expects (Python list).
RULES_PARSED = json.loads(RULES_JSON)
RULES_PARSED_UPDATED = json.loads(RULES_JSON_UPDATED)


class TestFederationMappings(unittest.TestCase):

    def _make_mock(self):
        """Build a mock keystone client with federation.mappings."""
        mock_keystone = Mock()
        mock_openstack = Mock()
        mock_openstack.get_keystoneclient.return_value = mock_keystone
        mock_openstack.sanitize = os.sanitize
        return mock_openstack, mock_keystone

    def test_mapping_create(self):
        mock_openstack, mock_keystone = self._make_mock()
        mock_keystone.federation.mappings.get.side_effect = Exception("not found")
        handler = FederationMappings({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{'id': 'test-mapping', 'schema_version': '2.0', 'rules': RULES_JSON}])
        # keystoneclient receives a Python list, not a JSON string
        mock_keystone.federation.mappings.create.assert_called_with(
            'test-mapping', rules=RULES_PARSED, schema_version='2.0')

    def test_mapping_dry_run(self):
        mock_openstack, mock_keystone = self._make_mock()
        mock_keystone.federation.mappings.get.side_effect = Exception("not found")
        handler = FederationMappings({}, dry_run=True)
        handler.openstack = mock_openstack
        handler.seed([{'id': 'test-mapping', 'schema_version': '2.0', 'rules': RULES_JSON}])
        assert not mock_keystone.federation.mappings.create.called

    def test_mapping_update(self):
        mock_openstack, mock_keystone = self._make_mock()
        existing = Mock()
        existing.rules = RULES_PARSED
        existing.schema_version = '2.0'
        mock_keystone.federation.mappings.get.return_value = existing
        handler = FederationMappings({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{'id': 'test-mapping', 'schema_version': '2.0', 'rules': RULES_JSON_UPDATED}])
        mock_keystone.federation.mappings.update.assert_called_with(
            'test-mapping', rules=RULES_PARSED_UPDATED, schema_version='2.0')

    def test_mapping_no_update_when_unchanged(self):
        mock_openstack, mock_keystone = self._make_mock()
        existing = Mock()
        existing.rules = RULES_PARSED
        existing.schema_version = '2.0'
        mock_keystone.federation.mappings.get.return_value = existing
        handler = FederationMappings({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{'id': 'test-mapping', 'schema_version': '2.0', 'rules': RULES_JSON}])
        assert not mock_keystone.federation.mappings.update.called


class TestFederationMappingValidation(unittest.TestCase):

    def test_validate_missing_id(self):
        spec = {'federation_mappings': [{'rules': RULES_JSON}]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'must have an id',
            validate_federation_mappings, spec, False)

    def test_validate_missing_rules(self):
        spec = {'federation_mappings': [{'id': 'test-mapping'}]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'must have rules',
            validate_federation_mappings, spec, False)

    def test_validate_invalid_json(self):
        spec = {'federation_mappings': [{'id': 'test-mapping', 'rules': 'not valid json'}]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'valid JSON',
            validate_federation_mappings, spec, False)

    def test_validate_not_a_json_array(self):
        spec = {'federation_mappings': [{'id': 'test-mapping', 'rules': '{"not": "an array"}'}]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'JSON array',
            validate_federation_mappings, spec, False)

    def test_validate_valid(self):
        spec = {'federation_mappings': [{
            'id': 'test-mapping',
            'rules': RULES_JSON,
        }]}
        try:
            validate_federation_mappings(spec, False)
        except kopf.AdmissionError:
            self.fail("validate_federation_mappings raised AdmissionError on valid input")
