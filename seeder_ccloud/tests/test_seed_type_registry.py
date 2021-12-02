import unittest
from seeder_ccloud.seed_type_registry import SeedTypeRegistryBase


class TestSeedTypeRegistry(unittest.TestCase):

    def test_register_seed_types(self):
        from seeder_ccloud.seed_types.roles import Roles
        from seeder_ccloud.seed_types.regions import Regions
        from seeder_ccloud.seed_types.domains import Domains
        from seeder_ccloud.seed_types.flavors import Flavors
        from seeder_ccloud.seed_types.rbac_policies import Rbac_Policies
        from seeder_ccloud.seed_types.resource_classes import Resource_Classes
        from seeder_ccloud.seed_types.role_inferences import Role_Inferences
        from seeder_ccloud.seed_types.services import Services
        from seeder_ccloud.seed_types.volume_types import Volume_Types
        from seeder_ccloud.seed_types.traits import Traits
        from seeder_ccloud.seed_types.quota_class_sets import Quota_Class_Sets
        from seeder_ccloud.seed_types.share_types import Share_Types


        
        self.assertEqual(len(SeedTypeRegistryBase.SEED_TYPE_REGISTRY), 13)