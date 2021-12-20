from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from kubernetes import client, config
from time import sleep


try:
    config.load_kube_config()
except config.ConfigException:
    config.load_incluster_config()


class SeedsCollector(object):
    def describe(self):
        yield GaugeMetricFamily('ccloud_seeds_total', 'Shows number of seeds')
        yield GaugeMetricFamily('ccloud_seeds_status', 'Time spent processing request')

    def collect(self):
        total = GaugeMetricFamily('ccloud_seeds_total', 'Shows number of seeds', labels=None)
        status = GaugeMetricFamily('ccloud_seeds_status', 'Time spent processing request', labels=['name'])
        api = client.CustomObjectsApi()
        seeds = api.list_cluster_custom_object(
            group='kopf.dev', 
            version='v1',
            plural='kopfexamples',
        )
        total.add_metric(labels=[], value=1.0)
        yield total
        for seed in seeds['items']:
            status.add_metric(labels=[seed['metadata']['name']], value=1.0)
        yield status


REGISTRY.register(SeedsCollector())


if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(8000)
    while True:
        sleep(10)
