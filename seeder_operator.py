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
import json
import sys
import logging
import argparse
import kubernetes_asyncio
from kubernetes.client import api_client
from kubernetes.client.rest import ApiException
from keystoneauth1.loading import cli
from kopf._cogs.structs import bodies

PREFIX = 'seeder.ccloud.sap.com'
OPERATOR_ANNOTATION = 'seeder-ccloud'


operator_storage = kopf.AnnotationsDiffBaseStorage(
    prefix=PREFIX,
    key='last-handled-configuration',
)

@kopf.on.startup()
async def startup(settings: kopf.OperatorSettings, **kwargs):
    args = get_args()
    # Load kubernetes_asyncio config as kopf does not do that automatically for us.
    try:
        # Try incluster config first.
        kubernetes_asyncio.config.load_incluster_config()
    except kubernetes_asyncio.config.ConfigException:
        # Fall back to regular config.
        await kubernetes_asyncio.config.load_kube_config()

    settings.execution.max_workers = args.max_workers
    settings.persistence.diffbase_storage = operator_storage
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix=PREFIX)


@kopf.on.create('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION})
@kopf.on.update('kopfexamples', annotations={'operatorVersion': OPERATOR_ANNOTATION}, field='spec.requires', value=kopf.PRESENT)
def check_dependencies(spec, new, name, namespace, **kwargs):
    requires = spec.get('requires', None)
    if not requires:
        return
    if has_dependency_cycle(api_client, name, namespace, requires):
        raise kopf.TemporaryError('dependency cycle', delay=300)
    try:
        resolve_requires(api_client, requires)
    except kopf.TemporaryError as error:
        raise kopf.TemporaryError('{}'.format(error), delay=30)
    except Exception as error:
        raise kopf.TemporaryError('{}'.format(error), delay=30)


def has_dependency_cycle(client, seed_name, namespace, requires):
    if requires is None:
        return False
    api = client.CustomObjectsApi()
    visited_seeds = []
    def check(requires):
        for re in requires:
            # namespace/seed_name
            name = re.split("/")
            if re in visited_seeds:
                continue
            try:
                res = api.get_namespaced_custom_object_status(
                    group='kopf.dev', 
                    version='v1',
                    plural='kopfexamples',
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


def resolve_requires(client, requires):
    if requires == None:
        return
    api = client.CustomObjectsApi()
    for re in requires:
        # namespace/seed_name
        name = re.split("/")
        res = api.get_namespaced_custom_object_status(
            group='kopf.dev', 
            version='v1',
            plural='kopfexamples',
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


def setup_logging(args):
    logging.basicConfig(
        format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        level=getattr(logging, args.logLevel))


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',
                        help='the yaml file with the identity configuration')
    parser.add_argument('--interface',
                        help='the keystone interface-type to use',
                        default='internal',
                        choices=['admin', 'public', 'internal'])
    parser.add_argument('--insecure',
                        help='do not verify SSL certificates',
                        default=False,
                        action='store_true')
    parser.add_argument("-l", "--log", dest="logLevel",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                 'CRITICAL'],
                        help="Set the logging level",
                        default='INFO')
    parser.add_argument('--dry-run', default=False, action='store_true',
                        help='Only parse the seed, do no actual seeding.')
    parser.add_argument('--max-workers', default=1, action='store_true',
                        help='Max workers for the kopf operator.')
    parser.add_argument("--namespace-patterns", dest="namespaces",
                        help="list of namespace patterns. default is cluster wide",
                        default='')
    cli.register_argparse_arguments(parser, sys.argv[1:])
    return parser.parse_args()


def main():
    from seeder_ccloud.seeder import Seeder
    args = get_args()
    setup_logging(args)
    verbose = True if args.logLevel == 'DEBUG' else False 
    kopf.configure(verbose=verbose, log_prefix=True)  # purely for logging

    # either threading.Event(), or asyncio.Event(), or asyncio/concurrent Future().
    memo = kopf.Memo(my_stop_flag=threading.Event())
    memo.seeder = Seeder(args)
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