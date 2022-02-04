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
from kubernetes import config as k8s_config
from seeder_ccloud import utils
from seeder_ccloud.operator.handlers import Handlers


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
        settings.admission.managed = 'seeder.cloud.sap'
    except k8s_config.ConfigException:
        k8s_config.load_incluster_config()
        settings.admission.server = kopf.WebhookServer(addr='0.0.0.0', port=80, insecure=True)
        #settings.admission.server.host = 'https://seeder-ccloud.qa-de-1.cloud.sap'

    logging.info('starting operator with {} workers and crd {}'.format(int(args.max_workers), config.crd_info))
    settings.execution.max_workers = int(args.max_workers)
    #settings.admission.managed = 'seeder.cloud.sap'
    settings.persistence.diffbase_storage = operator_storage
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix=config.prefix)


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

    h = Handlers(operator_storage)
    h.setup()

    asyncio.run(kopf.operator(
        memo=memo, 
        stop_flag=memo.my_stop_flag,
        clusterwide=clusterwide,
        standalone=True,
        namespace= args.namespaces
    ))


if __name__ == '__main__':
    main()