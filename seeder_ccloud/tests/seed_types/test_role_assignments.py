import unittest, kopf
from seeder_ccloud.handlers.role_assignments import validate_role_assignments, Role_Assignments
from unittest.mock import patch, Mock
from keystoneclient import exceptions


class TestRoleAssignments(unittest.TestCase):
    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.roles.RoleManager')
    def test_role_assignment(self, openstack_mock, roles_mock):
        openstack_mock.get_role_id.return_value = '1234'
        openstack_mock.get_user_id.return_value = '2233'
        openstack_mock.get_keystoneclient.return_value = roles_mock
        ra = Role_Assignments({}, True)
        ra.openstack = openstack_mock
        ra.seed([{'role': 'role_name', 'user': 'user_name@domain_name'}])
        roles_mock.roles.check.assert_called_with('1234', user= '2233')
        openstack_mock.get_user_id.assert_called_with('domain_name', 'user_name')


    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.roles.RoleManager')
    def test_role_assignment_grant(self, openstack_mock, roles_mock):
        roles_mock.roles.check.side_effect = exceptions.NotFound
        openstack_mock.get_role_id.return_value = '1234'
        openstack_mock.get_user_id.return_value = '2233'
        openstack_mock.get_keystoneclient.return_value = roles_mock
        ra = Role_Assignments({}, False)
        ra.openstack = openstack_mock
        ra.seed([{'role': 'role_name', 'user': 'user_name@domain_name'}])
        roles_mock.roles.check.assert_called_with('1234', user= '2233')
        roles_mock.roles.grant.assert_called_with('1234', user= '2233')


    def test_validation_role(self):
        spec = {
            'role_assignments': [
                {
                    'domain': 'domain_name'
                }
            ]
        }
        self.assertRaisesRegex(kopf.AdmissionError, 'role name is mandatory', validate_role_assignments, spec, False)

    def test_validation_name(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'group': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'some name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            self.fail("should not raise error")

    def test_validation_system(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'system': 'system_name',
                    'domain': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'system': 'system_name',
                    'group': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'system': 'all',
                    'user': 'user@domain',
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            self.fail("should not raise error: {}".format(e))

    def test_validation_domain(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'project': 'system_name',
                    'domain': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'domain': 'system_name',
                    'group': 'domain@name',
                    'user': 'domain@name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'domain': 'system_name',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            self.fail("should not raise error")

    def test_validation_project(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'project': 'project_name@domain',
                    'group': 'domain@name',
                    'user': 'domain@name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, validate_role_assignments, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'project': 'project_name@domain',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            print(e)
            self.fail("should not raise error")

    def test_validation_user(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            print(e)
            self.fail("should not raise error")
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'domain@name',
                    'system': 'all',
                }
            ]
        }
        try:
            validate_role_assignments(spec, False)
        except Exception as e:
            print(e)
            self.fail("should not raise error")
