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
import asyncio
import threading
import kopf
import logging
from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kopf._cogs.structs import bodies
from seeder_ccloud import utils

import seeder_ccloud.crd_legacy_mutate
import seeder_ccloud.seed_types.domains
import seeder_ccloud.seed_types.groups
import seeder_ccloud.seed_types.role_assignments
import seeder_ccloud.seed_types.projects.projects


config = utils.Config()
operator_storage = kopf.AnnotationsDiffBaseStorage(
    prefix=config.prefix,
    key='last-handled-configuration',
)

@kopf.on.startup()
def startup(settings: kopf.OperatorSettings, **kwargs):
    args = config.get_args()
    # Load kubernetes_asyncio config as kopf does not do that automatically for us.
    try:
        k8s_config.load_kube_config()
        settings.admission.server = kopf.WebhookNgrokTunnel(port=88)
        settings.admission.server.insecure = True
    except k8s_config.ConfigException:
        settings.admission.server = kopf.WebhookServer()
        k8s_config.load_incluster_config()

    logging.info('starting operator with {} workers'.format(int(args.max_workers)))
    settings.execution.max_workers = int(args.max_workers)
    settings.admission.managed = 'seeder.cloud.sap'
    settings.persistence.diffbase_storage = operator_storage
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix=config.prefix)


@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version})
@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version})
def check_dependencies(spec, new, name, namespace, **kwargs):
    requires = spec.get('requires', None)
    logging.info('checking dependencies for seed {}'.format(name))
    if not requires:
        return
    if has_dependency_cycle(client, name, namespace, requires):
        raise kopf.TemporaryError('dependency cycle', delay=300)
    try:
        resolve_requires(client, requires)
    except kopf.TemporaryError as error:
        raise kopf.TemporaryError('{}'.format(error), delay=30)
    except Exception as error:
        raise kopf.TemporaryError('{}'.format(error), delay=30)


def has_dependency_cycle(k8s_client, seed_name, namespace, requires):
    if requires is None:
        return False
    api = k8s_client.CustomObjectsApi()
    visited_seeds = []
    def check(requires):
        for re in requires:
            # namespace/seed_name
            name = re.split("/")
            if re in visited_seeds:
                continue
            try:
                res = api.get_namespaced_custom_object_status(
                    group=config.crd_info['group'], 
                    version=config.crd_info['version'],
                    plural=config.crd_info['plural'],
                    namespace=name[0],
                    name=name[1],
                )
                new_requires = res['spec'].get('requires', None)
                visited_seeds.append(re)
                if new_requires is None:
                    continue
                if "{}/{}".format(namespace, seed_name) in new_requires:
                    return True
                if check(new_requires):
                    return True
            except ApiException as e:
                logging.error('error checking for dependency cycle: {}'.format(e))
        return False
    return check(requires)


def resolve_requires(k8s_client, requires):
    if requires == None:
        return
    api = k8s_client.CustomObjectsApi()
    for re in requires:
        # namespace/seed_name
        name = re.split("/")
        res = api.get_namespaced_custom_object_status(
            group=config.crd_info['group'], 
            version=config.crd_info['version'],
            plural=config.crd_info['plural'],
            namespace=name[0],
            name=name[1],
        )
        if res is None:
            raise kopf.TemporaryError('cannot find dependency {}'.format(re))
        # check if the operator has added the annotation yet        
        body = bodies.Body(res)
        last_handled = operator_storage.fetch(body=body)
        if last_handled is None:
            raise kopf.TemporaryError('dependency not reconsiled yet')

        # compare the last handled state with the actual crd state. We only care about spec changes
        if last_handled['spec'] != res['spec']:
            raise kopf.TemporaryError('dependency not reconsiled with latest configuration yet')


def setup_logging(logLevel):
    logging.basicConfig(
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        level=getattr(logging, logLevel))


def main():
    args = config.get_args()
    setup_logging(args.logLevel)
    verbose = True if args.logLevel == 'DEBUG' else False 
    kopf.configure(verbose=verbose, log_prefix=True)  # purely for logging
    # either threading.Event(), or asyncio.Event(), or asyncio/concurrent Future().
    memo = kopf.Memo(my_stop_flag=threading.Event())
    memo['args'] = args
    memo['dry_run'] = args.dry_run
    clusterwide = True
    if args.namespaces:
        clusterwide = False

    asyncio.run(kopf.operator(
        memo=memo, 
        stop_flag=memo.my_stop_flag,
        clusterwide=clusterwide,
        standalone=True,
        namespace= args.namespaces
    ))


if __name__ == '__main__':
    main()