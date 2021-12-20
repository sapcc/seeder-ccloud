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

import logging, kopf
from seeder_operator import OPERATOR_ANNOTATION
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud.seed_type_registry import BaseRegisteredSeedTypeClass
from seeder_ccloud import utils


class Share_Types(BaseRegisteredSeedTypeClass):
    def __init__(self, args, seeder, dry_run=False):
        super().__init__(args, seeder, dry_run)
        self.openstack = OpenstackHelper(self.args)


    @staticmethod
    @kopf.on.update('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.share_types')
    @kopf.on.create('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.share_types')
    def seed_domains_handler(memo: kopf.Memo, old, new, spec, name, annotations, **kwargs):
        logging.info('seeding {} share_types'.format(name))
        if not utils.is_dependency_successful(annotations):
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

        try:
            memo['seeder'].all_seedtypes['share_types'].seed(new)
        except Exception as error:
            raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


    def seed(self, share_types):
        logging.info('seeding manila share_types')
        for share_type in share_types:
            self._seed_share_types(share_type)


    def _seed_share_types(self, share_type):
        """ seed manila share type """
        logging.debug("seeding Manila share type %s" % share_type)

        # intialize manila client
        try:
            client = self.openstack.get_manilaclient("2.40")
            manager = client.share_types
        except Exception as e:
            logging.error("Fail to initialize client: %s" % e)
            raise

        def get_type_by_name(name):
            opts = {'all_tenants': 1}
            for t in manager.list(search_opts=opts):
                if t.name == name:
                    return t
            return None

        def validate_share_type(sharetype):
            sharetype = self.openstack.sanitize(sharetype, [
                'name', 'description', 'is_public', 'specs', 'extra_specs'])
            specs = sharetype.pop('specs')
            try:
                sharetype['extra_specs'].update(specs)
            except KeyError:
                sharetype['extra_specs'] = specs
            return sharetype

        def update_type(stype, extra_specs):
            to_be_unset = []
            for k in list(stype.extra_specs.keys()):
                if k not in list(extra_specs.keys()):
                    to_be_unset.append(k)
            stype.unset_keys(to_be_unset)
            stype.set_keys(extra_specs)

        def create_type(sharetype):
            extra_specs = sharetype['extra_specs']
            try:
                dhss = extra_specs.pop('driver_handles_share_servers')
                sharetype['spec_driver_handles_share_servers'] = dhss
            except KeyError:
                pass
            try:
                snapshot_support = extra_specs.pop('snapshot_support')
                sharetype['spec_snapshot_support'] = snapshot_support
            except KeyError:
                pass
            sharetype['extra_specs'] = extra_specs
            try:
                manager.create(**sharetype)
            except:
                sharetype.pop('description')
                manager.create(**sharetype)

        # validation sharetype
        share_type = validate_share_type(share_type)
        logging.debug("Validated Manila share type %s" % share_type)

        # update share type if exists
        stype = get_type_by_name(share_type['name'])
        if stype:
            try:
                if not self.dry_run:
                    update_type(stype, share_type['extra_specs'])
            except Exception as e:
                logging.error("Failed to update share type %s: %s" % (share_type, e))
                raise
        else:
            try:
                if not self.dry_run:
                    create_type(share_type)
            except Exception as e:
                logging.error("Failed to create share type %s: %s" % (share_type, e))
                raise