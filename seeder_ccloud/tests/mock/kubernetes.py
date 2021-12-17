
class CustomObjectsApi():
    def __init__(self, seed_list):
        self.seed_list = seed_list


    def CustomObjectsApi(self):
        return self


    def get_namespaced_custom_object_status(self, group, version, namespace, plural, name, **kwargs):
        return self.seed_list[name]