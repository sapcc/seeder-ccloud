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
import kubernetes
import json
import sys
import logging
import argparse
import kubernetes_asyncio
from kubernetes.client.rest import ApiException
from keystoneauth1.loading import cli
from seeder_ccloud.seeder import Seeder


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
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix='openstackseeds.sap.com')


#why we dont use async handlers: https://kopf.readthedocs.io/en/stable/async/
#@kopf.on.create('openstackseeds.openstack.stable.sap.cc')
@kopf.on.create('kopfexamples', annotations={'operator_version': '2'})
def seed_create(patch, memo: kopf.Memo, spec, name, namespace, status, retry):
    logging.debug("retried {0}x to seed {1}".format(retry, name))
    requires = spec.get('requires', None)
    if has_dependency_cycle(name, namespace, requires):
        #patch.annotations['seeder_error'] = 'dependency cyle detected'
        raise kopf.TemporaryError('dependency cycle', delay=300)
    try:
        resolveRequires(requires)
    except kopf.TemporaryError as error:
        raise kopf.TemporaryError('{}'.format(error), delay=30)
        #patch.annotations['seeder_error'] = 'required seeds not seeded'
    except Exception as error:
        #patch.annotations['seeder_error'] = 'cannot check for requires'
        raise kopf.PermanentError('error getting required seeds: {}'.format(error))

    try:
        memo['seeder'].seed_spec(spec)
    except Exception as error:
        #patch.annotations['seeder_error'] = 'error exec seed'
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=300)


@kopf.on.update('kopfexamples', annotations={'operator_version': '2'})
def seed_update(patch, memo: kopf.Memo, spec, name, namespace, status, diff, retry):
    # TODO: just seed the diff?!
    # check for has_dependency_cycle only when the requires field changed!!
    print(diff)
    pass


def has_dependency_cycle(seed_name, namespace, requires):
    api = kubernetes.client.CustomObjectsApi()
    if requires == None:
        return False
    for re in requires:
        # namespace/seed_name
        name = re.split("/")
        try:
            res = api.get_namespaced_custom_object_status(
                group='kopf.dev', 
                version='v1',
                plural='kopfexamples',
                namespace=name[0],
                name=name[1],
            )
            requires = res.spec.get('requires', None)
            if namespace + seed_name in requires:
                return True
            if requires is not None:
                has_dependency_cycle(seed_name, namespace, requires)
        except ApiException as e:
            logging.error('error checking for dependency cycle: {}'.format(e))
    return False


def resolveRequires(requires):
    if requires == None:
        return
    api = kubernetes.client.CustomObjectsApi()
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
        if res['metadata']['annotations']['kopf.zalando.org/last-handled-configuration'] == None:
            raise kopf.TemporaryError('dependency not reconsiled yet')

        # compare the last handled state with the actual crd state. We only care about spec changes
        lastHandled = json.loads(res['metadata']['annotations']['kopf.zalando.org/last-handled-configuration'])
        if lastHandled['spec'] != res['spec']:
            raise kopf.TemporaryError('dependency not reconsiled yet')


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
    cli.register_argparse_arguments(parser, sys.argv[1:])
    return parser.parse_args()


def main():
    args = get_args()
    setup_logging(args)
    verbose = True if args.logLevel == 'DEBUG' else False 
    kopf.configure(verbose=verbose, log_prefix=True)  # purely for logging

    # either threading.Event(), or asyncio.Event(), or asyncio/concurrent Future().
    memo = kopf.Memo(my_stop_flag=threading.Event())
    memo.seeder = Seeder(args)
    asyncio.run(kopf.operator(memo=memo, stop_flag=memo.my_stop_flag))


if __name__ == '__main__':
    main()