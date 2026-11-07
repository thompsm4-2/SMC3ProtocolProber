"""Software-only structural tests for the v0.5 sweep package (task T1.4).

Mirrors the archived test organization
(ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/tests/): test_*.py
files in a tests/ directory next to the sources, unittest-based,
directly executable.

These tests exercise the Phase 1 package skeleton only: imports, file
structure, module independence (no circular imports), the no-unnecessary
dependencies rule, and the no-hardware/serial-device dependency rule.
They never open a serial port and never import pyserial.

Run directly:
    python src/sweep/h3_sweep_v05/tests/test_package.py
"""
import sys
import unittest
import ast
import importlib
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../h3_sweep_v05/tests
PKG = HERE.parent                                   # .../h3_sweep_v05
sys.path.insert(0, str(PKG.parent))                 # allow `import h3_sweep_v05`

MODULE_NAMES = ("driver", "recorder", "ledger", "eventslog", "csvlog")
PACKAGE_MODULES = ("__init__",) + MODULE_NAMES
FORBIDDEN_IMPORTS = {"serial", "pyserial"}
FORBIDDEN_DEVICE_PATHS = ("/dev/ttyACM0", "/dev/ttyUSB0")


def module_paths():
    """Absolute paths of the six package module files."""
    return {name: PKG / f"{name}.py" for name in PACKAGE_MODULES}


def imported_top_level_names(path):
    """Top-level module names a source file imports (level-0 only)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def string_constants(path):
    """All string constants in a source file (includes docstrings)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


class PackageTests(unittest.TestCase):
    """Structural contracts for the Phase 1 v0.5 package skeleton."""

    def test_package_imports(self):
        import h3_sweep_v05
        self.assertTrue(h3_sweep_v05.__doc__)

    def test_module_files_present(self):
        for name, path in module_paths().items():
            self.assertTrue(path.is_file(), f"missing module: {path}")

    def test_modules_compile(self):
        """Every module file parses as valid Python."""
        for name, path in module_paths().items():
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:  # pragma: no failure expected
                self.fail(f"{name} does not compile: {exc}")

    def test_modules_importable(self):
        for name in MODULE_NAMES:
            mod = importlib.import_module(f"h3_sweep_v05.{name}")
            self.assertEqual(mod.__name__, f"h3_sweep_v05.{name}")

    def test_no_circular_or_sibling_imports(self):
        """Importing one module must not pull in another v0.5 module."""
        for name in MODULE_NAMES:
            sys.modules.pop(f"h3_sweep_v05.{name}", None)  # fresh import per check
            before = {
                key for key in sys.modules if key.startswith("h3_sweep_v05.")
            }
            mod_name = f"h3_sweep_v05.{name}"
            importlib.import_module(mod_name)
            added = {
                key
                for key in sys.modules
                if key.startswith("h3_sweep_v05.")
            } - before
            self.assertEqual(added, {mod_name}, "modules must be independent")

    def test_package_init_has_no_reexports(self):
        """T1.1/accepted T1.3: __init__.py provides no module re-exports."""
        tree = ast.parse(module_paths()["__init__"].read_text(encoding="utf-8"))
        body = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertEqual(body, [], "no imports or re-exports in __init__.py")

    def test_no_serial_dependency_in_sources(self):
        """No package module imports pyserial (software-only tests)."""
        for name, path in module_paths().items():
            imported = imported_top_level_names(path)
            self.assertEqual(
                imported & FORBIDDEN_IMPORTS, set(),
                f"{name} imports a serial dependency",
            )

    def test_no_serial_in_sys_modules_after_import(self):
        """Importing the package must not load pyserial."""
        importlib.import_module("h3_sweep_v05")
        for name in MODULE_NAMES:
            importlib.import_module(f"h3_sweep_v05.{name}")
        for forbidden in FORBIDDEN_IMPORTS:
            self.assertNotIn(forbidden, sys.modules)

    def test_no_device_paths_in_package_sources(self):
        """No package module hardcodes physical serial-device paths."""
        for name, path in module_paths().items():
            for literal in string_constants(path):
                for dev in FORBIDDEN_DEVICE_PATHS:
                    self.assertNotIn(dev, literal,
                                     f"{name} references {dev}")


if __name__ == "__main__":
    unittest.main()
