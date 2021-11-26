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

import logging
from typing import DefaultDict
from seeder.openstack.openstack_helper import OpenstackHelper

from novaclient import exceptions as novaexceptions
from seeder.seed_type_registry import BaseRegisteredSeedTypeClass


class Flavor(BaseRegisteredSeedTypeClass):
    def __init__(self, args):
        self.opentack = OpenstackHelper(args)
   
    def seed(self, spec):
       
        flavors: list[dict] = []
        resource_classes: set[str] = set()
        traits: set[str] = set()
        if 'flavors' in spec:
            seedable_flavors, flavor_resource_classes, flavor_missing_traits = \
                self.check_seedable_flavors_and_resourceclasses_and_traits(
                    spec['flavors'])
            flavors.extend(seedable_flavors)
            resource_classes.update(flavor_resource_classes)
            traits.update(flavor_missing_traits)
        
        if 'traits' in spec:
            traits.update(spec['traits'])

        for trait in traits:
            logging.info("seeding trait {}".format(trait))
            self.seed_trait(trait)

        for flavor in flavors:
            self._seed_flavor(flavor)

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
                for attr in list(flavor_cmp.keys()):
                    if flavor_cmp[attr] != getattr(resource, attr):
                        logging.info(
                            "deleting flavor '%s' to re-create, since '%s' differs" %
                            (flavor['name'], attr))
                        resource.delete()
                        create = True
                        break
            except novaexceptions.NotFound:
                create = True

            # (re-) create the flavor
            if create:
                logging.info("creating flavor '%s'" % flavor['name'])
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

                if set_extra_specs:
                    logging.info(
                        "updating extra-specs '%s' of flavor '%s'" % (
                            keys, flavor['name']))
                    resource.set_keys(keys)
        except Exception as e:
            logging.error("Failed to seed flavor %s: %s" % (flavor, e))
            raise


    def check_seedable_flavors_and_resourceclasses_and_traits(self, flavors):
        """Sanitize flavors and check for:
            * Missing/faulty extra specs
            * Missing 'id'
            * Missing 'name'
            * Missing trait providers in the region, when traits are required.
        Returns a tuple of:
            * a list of all seedable flavors
            * a list of resource classes required by the flavors
            * a list of traits mentioned by the flavors (this is different
            from "required" traits, because some traits might be "forbidden".
            Both kinds of flavors must still exist, assigned or not.)
        Note: The list of traits will also include traits from unseedable flavors. This
        allows seeding once (flavor fails, but trait is created), then (manually) setting
        newly created traits on one or more resource providers, and then seeding flavors
        again, with the flavor now succeeding, since the trait is present and providable.
        """
        required_resource_classes = set()
        mentioned_traits = set()
        sanitized_flavors = []
        for flavor in flavors:
            flavor = self.openstack.sanitize(flavor, (
                'id', 'name', 'ram', 'disk', 'vcpus', 'swap', 'rxtx_factor',
                'is_public', 'disabled', 'ephemeral', 'extra_specs'))
            if 'name' not in flavor or not flavor['name']:
                logging.warn("skipping flavor '{}', since it has no name".format(flavor))
                continue
            if 'id' not in flavor or not flavor['id']:
                logging.warn("skipping flavor '{}', since its id is missing".format(flavor))
                continue
            required_traits = set()
            if 'extra_specs' in flavor:
                extra_specs = flavor['extra_specs']
                if not isinstance(extra_specs, dict):
                    logging.warn("skipping flavor '{}', since it has invalid extra_specs"
                                .format(flavor))
                    continue

                for k, v in extra_specs.items():
                    if k.startswith('resources:CUSTOM_'):
                        resource_class = k.split(':', 1)[-1]
                        required_resource_classes.add(resource_class)
                    if k.startswith('trait:CUSTOM_'):
                        trait = k.split(':', 1)[-1]
                        mentioned_traits.add(trait)
                        if v == "required":
                            required_traits.add(trait)

            sanitized_flavors.append((flavor, required_traits))

        associated_traits = set(self._get_traits(only_associated=True))

        seedable_flavors = []
        unseedable_flavorids_by_trait = DefaultDict(set)
        for flavor, required_traits in sanitized_flavors:
            if not required_traits:
                seedable_flavors.append(flavor)
                continue

            missing_traits = required_traits - associated_traits
            if not missing_traits:
                seedable_flavors.append(flavor)
                continue

            for trait in missing_traits:
                unseedable_flavorids_by_trait[trait].add(flavor['id'])

        if unseedable_flavorids_by_trait:
            for trait, flavorids in unseedable_flavorids_by_trait.items():
                logging.warn("Flavors {} need a resource provider with trait '{}' and will"
                            " not be seeded".format(', '.join(flavorids), trait))
            logging.warn("You can add missing traits to resource providers with\n"
                        "    'openstack resource provider trait set --trait <TRAIT>"
                        " <RP-UUID>'\n"
                        "and then wait for the seeder to run again.")

        missing_traits = list(mentioned_traits - set(self._get_traits()))
        if missing_traits:
            logging.info("Found traits mentioned in flavors missing in Nova: {}".format(missing_traits))

        logging.info("Found resource classes: {}".format(list(required_resource_classes)))
        return seedable_flavors, required_resource_classes, missing_traits

    
    def seed_trait(self, trait):
        try:
            self.get_placementapi().request('PUT', '/traits/{}'.format(trait))
        except Exception as e:
            logging.error("Failed to seed trait %s: %s" % (trait, e))
    
    
    def _get_traits(self, only_associated=False):
        """
        Return the list of all traits that have been set on at least one resource provider.
        """
        try:
            params = {'associated': 'true'} if only_associated else {}
            url_params = '&'.join(f'{k}={v}' for k, v in params.items())
            result = self.get_placementapi.request('GET', f'/traits?{url_params}')
        except Exception as e:
            logging.error("Failed checking for trait resource providers: {}".format(e))
            return []
        return result.json().get("traits", [])