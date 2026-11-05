import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent

# Allow direct execution: python tests/test_smc3.py
# Use the local serial-compatible stub for tests that do not require hardware.
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT))
sys.modules.pop("serial", None)

from smc3 import (
    MotorCommand,
    SMC3Transport,
    encode_command,
    encode_disable,
    encode_enable,
    encode_version_request,
)


class SMC3Tests(unittest.TestCase):
    def test_encoding(self):
        self.assertEqual(encode_command("A", 510), b"[A\x01\xfe]")
        self.assertEqual(encode_enable(), b"[ena]")
        self.assertEqual(encode_disable(), b"[]")
        self.assertEqual(encode_version_request(), b"[ver]")

    def test_motor_validation_and_clamp(self):
        self.assertEqual(MotorCommand("a", -5).motor, "A")
        self.assertEqual(MotorCommand("a", -5).position, 0)
        self.assertEqual(MotorCommand("b", 5000).position, 1023)
        with self.assertRaises(ValueError):
            MotorCommand("D", 512)

    def test_transport_path(self):
        transport = SMC3Transport("echo")
        transport.start()
        try:
            transport.enable()
            transport.set_positions(522, 512, 512)
            self.assertTrue(transport.wait_for_idle(2.0))
            # wait_for_idle can observe the queue between worker dispatches;
            # allow the 30 Hz CommandHub to finish the complete A/B/C set.
            import time
            time.sleep(0.15)
            import smc3
            writes = smc3.serial.Serial.instances[-1].writes
            self.assertIn(b"[ena]", writes)
            self.assertIn(b"[A\x02\x0a]", writes)
            self.assertIn(b"[B\x02\x00]", writes)
            self.assertIn(b"[C\x02\x00]", writes)
        finally:
            transport.close()


if __name__ == "__main__":
    unittest.main()
