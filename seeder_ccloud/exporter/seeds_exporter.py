import sys
import kopf
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from kubernetes import client, config
from time import sleep
from kopf._cogs.structs import bodies
from seeder_ccloud import utils
import logging

try:
    config.load_kube_config()
except config.ConfigException:
    config.load_incluster_config()

try:
    config = utils.Config()
except Exception as e:
    logging.error(e)
    sys.exit(0)

class SeedsCollector(object):
    def __init__(self):
        self.storage = kopf.AnnotationsDiffBaseStorage(
            prefix=config.prefix,
            key='last-applied-configuration',
        )

    def describe(self):
        yield GaugeMetricFamily('ccloud_seeds_total', 'Shows number of seeds')
        yield GaugeMetricFamily('ccloud_seeds_status', 'Shows the status of a single seed')

    def collect(self):
        total = GaugeMetricFamily('ccloud_seeds_total', 'Shows number of seeds', labels=None)
        status = GaugeMetricFamily('ccloud_seeds_status', 'Shows the status of a single seed', labels=['name'])
        api = client.CustomObjectsApi()
        seeds = api.list_cluster_custom_object(
            group=config.crd_info['group'], 
            version=config.crd_info['version'],
            plural=config.crd_info['plural'],
        )
        total.add_metric(labels=[], value=len(seeds['items']))
        yield total

        for seed in seeds['items']:
            meta = None
            try:
                body = bodies.Body(seed)
                meta = bodies.Meta(seed)
                lastApplied = self.storage.fetch(body=body)
                if lastApplied is None:
                    status.add_metric(labels=[meta.name], value=0.0)
                    continue
                if lastApplied['spec'] != seed['spec']:
                    status.add_metric(labels=[meta.name], value=0.0)
                else:
                    status.add_metric(labels=[meta.name], value=1.0)
            except Exception as e:
                logging.error(e)
                if meta is not None:
                    status.add_metric(labels=[meta.name], value=0.0)
        yield status


REGISTRY.register(SeedsCollector())


def main():
    # Start up the server to expose the metrics.
    start_http_server(9000)
    while True:
        sleep(10)


if __name__ == '__main__':
    main()