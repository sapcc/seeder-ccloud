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

import kopf
import kubernetes
import json
import logging

from seeder.seeder import Seeder

seeder = Seeder()

@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **kwargs):
    settings.execution.max_workers = 100
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix='openstackseeds.sap.com')

#@kopf.on.create('openstackseeds.openstack.stable.sap.cc')
@kopf.on.create('kopfexamples')
@kopf.on.update('kopfexamples')
def openstack_seeder(patch, spec, name, namespace, status, retry, **kwargs):
    logging.debug("retried {0} to seed {1}".format(retry, name))
    requires = spec.get('requires', None)
    if requires == None:
        return
    try:
        resolveRequires(requires)
    except Exception as error:
        logging.error(error)
        #patch.status['seeder_error'] = error
        raise kopf.TemporaryError('requires not yet seeded', delay=30)

    try:
        seeder.seed_spec(spec)
    except Exception as error:
        logging.error("could not seed %s. error: %s" % name, error)
        raise kopf.TemporaryError('expected error', delay=300)


def resolveRequires(requires):
    api = kubernetes.client.CustomObjectsApi()
    for re in requires:
        name = re.split("/")
        res = api.get_namespaced_custom_object_status(
            group='kopf.dev', 
            version='v1',
            plural='kopfexamples',
            namespace=name[0],
            name=name[1],
        )
        # check if the operator has added the annotation yet
        if res['metadata']['annotations']['kopf.zalando.org/last-handled-configuration'] == None:
            raise Exception('dependency not reconsiled yet')

        # compare the last handled state with the actual crd state. We only care about spec changes
        lastHandled = json.loads(res['metadata']['annotations']['kopf.zalando.org/last-handled-configuration'])
        if lastHandled['spec'] != res['spec']:
            raise Exception('dependency not reconsiled yet')
