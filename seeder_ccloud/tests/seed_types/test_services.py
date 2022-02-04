import unittest, kopf
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.handlers.services import Services
from unittest.mock import patch
from keystoneclient.v3.services import Service


os = OpenstackHelper({})
class TestServices(unittest.TestCase):
    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.services.ServiceManager')
    def test_service_create(self, openstack_mock, service_mock):
        service_mock.services.list.return_value = None
        openstack_mock.get_keystoneclient.return_value = service_mock
        openstack_mock.sanitize = os.sanitize
        s = Services({}, False)
        s.openstack = openstack_mock
        s.seed([{'name': 'service_name', 'type': 'type_name', 'enabled': True, 'description': 'descr'}])
        service_mock.services.create.assert_called_with(type='type_name', name='service_name', enabled=True, description='descr')

    
    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.services.ServiceManager')
    def test_services_dry_run(self, openstack_mock, service_mock):
        service_mock.roles.list.return_value = None
        openstack_mock.get_keystoneclient.return_value = service_mock
        openstack_mock.sanitize = os.sanitize
        s = Services({}, True)
        s.openstack = openstack_mock
        s.seed([{'name': 'service_name', 'type': 'type_name'}])
        assert not service_mock.services.create.called


    @patch('seeder_ccloud.openstack.openstack_helper')
    @patch('keystoneclient.v3.services.ServiceManager')
    def test_role_update(self, openstack_mock, service_mock):
        svc = Service(None, {'id' :'1', 'name': 'service_name', 'description': 'descr', 'type': 'type_name', 'enabled': True})
        service_mock.services.list.return_value = [svc]
        openstack_mock.get_keystoneclient.return_value = service_mock
        openstack_mock.sanitize = os.sanitize
        r = Services({}, False)
        r.openstack = openstack_mock
        r.seed([{'name': 'service_name', 'description': 'descr', 'type': 'type_name', 'enabled': False}])
        service_mock.services.update.assert_called_once()
