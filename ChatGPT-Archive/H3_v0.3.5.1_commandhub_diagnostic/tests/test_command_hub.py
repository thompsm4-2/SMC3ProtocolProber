import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT))
sys.modules.pop("serial", None)

from smc3 import MotionCommandQueue, MotorCommand


class CommandHubTests(unittest.TestCase):
    def test_hybrid_latest_value_wins(self):
        q = MotionCommandQueue()
        q.put(MotorCommand("A", 520))
        q.put(MotorCommand("A", 530))
        q.put(MotorCommand("B", 540))
        self.assertEqual(q.get().position, 530)
        self.assertEqual(q.get().motor, "B")
        self.assertIsNone(q.get(timeout=0))


if __name__ == "__main__":
    unittest.main()
