import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class CalibrationToolTests(unittest.TestCase):
    def test_position_sequence(self):
        from examples.h3_calibrate import positions_for_sweep
        self.assertEqual(positions_for_sweep(-40, 40, 20), [-40, -20, 0, 20, 40])
        self.assertEqual(positions_for_sweep(-50, 45, 20), [-50, -30, -10, 10, 30, 45])

    def test_cli_help(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "tests")
        result = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "h3_calibrate.py"), "--help"],
            text=True, capture_output=True, env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Controlled one-motor-at-a-time", result.stdout)
        self.assertIn("--no-observe", result.stdout)

    def test_settle_zero_is_valid(self):
        from argparse import Namespace
        from examples.h3_calibrate import validate_args
        args = Namespace(step=1, start=0, end=2, settle=0.0)
        validate_args(args)

    def test_cli_smoke_with_echo_serial(self):
        commands = "e\nstatus\ncenter\nq\n"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "tests")
        result = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "h3_calibrate.py"), "echo"],
            input=commands, text=True, capture_output=True, env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("sent: [ena]", result.stdout)
        self.assertIn("sent: A=B=C=512", result.stdout)
        self.assertIn("writer=alive", result.stdout)

    def test_no_observe_sweep_with_echo_serial(self):
        commands = "e\nsweep a\nq\n"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "tests")
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "examples" / "h3_calibrate.py"),
                "echo", "--start", "0", "--end", "2", "--step", "1",
                "--settle", "0", "--no-observe"
            ],
            input=commands, text=True, capture_output=True, env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("Observation prompts are disabled (--no-observe).", result.stdout)
        self.assertIn("A=512 (offset +0)", result.stdout)
        self.assertIn("A=513 (offset +1)", result.stdout)
        self.assertIn("A=514 (offset +2)", result.stdout)
        self.assertIn("A sweep complete.", result.stdout)
        self.assertNotIn("observation [Enter=none, q=abort]", result.stdout)

    def test_sweep_path_with_echo_serial(self):
        # Two positions: 512 and 532. Blank observations are accepted.
        commands = "e\nsweep a\n\n\nq\n"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "tests")
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "examples" / "h3_calibrate.py"),
                "echo", "--start", "0", "--end", "20", "--step", "20", "--settle", "0"
            ],
            input=commands, text=True, capture_output=True, env=env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("A=512 (offset +0)", result.stdout)
        self.assertIn("A=532 (offset +20)", result.stdout)
        self.assertIn("A sweep complete.", result.stdout)


if __name__ == "__main__":
    unittest.main()
