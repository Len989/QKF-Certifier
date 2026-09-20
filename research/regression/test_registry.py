from copy import deepcopy
import json
import unittest
from .run import REGISTRY, modules


class RegistryTests(unittest.TestCase):
    def setUp(self):self.data=json.loads(REGISTRY.read_text())
    def test_actual_registry(self):self.assertEqual(modules(self.data),modules(self.data,'prior')+modules(self.data,'new'))
    def test_duplicate_rejected(self):
        self.data['new'].append(self.data['prior'][0])
        with self.assertRaises(ValueError):modules(self.data)
    def test_missing_rejected(self):
        self.data['new'].append('research.test_missing_context_suite')
        with self.assertRaises(ValueError):modules(self.data)
    def test_non_test_rejected(self):
        self.data['new'].append('research.signed_coverage.producer')
        with self.assertRaises(ValueError):modules(self.data)
    def test_invalid_group(self):
        with self.assertRaises(ValueError):modules(self.data,'unknown')
    def test_unknown_schema(self):
        self.data['schema']='fake'
        with self.assertRaises(ValueError):modules(self.data)


if __name__=='__main__':unittest.main()
