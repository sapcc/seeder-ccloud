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

from inspect import ArgSpec


class SeedTypeRegistryBase(type):

    SEED_TYPE_REGISTRY = {}

    def __new__(cls, name, bases, attrs):
        new_cls = type.__new__(cls, name, bases, attrs)
        cls.SEED_TYPE_REGISTRY[new_cls.__name__.lower()] = new_cls
        return new_cls

    @classmethod
    def get_seed_registry(cls):
        return dict(cls.SEED_TYPE_REGISTRY)


class BaseRegisteredSeedTypeClass(metaclass=SeedTypeRegistryBase):
    def __init__(self, args, session):
        self.args = args
        self.session = session

    def seed(self, *args, **kwargs):
        """
        Iterate over seeds in the crd spec
        and updates the openstack objects accordingly.
        """
        raise NotImplementedError()