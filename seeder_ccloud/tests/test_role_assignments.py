import unittest, kopf
from seeder_ccloud.seed_types.role_assignments import role_assignment_validation

class TestRoleAssignments(unittest.TestCase):

    def test_validation_role(self):
        spec = {
            'role_assignments': [
                {
                    'domain': 'domain_name'
                }
            ]
        }
        self.assertRaisesRegex(kopf.AdmissionError, 'role name is mandatory', role_assignment_validation, spec, False)

    def test_validation_name(self):
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'group': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'some name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            role_assignment_validation(spec, False)
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
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'system': 'system_name',
                    'group': 'domain_name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'system': 'all',
                    'user': 'user@domain',
                }
            ]
        }
        try:
            role_assignment_validation(spec, False)
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
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'domain': 'system_name',
                    'group': 'domain@name',
                    'user': 'domain@name'
                }
            ]
        }
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'domain': 'system_name',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            role_assignment_validation(spec, False)
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
        self.assertRaises(kopf.AdmissionError, role_assignment_validation, spec, False)
        spec = {
            'role_assignments': [
                {   'role': 'role_name',
                    'project': 'project_name@domain',
                    'user': 'domain@name'
                }
            ]
        }
        try:
            role_assignment_validation(spec, False)
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
            role_assignment_validation(spec, False)
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
            role_assignment_validation(spec, False)
        except Exception as e:
            print(e)
            self.fail("should not raise error")
