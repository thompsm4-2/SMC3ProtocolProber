import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ManualCLITests(unittest.TestCase):
    def test_all_commands_without_hardware(self):
        commands = "\n".join([
            "e", "a+", "a-", "b+", "b-", "c+", "c-",
            "center", "status", "ver", "s", "q", ""
        ])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "tests")
        result = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "manual_h3.py"), "echo", "--debug"],
            input=commands,
            text=True,
            capture_output=True,
            env=env,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("sent: [ena]", result.stdout)
        self.assertIn("sent: A=522 B=512 C=512", result.stdout)
        self.assertIn("sent: A=512 B=512 C=512", result.stdout)
        self.assertIn("sent: [ver]", result.stdout)
        self.assertIn("sent: []", result.stdout)


if __name__ == "__main__":
    unittest.main()
