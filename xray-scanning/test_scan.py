import unittest
from scan import ScanOperation


class ScanOperationTest(unittest.TestCase):

    def test_convert_component_id_to_path(self):
        scan_operation = ScanOperation(None, "docker://myrepo/path/component:5.0.50", None)
        component_path = scan_operation.convert_component_id_to_path()
        self.assertEqual(component_path, "myrepo/path/component/5.0.50")
