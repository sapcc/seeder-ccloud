import unittest
from seeder.seed_type_registry import SeedTypeRegistryBase


class TestSeedTypeRegistry(unittest.TestCase):

    def test_register_seed_types(self):
        from seeder.seed_types.roles import Roles
        from seeder.seed_types.regions import Regions
        from seeder.seed_types.domains import Domains
        from seeder.seed_types.flavors import Flavors
        from seeder.seed_types.rbac_policies import Rbac_Policies
        from seeder.seed_types.resource_classes import Resource_Classes
        from seeder.seed_types.role_inferences import Role_Inferences
        from seeder.seed_types.services import Services
        from seeder.seed_types.volume_types import Volume_Types
        from seeder.seed_types.traits import Traits
        from seeder.seed_types.quota_class_sets import Quota_Class_Sets
        from seeder.seed_types.share_types import Share_Types


        
        self.assertEqual(len(SeedTypeRegistryBase.SEED_TYPE_REGISTRY), 13)