import logging
import kopf
from seeder_ccloud import utils
from kubernetes import client
from kubernetes.client.rest import ApiException
from kopf._cogs.structs import bodies


class Handlers():
    def __init__(self, operator_storage):
        self.operator_storage = operator_storage
        self.config = utils.Config()

    def setup(self):
        
        @kopf.on.create(self.config.crd_info['plural'], annotations={'operatorVersion': self.config.operator_version})
        @kopf.on.update(self.config.crd_info['plural'], annotations={'operatorVersion': self.config.operator_version})
        def check_dependencies(spec, new, name, namespace, **kwargs):
            requires = spec.get('requires', None)
            logging.info('checking dependencies for seed {}'.format(name))
            if not requires:
                return
            if self.has_dependency_cycle(client, name, namespace, requires):
                raise kopf.TemporaryError('dependency cycle', delay=300)
            try:
                self.resolve_requires(client, requires)
            except kopf.TemporaryError as error:
                raise kopf.TemporaryError('{}'.format(error), delay=30)
            except Exception as error:
                raise kopf.TemporaryError('{}'.format(error), delay=30)

        import seeder_ccloud.operator.crd_legacy_mutate
        import seeder_ccloud.handlers.regions
        import seeder_ccloud.handlers.domains
        import seeder_ccloud.handlers.flavors
        import seeder_ccloud.handlers.groups
        import seeder_ccloud.handlers.role_assignments
        import seeder_ccloud.handlers.projects.projects


    def has_dependency_cycle(self, k8s_client, seed_name, namespace, requires):
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
                        group=self.config.crd_info['group'], 
                        version=self.config.crd_info['version'],
                        plural=self.config.crd_info['plural'],
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


    def resolve_requires(self, k8s_client, requires):
        if requires == None:
            return
        api = k8s_client.CustomObjectsApi()
        for re in requires:
            # namespace/seed_name
            name = re.split("/")
            res = api.get_namespaced_custom_object_status(
                group=self.config.crd_info['group'], 
                version=self.config.crd_info['version'],
                plural=self.config.crd_info['plural'],
                namespace=name[0],
                name=name[1],
            )
            if res is None:
                raise kopf.TemporaryError('cannot find dependency {}'.format(re))
            # check if the operator has added the annotation yet        
            body = bodies.Body(res)
            last_handled = self.operator_storage.fetch(body=body)
            if last_handled is None:
                raise kopf.TemporaryError('dependency not reconsiled yet')

            # compare the last handled state with the actual crd state. We only care about spec changes
            if last_handled['spec'] != res['spec']:
                raise kopf.TemporaryError('dependency not reconsiled with latest configuration yet')