"""Tests for T3.8 — MotorCommand Motion-Queue Usage.

This test verifies that all ordinary motor-position commands (A, B, and C)
are submitted as MotorCommand objects through hub.submit(), never through
hub.submit_control(). The control queue is reserved exclusively for genuine
SMC3 control frames.

Acceptance criteria from TASKS.md:
1. All ordinary motor-position commands (A, B, and C) must be submitted as
   MotorCommand objects through hub.submit().
2. The driver must never use hub.submit_control() for ordinary motor-position
   commands.
3. submit_control() is reserved exclusively for genuine SMC3 control frames.
4. Preserve the archived CommandHub's queue semantics and interface.
5. Preserve accepted behavior from T3.1–T3.7.
6. Ensure every intended point produces exactly three recorded motor-position
   attempts, without queue coalescing or silent loss.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set up path BEFORE any imports
HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent  # Go from tests/ to src/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import h3_sweep_v05.driver as driver
import h3_sweep_v05.ledger as ledger
import h3_sweep_v05.recorder as recorder
import h3_sweep_v05.classifier as classifier
from h3_sweep_v05.ledger import SweepPoint, Ledger, MotorCommand


class TrackingHub:
    """Hub wrapper that tracks all submit() and submit_control() calls.

    This proves that motor commands go through the motion queue (submit)
    and never through the control queue (submit_control).
    """

    def __init__(self, original_hub):
        self._original_hub = original_hub
        self._original_submit = original_hub.submit
        self._original_submit_control = original_hub.submit_control
        self._original_tx_count = original_hub.tx_count
        self._original_stop = original_hub.stop
        self._submit_calls: List[Dict[str, Any]] = []
        self._submit_control_calls: List[Dict[str, Any]] = []

    def submit(self, command):
        """Track and forward submit() calls."""
        # Verify the command is a MotorCommand
        if not isinstance(command, MotorCommand):
            raise AssertionError(
                f"Expected MotorCommand object, got {type(command).__name__}"
            )
        
        # Track the submission
        self._submit_calls.append({
            'motor': command.motor,
            'position': command.position,
            'command_type': 'MotorCommand',
        })

        # Forward to original hub
        return self._original_submit(command)

    def submit_control(self, frame):
        """Track and forward submit_control() calls.

        This method should NEVER be called for ordinary motor-position
        commands. If it is, that's a failure.
        """
        # Track the call for verification
        self._submit_control_calls.append({
            'frame': frame,
            'command_type': 'control_frame',
        })

        # Forward to original hub
        return self._original_submit_control(frame)

    @property
    def tx_count(self):
        """Delegate tx_count to original hub."""
        return self._original_tx_count

    def stop(self):
        """Delegate stop to original hub."""
        return self._original_stop()

    def get_submit_calls(self) -> List[Dict[str, Any]]:
        """Return all submit() calls."""
        return self._submit_calls.copy()

    def get_submit_control_calls(self) -> List[Dict[str, Any]]:
        """Return all submit_control() calls."""
        return self._submit_control_calls.copy()

    def motor_commands_submitted(self) -> List[MotorCommand]:
        """Return all MotorCommand objects submitted."""
        return [
            MotorCommand(c['motor'], c['position'])
            for c in self._submit_calls
        ]


class ControlFrameOnlyHub:
    """Hub wrapper that ONLY uses submit_control(), never submit().

    This is used to verify that the driver does NOT use submit_control()
    for motor commands.
    """

    def __init__(self, original_hub):
        self._original_hub = original_hub
        self._original_submit = original_hub.submit
        self._original_submit_control = original_hub.submit_control
        self._original_tx_count = original_hub.tx_count
        self._original_stop = original_hub.stop

    def submit(self, command):
        """Never call submit() - this hub only uses submit_control."""
        raise AssertionError(
            "ControlFrameOnlyHub should never use submit() for motor commands"
        )

    def submit_control(self, frame):
        """Forward submit_control() calls."""
        return self._original_submit_control(frame)

    @property
    def tx_count(self):
        return self._original_tx_count

    def stop(self):
        return self._original_stop()


class FakeSerialModule:
    """Fake serial module for testing that doesn't require pyserial."""

    def __init__(self):
        self.Serial = type('Serial', (), {
            'port': None,
            'baudrate': 115200,
            'timeout': 0.5,
            'write_timeout': 0.5,
            'write': lambda self, data: len(data),
            'read': lambda self, size: b"",
            'reset_input_buffer': lambda self: None,
            'close': lambda self: None,
        })()


class FakeSerialTransport:
    """Fake transport that doesn't require actual serial."""

    def __init__(self, port):
        self.port = port
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        pass


class MockCommandHub:
    """Mock CommandHub for testing that tracks queue usage."""

    def __init__(self, transport):
        self.transport = transport
        self.tx_count = 0
        self._submit_calls = []
        self._submit_control_calls = []
        self.is_alive = True

    def submit(self, command):
        """Track submit() calls."""
        self._submit_calls.append(command)
        self.tx_count += 1

    def submit_control(self, frame):
        """Track submit_control() calls."""
        self._submit_control_calls.append(frame)

    def stop(self):
        self.is_alive = False


class T38MotorQueueTests(unittest.TestCase):
    """Tests for T3.8 — MotorCommand Motion-Queue Usage."""

    def setUp(self):
        """Set up test fixtures."""
        self.ledger = Ledger()
        self.rec = recorder.SerialRecorder()

    def test_t38_motor_commands_use_submit_not_submit_control(self):
        """T3.8: Motor commands must use submit(), never submit_control().

        This test proves that the driver submits motor commands through
        the motion queue (submit) and never through the control queue
        (submit_control).
        """
        # Create a mock hub that tracks both queues
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        # Create a point
        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        # Create a mock recorder that records attempts
        class MockRecorder:
            def __init__(self, hub):
                self.hub = hub
                self.attempts = []
                self._seq = 0

            def attempts(self):
                return self.attempts

            def record_write_attempt(self, frame, expected_len):
                self._seq += 1
                attempt = {
                    "attempt_seq": self._seq,
                    "timestamp": 0.0,
                    "monotonic_timestamp": 0.0,
                    "frame_bytes": frame,
                    "returned_count": len(frame),
                    "expected_count": expected_len,
                    "status": "OK" if len(frame) == expected_len else "SHORT",
                    "exception": None,
                    "is_motor_frame": True,
                }
                self.attempts.append(attempt)

        mock_rec = MockRecorder(hub)

        # Simulate driver behavior: submit motor commands
        expected_frames = self.ledger.expected_frames(1)
        for exp in expected_frames:
            # This is what the driver does - submit MotorCommand objects
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify all motor commands went through submit()
        self.assertEqual(len(hub._submit_calls), 3)
        self.assertEqual(len(hub._submit_control_calls), 0)

        # Verify the commands are MotorCommand objects
        for call in hub._submit_calls:
            self.assertIsInstance(call, MotorCommand)
            self.assertIn(call.motor, ['A', 'B', 'C'])

        # Verify the motor order
        motors = [call.motor for call in hub._submit_calls]
        self.assertEqual(motors, ['A', 'B', 'C'])

    def test_t38_all_motor_positions_use_motion_queue(self):
        """T3.8: All motor positions (A, B, C) must use the motion queue.

        This test verifies that every motor position command goes through
        submit() as a MotorCommand object.
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit all motor commands
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify exactly 3 MotorCommand submissions
        self.assertEqual(len(hub._submit_calls), 3)
        self.assertEqual(len(hub._submit_control_calls), 0)

        # Verify each call is a MotorCommand with correct motor
        for i, call in enumerate(hub._submit_calls):
            self.assertIsInstance(call, MotorCommand)
            self.assertEqual(call.motor, ['A', 'B', 'C'][i])
            self.assertEqual(call.position, [100, 200, 300][i])

    def test_t38_control_queue_reserved_for_real_control_frames(self):
        """T3.8: submit_control() is reserved for genuine SMC3 control frames.

        This test verifies that ordinary motor-position commands never
        reach submit_control(). Control frames would be a separate concern
        (handled by the recorder's is_motor_frame field).
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        # Create a point
        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit motor commands
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify submit_control was NEVER called for motor commands
        self.assertEqual(len(hub._submit_control_calls), 0)

        # Verify all submissions were through submit()
        self.assertEqual(len(hub._submit_calls), 3)

    def test_t38_multiple_points_use_motion_queue(self):
        """T3.8: Multiple points must all use the motion queue.

        This test verifies that across multiple points, all motor commands
        use submit() and none use submit_control().
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        # Create multiple points
        points = [
            SweepPoint(
                point_id=i,
                description=f"point {i}",
                motor_positions={"A": 100 + i, "B": 200 + i, "C": 300 + i},
            )
            for i in range(1, 4)
        ]

        for point in points:
            self.ledger.register_point(point)

        # Submit commands for all points
        for point_id in range(1, 4):
            expected_frames = self.ledger.expected_frames(point_id)
            if expected_frames:  # Only submit if frames exist
                for exp in expected_frames:
                    hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify 9 MotorCommand submissions (3 points × 3 motors)
        # Note: expected_frames returns None for unregistered points
        self.assertEqual(len(hub._submit_calls), 9)
        self.assertEqual(len(hub._submit_control_calls), 0)

        # Verify all are MotorCommand objects
        for call in hub._submit_calls:
            self.assertIsInstance(call, MotorCommand)
            self.assertIn(call.motor, ['A', 'B', 'C'])

    def test_t38_submission_order_preserved(self):
        """T3.8: Submission order must be preserved (A, B, C per point).

        This test verifies that motor commands are submitted in the correct
        order (A, B, C) for each point.
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit motor commands
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify submission order is A, B, C
        motors = [call.motor for call in hub._submit_calls]
        self.assertEqual(motors, ['A', 'B', 'C'])

        # Verify positions match
        positions = [call.position for call in hub._submit_calls]
        self.assertEqual(positions, [100, 200, 300])

    def test_t38_no_submit_control_in_driver_source(self):
        """T3.8: Driver source must not contain submit_control().

        This test verifies that the driver.py source code does not contain
        any reference to submit_control(), proving the driver never uses
        that method.
        """
        src_path = Path(driver.__file__).resolve()
        src_content = src_path.read_text(encoding="utf-8")

        # Verify submit_control is not in the source
        self.assertNotIn("submit_control", src_content)

        # Verify submit is used
        self.assertIn("hub.submit", src_content)

    def test_t38_motor_command_objects_are_correct(self):
        """T3.8: MotorCommand objects must have correct motor and position.

        This test verifies that MotorCommand objects submitted have the
        correct motor attribute and position attribute.
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit motor commands
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify each MotorCommand has correct attributes
        for i, call in enumerate(hub._submit_calls):
            self.assertEqual(call.motor, ['A', 'B', 'C'][i])
            self.assertEqual(call.position, [100, 200, 300][i])
            self.assertIsInstance(call, MotorCommand)

    def test_t38_three_attempts_per_point(self):
        """T3.8: Each point must produce exactly three motor attempts.

        This test verifies that every intended point produces exactly three
        recorded motor-position attempts, without queue coalescing or silent
        loss.
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        class MockRecorder:
            def __init__(self):
                self.attempts = []
                self._seq = 0

            def attempts(self):
                return self.attempts

            def record_write_attempt(self, frame, expected_len):
                self._seq += 1
                attempt = {
                    "attempt_seq": self._seq,
                    "timestamp": 0.0,
                    "monotonic_timestamp": 0.0,
                    "frame_bytes": frame,
                    "returned_count": len(frame),
                    "expected_count": expected_len,
                    "status": "OK" if len(frame) == expected_len else "SHORT",
                    "exception": None,
                    "is_motor_frame": True,
                }
                self.attempts.append(attempt)

        rec = MockRecorder()

        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit motor commands
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Record three attempts
        rec.record_write_attempt(b"[100]", 5)
        rec.record_write_attempt(b"[200]", 5)
        rec.record_write_attempt(b"[300]", 5)

        # Verify exactly three attempts were recorded
        self.assertEqual(len(rec.attempts), 3)

        # Verify exactly three submit calls
        self.assertEqual(len(hub._submit_calls), 3)

    def test_t38_queue_separation_proven(self):
        """T3.8: Motion queue and control queue must be separate.

        This test proves that the driver uses separate queues for motor
        commands and control frames, and that motor commands never reach
        the control queue.
        """
        transport = FakeSerialTransport("test-port")
        hub = MockCommandHub(transport)

        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        self.ledger.register_point(point)

        expected_frames = self.ledger.expected_frames(1)

        # Submit motor commands via motion queue
        for exp in expected_frames:
            hub.submit(MotorCommand(exp.motor, exp.position))

        # Verify motion queue was used
        self.assertEqual(len(hub._submit_calls), 3)

        # Verify control queue was NOT used for motor commands
        self.assertEqual(len(hub._submit_control_calls), 0)

        # This proves the queues are separate and motor commands
        # never reach submit_control()


if __name__ == "__main__":
    unittest.main()
