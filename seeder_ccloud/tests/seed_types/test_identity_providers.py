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

import unittest, kopf
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.handlers.identity_providers import IdentityProviders, validate_identity_providers
from unittest.mock import patch, Mock


os = OpenstackHelper({})

class TestIdentityProviders(unittest.TestCase):

    def _make_mock(self):
        """Build a mock keystone client with federation.identity_providers and federation.protocols."""
        mock_keystone = Mock()
        mock_openstack = Mock()
        mock_openstack.get_keystoneclient.return_value = mock_keystone
        mock_openstack.sanitize = os.sanitize
        return mock_openstack, mock_keystone

    def test_idp_create(self):
        mock_openstack, mock_keystone = self._make_mock()
        mock_keystone.federation.identity_providers.get.side_effect = Exception("not found")
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Test IdP',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
        }])
        mock_keystone.federation.identity_providers.create.assert_called_with(
            'test-idp',
            description='Test IdP',
            enabled=True,
            remote_ids=['https://idp.example.com/metadata'],
        )

    def test_idp_dry_run(self):
        mock_openstack, mock_keystone = self._make_mock()
        mock_keystone.federation.identity_providers.get.side_effect = Exception("not found")
        handler = IdentityProviders({}, dry_run=True)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Test IdP',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
        }])
        assert not mock_keystone.federation.identity_providers.create.called

    def test_idp_update(self):
        mock_openstack, mock_keystone = self._make_mock()
        existing = Mock()
        existing.description = 'Old description'
        existing.enabled = True
        existing.remote_ids = ['https://idp.example.com/metadata']
        mock_keystone.federation.identity_providers.get.return_value = existing
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'New description',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
        }])
        mock_keystone.federation.identity_providers.update.assert_called_once()

    def test_idp_no_update_when_unchanged(self):
        mock_openstack, mock_keystone = self._make_mock()
        existing = Mock()
        existing.description = 'Same description'
        existing.enabled = True
        existing.remote_ids = ['https://idp.example.com/metadata']
        mock_keystone.federation.identity_providers.get.return_value = existing
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Same description',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
        }])
        assert not mock_keystone.federation.identity_providers.update.called

    def test_protocol_create(self):
        mock_openstack, mock_keystone = self._make_mock()
        # IdP exists
        existing_idp = Mock()
        existing_idp.description = 'Test'
        existing_idp.enabled = True
        existing_idp.remote_ids = ['https://idp.example.com/metadata']
        mock_keystone.federation.identity_providers.get.return_value = existing_idp
        # Protocol does not exist
        mock_keystone.federation.protocols.get.side_effect = Exception("not found")
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Test',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
            'protocols': [{'id': 'saml2', 'mapping_id': 'test-mapping'}],
        }])
        mock_keystone.federation.protocols.create.assert_called_with(
            'saml2', 'test-idp', 'test-mapping')

    def test_protocol_update(self):
        mock_openstack, mock_keystone = self._make_mock()
        # IdP exists
        existing_idp = Mock()
        existing_idp.description = 'Test'
        existing_idp.enabled = True
        existing_idp.remote_ids = ['https://idp.example.com/metadata']
        mock_keystone.federation.identity_providers.get.return_value = existing_idp
        # Protocol exists with different mapping
        existing_protocol = Mock()
        existing_protocol.mapping_id = 'old-mapping'
        mock_keystone.federation.protocols.get.return_value = existing_protocol
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Test',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
            'protocols': [{'id': 'saml2', 'mapping_id': 'new-mapping'}],
        }])
        mock_keystone.federation.protocols.update.assert_called_with(
            'test-idp', 'saml2', 'new-mapping')

    def test_protocol_no_update_when_unchanged(self):
        mock_openstack, mock_keystone = self._make_mock()
        existing_idp = Mock()
        existing_idp.description = 'Test'
        existing_idp.enabled = True
        existing_idp.remote_ids = ['https://idp.example.com/metadata']
        mock_keystone.federation.identity_providers.get.return_value = existing_idp
        existing_protocol = Mock()
        existing_protocol.mapping_id = 'test-mapping'
        mock_keystone.federation.protocols.get.return_value = existing_protocol
        handler = IdentityProviders({}, dry_run=False)
        handler.openstack = mock_openstack
        handler.seed([{
            'id': 'test-idp',
            'description': 'Test',
            'enabled': True,
            'remote_ids': ['https://idp.example.com/metadata'],
            'protocols': [{'id': 'saml2', 'mapping_id': 'test-mapping'}],
        }])
        assert not mock_keystone.federation.protocols.update.called


class TestIdentityProviderValidation(unittest.TestCase):

    def test_validate_missing_id(self):
        spec = {'identity_providers': [{'description': 'no id'}]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'must have an id',
            validate_identity_providers, spec, False)

    def test_validate_missing_protocol_id(self):
        spec = {'identity_providers': [{
            'id': 'test-idp',
            'protocols': [{'mapping_id': 'test-mapping'}],
        }]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'Protocol must have an id',
            validate_identity_providers, spec, False)

    def test_validate_missing_protocol_mapping_id(self):
        spec = {'identity_providers': [{
            'id': 'test-idp',
            'protocols': [{'id': 'saml2'}],
        }]}
        self.assertRaisesRegex(
            kopf.AdmissionError,
            'must have a mapping_id',
            validate_identity_providers, spec, False)

    def test_validate_valid(self):
        spec = {'identity_providers': [{
            'id': 'test-idp',
            'protocols': [{'id': 'saml2', 'mapping_id': 'test-mapping'}],
        }]}
        try:
            validate_identity_providers(spec, False)
        except kopf.AdmissionError:
            self.fail("validate_identity_providers raised AdmissionError on valid input")
