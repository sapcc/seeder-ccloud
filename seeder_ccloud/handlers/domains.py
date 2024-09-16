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

import logging, kopf, time
from datetime import timedelta, datetime
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
            raise kopf.AdmissionError("Domains must have a name")
        if 'config' in domain:
            if not isinstance(domain['config'], dict):
                raise kopf.AdmissionError("Domain config must be a valid dict if present")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.domains')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.domains')
def seed_domains_handler(memo: kopf.Memo, patch: kopf.Patch, new, old, name, annotations, **_):
    logging.info('seeding {}: domains'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        starttime = time.perf_counter()
        changed = utils.get_changed_seeds(old, new)
        diffs = Domains(memo['args'], memo['dry_run']).seed(changed)
        duration = timedelta(seconds=time.perf_counter()-starttime)
        utils.setStatusFields('domains', patch, 'seeded', duration=duration, diffs=diffs)
    except Exception as error:
        logging.error('error seeding {}: {}'.format(name, error))
        utils.setStatusFields('domains', patch, 'error', 0, latest_error=str(error))
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)
    finally:
        patch.status['latest_reconcile'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    logging.info('successfully seeded domains: {}'.format(name))


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
                logging.info("domain %s differs: '%s'" % (domain['name'], diff['values_changed']))
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
            if diff:
                if 'values_changed' in diff:
                    self.diffs[domain.name+'_config'].append(diff['values_changed'])
                if  'dictionary_item_added' in diff:
                    self.diffs[domain.name+'_config'].append(diff['dictionary_item_added'])
                if 'dictionary_item_removed' in diff:
                    self.diffs[domain.name+'_config'].append(diff['dictionary_item_removed']) 
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
