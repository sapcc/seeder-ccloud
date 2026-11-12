import copy
import importlib
import json
import logging
from types import SimpleNamespace
import unittest
from unittest import mock

import kopf
from keystoneclient import exceptions
from kopf._cogs.structs import bodies, diffs, patches, references
from kopf._core.actions import lifecycles
from kopf._core.intents import causes
from kopf._core.reactor import inventory, processing

from seeder_ccloud import utils


def resource_ref(**values):
    return SimpleNamespace(
        **values, to_dict=lambda: copy.deepcopy(values))


def merge_patch(target, patch):
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            merge_patch(target.setdefault(key, {}), value)
        else:
            target[key] = copy.deepcopy(value)


class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.args = SimpleNamespace(max_workers=1)
        config = SimpleNamespace(
            crd_info={'plural': 'ccloudseeds'}, operator_version='1.0',
            prefix='seeder.ccloud', get_args=lambda: self.args,
            is_dependency_successful=lambda annotations: True)

        # Import the real callbacks without parsing the test runner's arguments
        # or adding handlers to another test's registry.
        previous_registry = kopf.get_default_registry()
        kopf.set_default_registry(kopf.OperatorRegistry())
        try:
            with mock.patch.object(utils, 'Config', return_value=config):
                self.seeder = importlib.import_module(
                    'seeder_ccloud.operator.seeder')
                self.domains = importlib.import_module(
                    'seeder_ccloud.handlers.domains')
                self.assignments = importlib.import_module(
                    'seeder_ccloud.handlers.role_assignments')
        finally:
            kopf.set_default_registry(previous_registry)
        for module in (self.seeder, self.domains, self.assignments):
            self.patch_object(module, 'config', config)

        self.registry = kopf.OperatorRegistry()
        for field, fn in (
                ('domains', self.domains.seed_domains_handler),
                ('role_assignments',
                 self.assignments.seed_role_assignments_handler)):
            for decorator in (kopf.on.create, kopf.on.update):
                decorator('seeder.cloud.sap', 'v1', 'ccloudseeds',
                          field='spec.openstack.' + field,
                          registry=self.registry)(fn)

        self.settings = kopf.OperatorSettings()
        with mock.patch.object(
                self.seeder.k8s_config, 'load_kube_config',
                side_effect=self.seeder.k8s_config.ConfigException), \
                mock.patch.object(self.seeder.k8s_config,
                                  'load_incluster_config'), \
                mock.patch.object(kopf, 'WebhookServer'):
            self.seeder.startup(self.settings)
        self.addCleanup(self.settings.execution.executor.shutdown)

        self.resource = references.Resource(
            group='seeder.cloud.sap', version='v1', plural='ccloudseeds',
            kind='CcloudSeed', namespaced=True)
        self.logger = mock.Mock(spec=logging.Logger)
        self.memory = self.new_memory()
        self.raw = {
            'apiVersion': 'seeder.cloud.sap/v1', 'kind': 'CcloudSeed',
            'metadata': {
                'name': 'domain-ccadmin-seed', 'namespace': 'example',
                'uid': 'example-seed', 'generation': 1,
                'annotations': {'operatorVersion': '1.0'},
            },
            'spec': {'openstack': {
                'domains': [{'name': 'ccadmin', 'config': {
                    'identity': {'driver': 'cc_ldap'},
                    'ldap': {'url': 'ldap://bad.example'},
                }}],
                'role_assignments': [{
                    'group': 'CCADMIN_CLOUD_ADMINS', 'role': 'admin',
                    'domain': 'ccadmin', 'project': 'cloud_admin',
                }],
            }},
        }
        self.stored_config = None
        self.ldap_requests = []
        self.client = mock.Mock()
        self.client.domains.list.return_value = [
            resource_ref(id='ccadmin-id', name='ccadmin')]
        self.client.domain_configs.get.side_effect = self.get_domain_config
        self.client.domain_configs.create.side_effect = self.save_domain_config
        self.client.domain_configs.update.side_effect = self.save_domain_config
        self.client.roles.list.return_value = [
            resource_ref(id='admin-role', name='admin')]
        self.client.groups.list.side_effect = self.list_groups
        self.client.projects.list.return_value = [
            resource_ref(id='cloud-admin-id', name='cloud_admin')]
        self.client.roles.check.side_effect = exceptions.NotFound('No grant')

        helper = self.domains.OpenstackHelper
        for name in ('_singleton', 'args', 'id_cache', 'client_cache'):
            self.patch_object(helper, name, None, create=True)
        self.patch_object(helper, 'get_keystoneclient',
                          mock.Mock(return_value=self.client))

    def patch_object(self, obj, name, value, create=False):
        patcher = mock.patch.object(obj, name, value, create=create)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def new_memory(self):
        memory = inventory.ResourceMemory()
        memory.memo['args'] = self.args
        memory.memo['dry_run'] = False
        return memory

    def get_domain_config(self, domain):
        if self.stored_config is None:
            raise exceptions.NotFound('No domain configuration')
        return resource_ref(**self.stored_config)

    def save_domain_config(self, domain, config):
        self.stored_config = copy.deepcopy(config)

    def list_groups(self, domain, name):
        url = self.stored_config['ldap']['url']
        self.ldap_requests.append(url)
        if url == 'ldap://bad.example':
            raise TimeoutError('Simulated LDAP timeout')
        return [resource_ref(id='ldap-group-id', name=name)]

    def set_url(self, url):
        config = self.raw['spec']['openstack']['domains'][0]['config']
        config['ldap']['url'] = url
        self.raw['metadata']['generation'] += 1

    def progress(self, handler):
        return [json.loads(value)
                for key, value in self.raw['metadata']['annotations'].items()
                if key.startswith('seeder.ccloud/' + handler)]

    async def reconcile(self):
        # Advance delayed retries without sleeping or contacting Kubernetes.
        for key, value in list(self.raw['metadata']['annotations'].items()):
            if key.startswith('seeder.ccloud/seed_'):
                record = json.loads(value)
                record['delayed'] = '2000-01-01T00:00:00+00:00'
                self.raw['metadata']['annotations'][key] = json.dumps(record)

        body = bodies.Body(copy.deepcopy(self.raw))
        patch = patches.Patch()
        storage = self.settings.persistence.diffbase_storage
        old = storage.fetch(body=body)
        new = storage.build(body=body)
        progress = self.settings.persistence.progress_storage
        old = progress.clear(essence=old) if old is not None else None
        new = progress.clear(essence=new)
        cause = causes.detect_changing_cause(
            finalizer=self.settings.persistence.finalizer,
            raw_event={'type': 'MODIFIED', 'object': self.raw},
            body=body, old=old, new=new, diff=diffs.diff(old, new),
            initial=self.memory.noticed_by_listing,
            resource=self.resource, logger=self.logger, patch=patch,
            memo=self.memory.memo, indices={})
        await processing.process_changing_cause(
            lifecycle=lifecycles.all_at_once, registry=self.registry,
            settings=self.settings, memory=self.memory, cause=cause)
        merge_patch(self.raw, dict(patch))

    async def test_corrected_ldap_is_applied_while_assignments_retry(self):
        await self.reconcile()
        self.assertTrue(self.progress('seed_domains_handler')[0]['success'])
        self.assertFalse(self.progress(
            'seed_role_assignments_handler')[0]['success'])
        self.client.roles.grant.assert_not_called()

        self.set_url('ldap://good.example')
        await self.reconcile()

        self.assertEqual('ldap://good.example',
                         self.stored_config['ldap']['url'])
        self.client.roles.grant.assert_called_once_with(
            'admin-role', group='ldap-group-id', project='cloud-admin-id')
        self.assertFalse(self.progress('seed_domains_handler'))
        self.assertIn('seeder.ccloud/last-applied-configuration',
                      self.raw['metadata']['annotations'])

    async def test_corrected_ldap_is_applied_after_operator_restart(self):
        await self.reconcile()
        self.set_url('ldap://good.example')
        self.memory = self.new_memory()
        self.memory.noticed_by_listing = True
        await self.reconcile()

        self.assertEqual('ldap://good.example',
                         self.stored_config['ldap']['url'])
        self.client.roles.grant.assert_called_once()

    async def test_corrected_ldap_is_applied_during_unfinished_update(self):
        previous = copy.deepcopy(self.raw)
        previous['spec']['openstack']['domains'][0]['config']['ldap'] = {
            'url': 'ldap://previous.example'}
        previous['spec']['openstack']['role_assignments'] = []
        storage = self.settings.persistence.diffbase_storage
        previous = storage.build(body=bodies.Body(previous))
        patch = patches.Patch()
        storage.store(body=bodies.Body(self.raw), patch=patch,
                      essence=previous)
        merge_patch(self.raw, dict(patch))
        await self.reconcile()
        self.assertEqual('update',
                         self.progress('seed_domains_handler')[0]['purpose'])

        self.set_url('ldap://good.example')
        await self.reconcile()

        self.assertEqual('ldap://good.example',
                         self.stored_config['ldap']['url'])
        self.client.roles.grant.assert_called_once()

    async def test_failed_correction_can_be_retried(self):
        await self.reconcile()
        self.set_url('ldap://good.example')
        self.client.domain_configs.update.side_effect = TimeoutError(
            'Simulated configuration API timeout')
        await self.reconcile()
        self.assertFalse(self.progress('seed_domains_handler')[0]['success'])
        self.client.roles.grant.assert_not_called()

        self.client.domain_configs.update.side_effect = self.save_domain_config
        await self.reconcile()
        # The assignments guard observes the domain success on the next event.
        await self.reconcile()

        self.assertEqual('ldap://good.example',
                         self.stored_config['ldap']['url'])
        self.client.roles.grant.assert_called_once()

    async def test_status_changes_preserve_successful_handler_progress(self):
        await self.reconcile()
        self.raw['status']['latest_reconcile'] = '2026-11-12T12:00:00Z'
        self.raw['metadata']['generation'] += 1
        self.raw['spec']['duration'] = '0:00:02'
        await self.reconcile()

        self.client.domain_configs.get.assert_called_once()
        self.assertEqual(['ldap://bad.example', 'ldap://bad.example'],
                         self.ldap_requests)

    async def test_legacy_progress_does_not_block_corrected_ldap(self):
        self.settings.persistence.progress_storage = (
            kopf.AnnotationsProgressStorage(prefix='seeder.ccloud'))
        await self.reconcile()
        self.set_url('ldap://good.example')
        self.memory = self.new_memory()
        # Simulate deploying the new operator onto an already stuck seed.
        with mock.patch.object(
                self.seeder.k8s_config, 'load_kube_config',
                side_effect=self.seeder.k8s_config.ConfigException), \
                mock.patch.object(self.seeder.k8s_config,
                                  'load_incluster_config'), \
                mock.patch.object(kopf, 'WebhookServer'):
            self.seeder.startup(self.settings)
        await self.reconcile()

        self.assertEqual('ldap://good.example',
                         self.stored_config['ldap']['url'])
        self.client.roles.grant.assert_called_once()
