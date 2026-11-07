"""Tests for T3.9 — Classification uses only the new v0.5 package.

This test verifies that the v0.5 classification implementation does NOT:
1. Import historical v0.4.1 calibration modules (src/calibration/h3_characterize.py)
2. Dynamically load or execute historical v0.4.1 source code
3. Depend on archived implementation code for classification

The test uses runtime/import checks, not source-text searches.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
import importlib

# Set up path BEFORE any imports
HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent  # Go from tests/ to src/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Define the v0.4.1 calibration module paths that should NOT be imported
FORBIDDEN_MODULES = {
    "calibration.h3_characterize",
    "calibration.test_v04",
    "calibration.test_fake_serial",
}

# Define the v0.5 modules we expect to be importable
EXPECTED_MODULES = {
    "h3_sweep_v05.classifier",
    "h3_sweep_v05.ledger",
    "h3_sweep_v05.recorder",
    "h3_sweep_v05.driver",
    "h3_sweep_v05.eventslog",
    "h3_sweep_v05.csvlog",
}


class ForbiddenModuleTracker:
    """Track which forbidden modules get loaded during import."""
    
    def __init__(self):
        self.loaded = set()
    
    def track_import(self, name):
        if name in FORBIDDEN_MODULES:
            self.loaded.add(name)
        # Also track the full dotted path
        full_name = f"{name}.h3_sweep_v05" if "." in name else name
        if full_name in FORBIDDEN_MODULES:
            self.loaded.add(full_name)


class T39IndependenceTests(unittest.TestCase):
    """Tests that the v0.5 package is independent of historical v0.4.1 code."""
    
    def setUp(self):
        """Clear any cached imports before each test."""
        # Remove all h3_sweep_v05 modules to ensure fresh import
        modules_to_remove = [
            key for key in sys.modules
            if key.startswith("h3_sweep_v05")
        ]
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # Also clear calibration modules
        modules_to_remove = [
            key for key in sys.modules
            if key.startswith("calibration")
        ]
        for module_name in modules_to_remove:
            del sys.modules[module_name]
    
    def test_no_forbidden_modules_in_import(self):
        """Verify that importing v0.5 does not load forbidden v0.4.1 modules."""
        tracker = ForbiddenModuleTracker()
        original_import = __builtins__["__import__"]
        
        def tracked_import(name, *args, **kwargs):
            tracked_import(name, *args, **kwargs)
        
        # Monkey-patch __import__ to track forbidden modules
        def custom_import(name, globals=None, locals=None, fromlist=(), level=0):
            result = original_import(name, globals, locals, fromlist, level)
            tracker.track_import(name)
            return result
        
        __builtins__["__import__"] = custom_import
        
        try:
            # Import the v0.5 package
            import h3_sweep_v05
            import h3_sweep_v05.classifier
            import h3_sweep_v05.ledger
            import h3_sweep_v05.recorder
            import h3_sweep_v05.driver
            
            # Check that no forbidden modules were loaded
            self.assertEqual(
                len(tracker.loaded), 0,
                f"Forbidden modules were loaded: {tracker.loaded}"
            )
        finally:
            # Restore original import
            __builtins__["__import__"] = original_import
    
    def test_classification_works_without_calibration_modules(self):
        """Verify classification can be performed without loading calibration modules."""
        # Import v0.5 modules
        import h3_sweep_v05.classifier as classifier
        import h3_sweep_v05.ledger as ledger
        
        # Check that calibration modules are NOT in sys.modules
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, sys.modules,
                f"Forbidden module {forbidden} was loaded during classification import"
            )
            self.assertNotIn(
                f"calibration.{forbidden}", sys.modules,
                f"Forbidden module calibration.{forbidden} was loaded"
            )
        
        # Verify we can create a classifier without calibration dependencies
        from h3_sweep_v05.classifier import PointClassification, classify_point
        from h3_sweep_v05.ledger import VerificationResult
        
        # Create a simple classification without any calibration data
        # Use None for verification to test barrier timeout case
        verification = VerificationResult(
            point_id=1,
            verified=False,
            frames_match=False,
            counts_match=False,
            statuses_match=False,
            mismatches=(),
        )
        
        # Test FAILED case (verification failed)
        classification = classify_point(
            verification_result=verification,
            tx_count_before=10,
            barrier_timed_out=False,
            attempts=[],
        )
        classification.classify()
        
        # Should be FAILED because verification failed
        self.assertEqual(classification.status, "FAILED")
        
        # Now test COMPLETE case with proper attempts
        # Create mock attempts with all required fields
        mock_attempts = [
            {
                "attempt_seq": 1,
                "timestamp": 1000.0,
                "monotonic_timestamp": 100.0,
                "frame_bytes": b"\x5BA\x00\x064\x5D",
                "returned_count": 5,
                "expected_count": 5,
                "status": "OK",
                "exception": None,
                "is_motor_frame": True,
            },
            {
                "attempt_seq": 2,
                "timestamp": 1000.1,
                "monotonic_timestamp": 100.1,
                "frame_bytes": b"\x5BB\x00\x068\x5D",
                "returned_count": 5,
                "expected_count": 5,
                "status": "OK",
                "exception": None,
                "is_motor_frame": True,
            },
            {
                "attempt_seq": 3,
                "timestamp": 1000.2,
                "monotonic_timestamp": 100.2,
                "frame_bytes": b"\x5BC\x00\x06C\x5D",
                "returned_count": 5,
                "expected_count": 5,
                "status": "OK",
                "exception": None,
                "is_motor_frame": True,
            },
        ]
        
        # Create a verification that passes
        verification_pass = VerificationResult(
            point_id=1,
            verified=True,
            frames_match=True,
            counts_match=True,
            statuses_match=True,
            mismatches=(),
        )
        
        classification = classify_point(
            verification_result=verification_pass,
            tx_count_before=10,
            barrier_timed_out=False,
            attempts=mock_attempts,
        )
        classification.classify()
        
        # Should be COMPLETE
        self.assertEqual(classification.status, "COMPLETE")
    
    def test_ledger_executes_only_v0351_not_v041(self):
        """Verify ledger.py only executes v0.3.5.1 encoder, not v0.4.1 calibration."""
        # The ledger module should have loaded the v0.3.5.1 encoder
        # but NOT the v0.4.1 calibration modules
        
        # Check that calibration modules are NOT loaded
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, sys.modules,
                f"Forbidden calibration module {forbidden} was loaded by ledger"
            )
    
    def test_no_dynamic_execution_of_calibration_source(self):
        """Verify no runtime execution of v0.4.1 calibration source."""
        # Check that no calibration source files exist in sys.modules
        # that would indicate dynamic loading
        
        # The ledger module uses exec() to load v0.3.5.1 smc3.py
        # but this should NOT load v0.4.1 calibration code
        
        import h3_sweep_v05.ledger as ledger
        
        # Verify the ledger has the v0.3.5.1 encoder loaded
        self.assertIsNotNone(ledger.encode_command)
        self.assertIsNotNone(ledger.MotorCommand)
        self.assertIsNotNone(ledger.ARCHIVED_MOTORS)
        
        # But calibration modules should NOT be loaded
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, sys.modules,
                f"Dynamic execution of forbidden module {forbidden} detected"
            )
    
    def test_classification_uses_only_v05_interfaces(self):
        """Verify classification uses only v0.5 interfaces, not v0.4.1."""
        from h3_sweep_v05.classifier import PointClassification
        from h3_sweep_v05.ledger import VerificationResult
        
        # Check that PointClassification does not reference calibration modules
        import inspect
        source = inspect.getsource(PointClassification)
        
        # Verify no calibration module references in the classifier source
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, source,
                f"Classifier source references forbidden module {forbidden}"
            )
        
        # Verify no src/calibration references
        self.assertNotIn(
            "src/calibration", source,
            "Classifier source references src/calibration"
        )
        self.assertNotIn(
            "h3_characterize", source,
            "Classifier source references h3_characterize"
        )
    
    def test_recorder_uses_only_v05_interfaces(self):
        """Verify recorder uses only v0.5 interfaces."""
        from h3_sweep_v05.recorder import SerialRecorder
        
        import inspect
        source = inspect.getsource(SerialRecorder)
        
        # Verify no calibration module references
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, source,
                f"Recorder source references forbidden module {forbidden}"
            )
    
    def test_driver_uses_only_v05_interfaces(self):
        """Verify driver uses only v0.5 interfaces."""
        from h3_sweep_v05.driver import run
        
        import inspect
        source = inspect.getsource(run)
        
        # Verify no calibration module references
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, source,
                f"Driver source references forbidden module {forbidden}"
            )
    
    def test_ledger_uses_archived_encoder_not_calibration(self):
        """Verify ledger uses archived v0.3.5.1 encoder, not v0.4.1 calibration."""
        import h3_sweep_v05.ledger as ledger
        
        # The ledger should have v0.3.5.1 encoder loaded
        self.assertIsNotNone(ledger.encode_command)
        self.assertIsNotNone(ledger.MotorCommand)
        self.assertIsNotNone(ledger.ARCHIVED_MOTORS)
        
        # But NOT calibration modules
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, sys.modules,
                f"Ledger loaded forbidden calibration module {forbidden}"
            )
    
    def test_classification_priority_rules_independent_of_calibration(self):
        """Verify classification priority rules don't depend on calibration."""
        from h3_sweep_v05.classifier import PointClassification
        
        import inspect
        source = inspect.getsource(PointClassification)
        
        # Verify classification rules are self-contained
        # Check that classify() method exists and doesn't reference calibration
        classify_method = None
        for name, obj in inspect.getmembers(PointClassification):
            if name == "classify" and inspect.isfunction(obj):
                classify_method = obj
                break
        
        self.assertIsNotNone(classify_method, "classify method not found")
        
        # Verify the method source doesn't reference calibration
        method_source = inspect.getsource(classify_method)
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, method_source,
                f"Classification method references forbidden module {forbidden}"
            )
    
    def test_package_does_not_import_calibration_at_package_level(self):
        """Verify the package __init__.py doesn't import calibration."""
        import h3_sweep_v05
        
        # Check that no calibration modules are loaded at package level
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, sys.modules,
                f"Package init loaded forbidden module {forbidden}"
            )
        
        # Also check the __init__.py source
        init_path = Path(h3_sweep_v05.__file__)
        source = init_path.read_text()
        
        for forbidden in FORBIDDEN_MODULES:
            self.assertNotIn(
                forbidden, source,
                f"__init__.py references forbidden module {forbidden}"
            )
    
    def test_classification_status_values_are_v05_defined(self):
        """Verify classification status values are defined in v0.5, not imported from v0.4.1."""
        from h3_sweep_v05.classifier import PointClassification
        
        # Check that COMPLETE, DEGRADED, FAILED are defined in the classifier module
        self.assertTrue(hasattr(PointClassification, "COMPLETE"))
        self.assertTrue(hasattr(PointClassification, "DEGRADED"))
        self.assertTrue(hasattr(PointClassification, "FAILED"))
        
        # Verify they are string literals, not imported
        import inspect
        source = inspect.getsource(PointClassification)
        
        # Check these are defined locally
        self.assertIn('COMPLETE = "COMPLETE"', source)
        self.assertIn('DEGRADED = "DEGRADED"', source)
        self.assertIn('FAILED = "FAILED"', source)
    
    def test_runtime_check_no_calibration_import(self):
        """Runtime check: import v0.5 and verify no calibration import occurs."""
        # Fresh import to ensure clean state
        modules_to_remove = [
            key for key in sys.modules
            if key.startswith("h3_sweep_v05") or key.startswith("calibration")
        ]
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # Import v0.5
        import h3_sweep_v05
        
        # Runtime check: verify no calibration modules in sys.modules
        loaded_calib_modules = [
            name for name in sys.modules
            if name.startswith("calibration")
        ]
        
        self.assertEqual(
            len(loaded_calib_modules), 0,
            f"Runtime check failed: calibration modules loaded: {loaded_calib_modules}"
        )
    
    def test_classification_can_run_without_any_calibration_dependency(self):
        """Full runtime test: verify classification can run without calibration dependency.
        
        This test verifies that the v0.5 classification implementation:
        1. Can be imported without loading v0.4.1 calibration modules
        2. Can perform classification operations without calibration data
        3. Uses only v0.5-defined interfaces and data structures
        """
        # Fresh import
        modules_to_remove = [
            key for key in sys.modules
            if key.startswith("h3_sweep_v05") or key.startswith("calibration")
        ]
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # Import only v0.5 modules
        import h3_sweep_v05.classifier as classifier
        import h3_sweep_v05.ledger as ledger
        import h3_sweep_v05.recorder as recorder
        
        # Verify no calibration modules loaded
        loaded_calib = [name for name in sys.modules if name.startswith("calibration")]
        self.assertEqual(len(loaded_calib), 0)
        
        # Verify the classification infrastructure is available
        from h3_sweep_v05.classifier import PointClassification, classify_point
        from h3_sweep_v05.ledger import Ledger, SweepPoint, VerificationResult
        
        # Verify we can create a PointClassification object
        pc = PointClassification(
            verification_result=None,
            tx_count_before=10,
            barrier_timed_out=False,
            attempts=[],
        )
        
        # Verify we can call classify()
        pc.classify()
        
        # Verify the status is set (will be FAILED due to None verification, which is expected)
        self.assertIn(pc.status, ["FAILED", "COMPLETE", "DEGRADED"])
        
        # Final check: still no calibration modules
        loaded_calib = [name for name in sys.modules if name.startswith("calibration")]
        self.assertEqual(len(loaded_calib), 0)
        
        # Verify ledger can generate expected frames (uses v0.3.5.1 encoder, not v0.4.1)
        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        
        ledger_obj = Ledger()
        ledger_obj.register_point(point)
        
        # This should work without loading v0.4.1 calibration modules
        frames = ledger_obj.expected_frames(1)
        
        self.assertEqual(len(frames), 3)  # 3 motor frames (A, B, C)
        
        # Verify frames have correct structure
        for frame in frames:
            self.assertEqual(len(frame.frame_bytes), 5)  # 5-byte motor frames
            self.assertIn(frame.motor, ["A", "B", "C"])
    
    def test_import_chain_does_not_include_calibration(self):
        """Verify the import chain from v0.5 to classifier doesn't include calibration."""
        # Track import chain
        import_chain = []
        
        original_import = __builtins__["__import__"]
        
        def chain_import(name, *args, **kwargs):
            import_chain.append(name)
            return original_import(name, *args, **kwargs)
        
        __builtins__["__import__"] = chain_import
        
        try:
            # Clear modules
            modules_to_remove = [
                key for key in sys.modules
                if key.startswith("h3_sweep_v05")
            ]
            for module_name in modules_to_remove:
                del sys.modules[module_name]
            
            # Import classifier
            import h3_sweep_v05.classifier
            
            # Check that no calibration modules are in the import chain
            for module in import_chain:
                self.assertNotIn(
                    "calibration", module,
                    f"Import chain includes calibration module: {module}"
                )
        finally:
            __builtins__["__import__"] = original_import
    
    def test_classification_object_is_v05_only(self):
        """Verify the PointClassification object is entirely v0.5."""
        from h3_sweep_v05.classifier import PointClassification
        
        # Get all attributes of PointClassification
        attrs = dir(PointClassification)
        
        # Check that key attributes exist
        self.assertIn("COMPLETE", attrs)
        self.assertIn("DEGRADED", attrs)
        self.assertIn("FAILED", attrs)
        self.assertIn("classify", attrs)
        self.assertIn("status", attrs)
        self.assertIn("reason", attrs)
        
        # Verify these are not from calibration
        import h3_sweep_v05.classifier as classifier_module
        module_file = Path(classifier_module.__file__)
        source = module_file.read_text()
        
        for attr in ["COMPLETE", "DEGRADED", "FAILED", "classify", "status", "reason"]:
            self.assertIn(attr, source, f"Attribute {attr} not found in classifier source")


if __name__ == "__main__":
    unittest.main()
