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

import kopf, logging
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper
from seeder_ccloud import utils
from deepdiff import DeepDiff
from novaclient import exceptions as novaexceptions

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.flavors')
def validate_flavors(spec, dryrun, **_):
    flavors = spec.get('flavors', [])
    for flavor in flavors:
        if 'name' not in flavor or not flavor['name']:
            raise kopf.AdmissionError("Flavors must have a name if present..")
        if 'id' not in flavor or not flavor['id']:
            raise kopf.AdmissionError("Flavors must have an id if present.")
        if 'extra_specs' in flavor:
            extra_specs = flavor['extra_specs']
            if not isinstance(extra_specs, dict):
                raise kopf.AdmissionError("extra_specs must be a valid dict if present.")


@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.flavors')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.flavors')
def seed_flavors_handler(memo: kopf.Memo, new, old, spec, name, annotations, **_):
    logging.info('seeding {} flavor'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Flavors(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Flavors():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


    def seed(self, flavors, spec):
        resource_classes: set[str] = set()
        traits: set[str] = set()
        for flavor in flavors:
            flavor = self.openstack.sanitize(flavor, (
                'id', 'name', 'ram', 'disk', 'vcpus', 'swap', 'rxtx_factor',
                'is_public', 'disabled', 'ephemeral', 'extra_specs'))
            required_traits, mentioned_traits, required_resource_classes = self._get_traits_and_resource_classes(flavor)
            missing_traits = list(mentioned_traits - set(self._get_traits()))
            associated_traits = set(self._get_traits(only_associated=True))
            resource_classes.update(required_resource_classes)
            traits.update(missing_traits)
            if missing_traits:
                logging.info("Found traits mentioned in flavors missing in Nova: {}".format(missing_traits))    
            if not required_traits:
                self._seed_flavor(flavor)
                continue
            missing_req_traits = required_traits - associated_traits
            if not missing_traits:
                self._seed_flavor(flavor)
                continue
            for trait in missing_req_traits:
                logging.warn("Flavors {} need a resource provider with trait '{}' and will"
                        " not be seeded".format(', '.join(flavor['id']), trait))
                logging.warn("You can add missing traits to resource providers with\n"
                    "    'openstack resource provider trait set --trait <TRAIT>"
                    " <RP-UUID>'\n"
                    "and then wait for the seeder to run again.")

        # seed the missing traits and resource_classes
        if 'resource_classes' in spec:
            self.seeder.all_seedtypes['resource_classes'].seed(set(spec['resource_classes']) - resource_classes)
        if 'traits' in spec:
            self.seeder.all_seedtypes['traits'].seed(set(spec['traits']) - traits)


    def _seed_flavor(self, flavor):
        logging.debug("seeding flavor %s" % flavor)
        try:
            nova = self.openstack.get_novaclient()

            # we need to pop the extra_specs, because Nova handles them at their
            # own endpoint and does not understand us posting them with the rest of
            # the flavor
            extra_specs = flavor.pop('extra_specs', None)

            # wtf, flavors has no update(): needs to be dropped and re-created instead
            create = False
            resource = None
            try:
                resource = nova.flavors.get(flavor['id'])

                # 'rename' some attributes, since api and internal representation differ
                flavor_cmp = flavor.copy()
                if 'is_public' in flavor_cmp:
                    flavor_cmp['os-flavor-access:is_public'] = flavor_cmp.pop('is_public')
                if 'disabled' in flavor_cmp:
                    flavor_cmp['OS-FLV-DISABLED:disabled'] = flavor_cmp.pop('disabled')
                if 'ephemeral' in flavor_cmp:
                    flavor_cmp['OS-FLV-EXT-DATA:ephemeral'] = flavor_cmp.pop('ephemeral')

                # check for delta
                diff = DeepDiff(flavor_cmp, resource.to_dict())
                if 'values_changed' in diff:
                    logging.info(
                        "deleting flavor '%s' to re-create, since it differs '%s'" %
                        (flavor['name'], diff['values_changed']))
                if not self.dry_run:
                    resource.delete()
                    create = True

            except novaexceptions.NotFound:
                create = True

            # (re-) create the flavor
            if create:
                logging.info("creating flavor '%s'" % flavor['name'])
                if not self.dry_run:
                    flavor['flavorid'] = flavor.pop('id')
                    resource = nova.flavors.create(**flavor)

            # take care of the flavors extra specs
            if extra_specs and resource:
                set_extra_specs = False
                try:
                    keys = resource.get_keys()
                    for k, v in extra_specs.items():
                        if v != keys.get(k, ''):
                            keys[k] = v
                            set_extra_specs = True
                except novaexceptions.NotFound:
                    set_extra_specs = True
                    keys = extra_specs

                if set_extra_specs and not self.dry_run:
                    logging.info(
                        "updating extra-specs '%s' of flavor '%s'" % (
                            keys, flavor['name']))
                    resource.set_keys(keys)
        except Exception as e:
            logging.error("Failed to seed flavor %s: %s" % (flavor, e))
            raise


    def _get_traits_and_resource_classes(self, flavor):
        required_traits = set()
        mentioned_traits = set()
        required_resource_classes = set()
        if 'extra_specs' in flavor:
                extra_specs = flavor['extra_specs']
                required_traits = set()
                for k, v in extra_specs.items():
                    if k.startswith('resources:CUSTOM_'):
                        resource_class = k.split(':', 1)[-1]
                        required_resource_classes.add(resource_class)
                    if k.startswith('trait:CUSTOM_'):
                        trait = k.split(':', 1)[-1]
                        mentioned_traits.add(trait)
                        if v == "required":
                            required_traits.add(trait)
        
        return required_traits, mentioned_traits, required_resource_classes


    def _get_traits(self, only_associated=False):
        """
        Return the list of all traits that have been set on at least one resource provider.
        """
        try:
            params = {'associated': 'true'} if only_associated else {}
            url_params = '&'.join(f'{k}={v}' for k, v in params.items())
            result = self.openstack.get_placementclient().request('GET', f'/traits?{url_params}')
        except Exception as e:
            logging.error("Failed checking for trait resource providers: {}".format(e))
            return []
        return result.json().get("traits", [])