import unittest, kopf
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seed_types.roles import Roles
from unittest.mock import patch, Mock
from keystoneclient.v3.roles import Role


os = OpenstackHelper({})
class TestRoles(unittest.TestCase):
    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.roles.RoleManager')
    def test_role_create(self, openstack_mock, roles_mock):
        roles_mock.roles.list.return_value = None
        openstack_mock.get_keystoneclient.return_value = roles_mock
        openstack_mock.sanitize = os.sanitize
        r = Roles({}, False)
        r.openstack = openstack_mock
        r.seed([{'name': 'role_name', 'domainId': '1234'}])
        roles_mock.roles.create.assert_called_with(name='role_name', domainId='1234')

    
    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.roles.RoleManager')
    def test_role_dry_run(self, openstack_mock, roles_mock):
        roles_mock.roles.list.return_value = None
        openstack_mock.get_keystoneclient.return_value = roles_mock
        openstack_mock.sanitize = os.sanitize
        r = Roles({}, True)
        r.openstack = openstack_mock
        r.seed([{'name': 'role_name', 'domainId': '1234'}])
        assert not roles_mock.roles.create.called


    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.roles.RoleManager')
    def test_role_update(self, openstack_mock, roles_mock):
        role = Role(None, {'id' :'1', 'name': 'role_name', 'description': 'old', 'domainId': '1234'})
        roles_mock.roles.list.return_value = [role]
        openstack_mock.get_keystoneclient.return_value = roles_mock
        openstack_mock.sanitize = os.sanitize
        r = Roles({}, False)
        r.openstack = openstack_mock
        r.seed([{'name': 'role_name', 'domainId': '1234', 'description': 'new'}])
        roles_mock.roles.update.assert_called_once()
