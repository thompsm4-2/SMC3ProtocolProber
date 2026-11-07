"""Software-only tests for the v0.5 eventslog module (task T1.4).

eventslog.py is a Phase 1 skeleton: JSONL event writing is assigned to
the Phase 6 logging tasks (T6.4) and is intentionally not tested
functionally here. Only the structural contract (an importable module
carrying the documented responsibility) is exercised. Nothing here
touches hardware.

Run directly:
    python src/sweep/h3_sweep_v05/tests/test_eventslog.py
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../h3_sweep_v05/tests
sys.path.insert(0, str(HERE.parent.parent))         # .../src/sweep holds h3_sweep_v05

from h3_sweep_v05 import eventslog


class EventslogTests(unittest.TestCase):
    def test_module_identity(self):
        self.assertEqual(eventslog.__name__, "h3_sweep_v05.eventslog")

    def test_responsibility_documented(self):
        """Responsibility per the Implementation.md section 3 table row."""
        doc = eventslog.__doc__ or ""
        self.assertIn("JSONL", doc)
        self.assertIn("event", doc)

    def test_skeleton_marker_present(self):
        """Phase 1 placeholder status is explicit in the docstring."""
        doc = eventslog.__doc__ or ""
        self.assertIn("Phase 1 skeleton placeholder", doc)


if __name__ == "__main__":
    unittest.main()
