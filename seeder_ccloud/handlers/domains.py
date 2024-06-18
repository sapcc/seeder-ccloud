"""
 Copyright 2021 SAP SE
 
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

import logging, kopf, time, json
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from deepdiff import DeepDiff
from keystoneclient import exceptions
from typing import List

config = utils.Config()


@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.domains')
def validate_domains(memo: kopf.Memo, dryrun, spec, old, warnings: List[str], **_):
    domains = spec['openstack'].get('domains', [])
    for domain in domains:
        if 'name' not in domain or not domain['name']:
            raise kopf.AdmissionError("Domains must have a name if present..")
    
    if dryrun and domains:
        old_domains = None
        if old is not None:
            old_domains = old['spec']['openstack'].get('domains', None)
        changed = utils.get_changed_seeds(old_domains, domains)
        diffs = Domains(memo['args'], dryrun).seed(changed)
        if diffs:
            warnings.append({'domains': diffs})



@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.domains')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.domains')
def seed_domains_handler(memo: kopf.Memo, patch: kopf.Patch, new, old, name, annotations, **_):
    logging.info('seeding {} == > domains'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        start = time.time()
        changed = utils.get_changed_seeds(old, new)
        diffs = Domains(memo['args'], memo['dry_run']).seed(changed)
        duration = time.time() - start
        patch.status['state'] = "seeded"
        patch.spec['duration'] = str(duration)
        if not 'changes' in patch.status:
            patch.status['changes'] =  json.dumps({"openstack.domains": len(diffs.keys())})
        else:
            try:
                changes = json.loads(patch.status['changes'])
                changes.update({'domains': len(diffs.keys())})
                patch.status['changes'] = json.dumps(changes)
            except Exception as error:
                logging.error('error updating changes: {}'.format(str(error)))
        if 'latest_error' in patch.status:
            latest_error = json.loads(patch.status['latest_error'])
            if 'openstack.domains' in latest_error:
                del latest_error['openstack.domains']
                patch.status['latest_error'] = json.dumps(latest_error)
    except Exception as error:
        patch.status['state'] = "failed"
        if not 'latest_error' in patch.status:
            patch.status['latest_error'] = json.dumps({'openstack.domains': str(error)})
        else:
            try:
                latest_error = json.loads(patch.status['latest_error'])
                latest_error.update({'openstack.domains': str(error)})
                patch.status['latest_error'] = json.dumps(latest_error)
            except Exception as error:
                logging.error('error updating latest_error: {}'.format(str(error)))
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
    
    logging.info('DONE seeding {} == > domains'.format(name))


class Domains():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)

   
    def seed(self, domains):
        self.diffs = {}
        for domain in domains:
            self._seed_domain(domain)
        return self.diffs


    def _seed_domain(self, domain):
        logging.debug('seeding domain {}'.format(domain['name']))
        self.diffs[domain['name']] = []
        #get all changed sub_seeds
        driver = domain.pop('config', None)

        # grab a keystone client
        keystone = self.openstack.get_keystoneclient()
        domain = self.openstack.sanitize(domain, ('name', 'description', 'enabled'))

        result = keystone.domains.list(name=domain['name'])
        resource = None
        if not result:
            self.diffs[domain['name']].append('create')
            if not self.dry_run:
                logging.info("create domain '%s'" % domain['name'])
                resource = keystone.domains.create(**domain)
        else:
            resource = result[0]
            diff = DeepDiff(resource.to_dict(), domain)
            if 'values_changed' in diff:
                self.diffs[domain['name']].append(diff['values_changed'])
                logging.info("domain %s differs: '%s'" % (domain['name'], diff))
                if not self.dry_run:
                    logging.info("update domain '%s'" % domain['name'])
                    keystone.domains.update(resource.id, **domain)

        if driver:
            self._seed_domain_config(resource, driver)


    def _seed_domain_config(self, domain, driver):
        logging.info(
            "seeding domain config %s %s" % (domain.name, self.openstack.redact(driver)))
        self.diffs[domain.name + '_config'] = []
        keystone = self.openstack.get_keystoneclient()
        # get the current domain configuration
        try:
            result = keystone.domain_configs.get(domain)
            diff = DeepDiff(result.to_dict(), driver, exclude_obj_callback=utils.diff_exclude_password_callback)
            if 'values_changed' in diff:
                self.diffs[domain.name+'_config'].append(diff['values_changed'])
                logging.info("domain_config %s differs: '%s'" % (domain.name, diff))
                if not self.dry_run:
                    logging.info('update domain config %s' % domain.name)
                    keystone.domain_configs.update(domain, driver)
        except exceptions.NotFound:
            self.diffs[domain.name + '_config'].append('create')
            if not self.dry_run:
                logging.info('create domain config %s' % domain.name)
                keystone.domain_configs.create(domain, driver)
        except Exception as e:
            logging.error(
                'could not configure domain %s: %s' % (domain.name, e))
