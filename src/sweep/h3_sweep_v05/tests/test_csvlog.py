"""Tests for the csvlog module skeleton."""
import sys
import unittest
from importlib import import_module
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../h3_sweep_v05/tests
sys.path.insert(0, str(HERE.parent.parent))         # .../src/sweep holds h3_sweep_v05

MODULE_NAME = "h3_sweep_v05.csvlog"


class TestCsvlogModule(unittest.TestCase):
    def test_module_identity(self):
        module = import_module(MODULE_NAME)
        self.assertEqual(module.__name__, "h3_sweep_v05.csvlog")
        self.assertEqual(module.__package__, "h3_sweep_v05")

    def test_documented_responsibility(self):
        """The module docstring records the CSV log responsibilities of §3.4."""
        doc = import_module(MODULE_NAME).__doc__
        for phrase in ("TX CSV", "Sensor CSV", "ten columns", "analyzer"):
            self.assertIn(phrase, doc)

    def test_skeleton_placeholder_marker(self):
        module = import_module(MODULE_NAME)
        self.assertIn("Phase 1 skeleton placeholder", module.__doc__)


if __name__ == "__main__":
    unittest.main()
