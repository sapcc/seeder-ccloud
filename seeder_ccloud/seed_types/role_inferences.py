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
from seeder_ccloud.seeder_operator import OPERATOR_ANNOTATION, SEED_CRD
from keystoneclient import exceptions
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper


@kopf.on.validate(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.role_inferences')
def validate_role_inferences(spec, dryrun, **_):
    role_inferences = spec.get('role_inferences', [])
    for role_inference in role_inferences:
        if 'prior_role' not in role_inference or not role_inference['prior_role']:
            raise kopf.AdmissionError("role_inferences must have a prior_role if present..")
        if 'implied_role' not in role_inference or not role_inference['implied_role']:
            raise kopf.AdmissionError("role_inferences must have a implied_role if present.")


@kopf.on.update(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.role_inferences')
@kopf.on.create(SEED_CRD['plural'], annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.role_inferences')
def seed_role_inferences_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} role_inferences'.format(name))
    if not utils.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)

    try:
        changed = utils.get_changed_seeds(old, new)
        Role_Inferences(memo['args', memo['dry_run']]).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Role_Inferences():
    def __init__(self, args, dry_run=False):
        self.dry_run = dry_run
        self.args = args
        self.openstack = OpenstackHelper(args)


    def seed(self, role_inferences):
        for role_inference in role_inferences:
            self._seed_role_inference(role_inference)


    def _seed_role_inference(self, role_inference):
        """ seed a keystone role inference """
        logging.debug("seeding role-inference %s" % role_inference)

        # todo: role.domainId ? just for global roles?

        role_inference = self.openstack.sanitize(role_inference, ('prior_role', 'implied_role'))

        # resolve role-id's
        prior_role_id = self.openstack.get_role_id(role_inference['prior_role'])
        if not prior_role_id:
            logging.warn(
                "skipping role-inference '%s', since its prior_role is unknown" % role_inference)
            return
        implied_role_id = self.openstack.get_role_id(role_inference['implied_role'])
        if not implied_role_id:
            logging.warn(
                "skipping role-inference '%s', since its implied_role is unknown" % role_inference)
            return

        try:
            self.openstack.get_keystoneclient().inference_rules.get(prior_role_id, implied_role_id)
        except exceptions.NotFound:
            logging.info("create role-inference '%s'" % role_inference)
            if not self.dry_run:
                self.openstack.get_keystoneclient().inference_rules.create(prior_role_id, implied_role_id)