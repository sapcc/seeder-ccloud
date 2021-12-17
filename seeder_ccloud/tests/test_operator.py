import unittest
import kopf
from seeder_operator import has_dependency_cycle, resolve_requires
from seeder_ccloud.tests.mock import kubernetes


class TestOperator(unittest.TestCase):
    def test_has_dependency_cycle(self):
        list = {
            "seed01": {
                "spec": {
                    "requires": ['namespace01/seed02']
                }
            },
            "seed02": {
                "spec": {
                    "requires": ['namespace01/seed03']
                }
            },
            "seed03": {
                "spec": {
                    "requires": ['namespace01/seed04']
                }
            },
            "seed04": {
                "spec": {
                    "requires": ['namespace01/seed01']
                }
            }
        }
        c = kubernetes.CustomObjectsApi(list)
        dep = has_dependency_cycle(c, 'seed01', 'namespace01', ['namespace01/seed02'])
        self.assertTrue(dep)


    def test_has_not_dependency_cycle(self):
        list = {
            "seed01": {
                "spec": {
                    "requires": ['namespace01/seed02']
                }
            },
            "seed02": {
                "spec": {
                    "requires": ['namespace01/seed03', 'namespace01/seed04']
                }
            },
            "seed03": {
                "spec": {
                    "requires": ['namespace01/seed02']
                }
            },
            "seed04": {
                "spec": {
                    "requires": ['namespace01/seed03']
                }
            }
        }
        c = kubernetes.CustomObjectsApi(list)
        dep = has_dependency_cycle(c, 'seed01', 'namespace01', ['namespace01/seed02'])
        self.assertFalse(dep)


    def test_missing_resolve_requires(self):
        list = {
            "seed02": {
                "spec": {
                    "requires": ['namespace01/seed03']
                },
                "metadata": {
                    "annotations": {}
                },
                "spec": {
                    "domains": "somedata"
                }
            }
        }
        c = kubernetes.CustomObjectsApi(list)
        self.assertRaisesRegex(kopf._core.actions.execution.TemporaryError, 'dependency not reconsiled yet', resolve_requires, c, ['namespace01/seed02', 'namespace01/seed04'])

    
    def test_resolve_requires(self):
        list = {
            "seed02": {
                "spec": {
                    "requires": ['namespace01/seed03']
                },
                "metadata": {
                    "annotations": {
                        "seeder.ccloud.sap.com/last-handled-configuration": '{"spec": {"domains": "somedata"}}'
                    }
                },
                "spec": {
                    "domains": "somedata"
                }
            },
            "seed03": {
                "spec": {
                    "requires": ['namespace01/seed04']
                }
            },
            "seed04": {
                "spec": {
                    "requires": ['namespace01/seed03']
                },
                "metadata": {
                    "annotations": {
                        "seeder.ccloud.sap.com/last-handled-configuration": '{"spec": {"domains": "somedata"}}'
                    }
                },
                "spec": {
                    "domains": "somedata"
                }
            }
        }
        c = kubernetes.CustomObjectsApi(list)
        try:
            resolve_requires(c, ['namespace01/seed02', 'namespace01/seed04'])
        except:
            self.fail("should not raise error")

        
    def test_not_resolved_requires(self):
        list = {
            "seed02": {
                "spec": {
                    "requires": ['namespace01/seed03']
                },
                "metadata": {
                    "annotations": {
                        "seeder.ccloud.sap.com/last-handled-configuration": '{"spec": {"domains": "somedata"}}'
                    }
                },
                "spec": {
                    "domains": "somedata"
                }
            },
            "seed03": {
                "spec": {
                    "requires": ['namespace01/seed04']
                }
            },
            "seed04": {
                "spec": {
                    "requires": ['namespace01/seed03']
                },
                "metadata": {
                    "annotations": {
                        "seeder.ccloud.sap.com/last-handled-configuration": '{"spec": {"domains": "somedata2"}}'
                    }
                },
                "spec": {
                    "domains": "somedata"
                }
            }
        }
        c = kubernetes.CustomObjectsApi(list)
        self.assertRaisesRegex(kopf._core.actions.execution.TemporaryError, 'dependency not reconsiled with latest configuration yet', resolve_requires, c, ['namespace01/seed02', 'namespace01/seed04'])