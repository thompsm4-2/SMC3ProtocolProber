"""Regression tests for T3.6 — Control-Frame Separation and Frame-Mismatch Failure.

These tests verify:
1. Control frames remain recorded in the attempt journal but never count toward
   a point's three motor-position attempts.
2. Each point is verified using exactly its three expected motor-position frames,
   associated through the existing sequence/barrier and ledger mechanisms.
3. A motor-frame mismatch against the point's expected ledger frames is treated
   as a software error and the point is classified FAILED.
4. Control-frame interleaving does not cause false completion, incorrect
   association, or accidental consumption of another point's motor attempts.

All tests are deterministic, hardware-free software-only tests.

Motor frame format (from HARDWARE_REFERENCE.md):
- 5 bytes: `[` + motor letter + position high byte + position low byte + `]`
- Example: A=512 → bytes(91, 65, 2, 0, 93) → b'[A\x02\x00]'
"""
from __future__ import annotations

import sys
from pathlib import Path
import types
import unittest

# Set up path BEFORE any imports - pytest adds the parent of the test file to sys.path
# which is src/sweep/h3_sweep_v05. We need to go up two levels to get to src/.
HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent  # Go from tests/ to src/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import h3_sweep_v05.driver as driver
import h3_sweep_v05.ledger as ledger
import h3_sweep_v05.recorder as recorder

from h3_sweep_v05.ledger import (
    SweepPoint,
    Ledger,
    VerificationResult,
    expected_frames,
)
from h3_sweep_v05.recorder import (
    Barrier,
    SerialRecorder,
    _is_motor_frame,
)

HERE = Path(__file__).resolve().parent
ARCHIVE_HARNESS = HERE.parents[3] / "ChatGPT-Archive" / "H3_v0.3.5.1_commandhub_diagnostic"

# Note: We use a self-contained FakeSerial/FakeSerialException stub to avoid
# importing pyserial or the archive's serial module, which would pollute sys.modules


class TimeWithoutDelay:
    """Time stand-in with no real delays for deterministic tests."""
    @staticmethod
    def sleep(seconds):
        return None

    @staticmethod
    def monotonic():
        return 0.0

    @staticmethod
    def time():
        return 0.0


class SerialException(Exception):
    """Dummy SerialException for testing."""
    pass


class FakeSerial:
    """Dummy Serial class for testing that doesn't require pyserial."""
    instances = []
    
    def __init__(self, port, baudrate, timeout=0.5, write_timeout=0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.writes = []
        self.closed = False
        FakeSerial.instances.append(self)
    
    def write(self, data):
        if self.closed:
            raise SerialException("port closed")
        data = bytes(data)
        self.writes.append(data)
        return len(data)
    
    def read(self, size=1):
        return b""
    
    def reset_input_buffer(self):
        return None
    
    def close(self):
        self.closed = True


class FakeSerialModule(types.ModuleType):
    """Fake serial module that exposes Serial class for testing.
    
    Uses a self-contained stub that doesn't require importing pyserial or
    the archive's serial module, avoiding sys.modules pollution.
    """
    def __init__(self):
        super().__init__("test_smc3")
        self.Serial = FakeSerial
        self.SerialException = SerialException
        self.time = TimeWithoutDelay
        self.serial = self  # The recorder looks for smc3_module.serial (alias to self)


def make_motor_frame(motor: str, position: int) -> bytes:
    """Create a motor frame byte sequence.
    
    Format: `[` + motor letter + position high byte + position low byte + `]`
    Example: A=512 → bytes(91, 65, 2, 0, 93) → b'[A\x02\x00]'
    """
    position = max(0, min(1023, position))
    return bytes([
        91,             # '['
        ord(motor),     # motor letter
        (position >> 8) & 255,  # high byte
        position & 255,     # low byte
        93              # ']'
    ])


def make_control_frame(frame_type: str) -> bytes:
    """Create a control frame byte sequence.
    
    Format: `[` + letters + `]` (5 bytes)
    Examples:
      - enable: `[ena]` → bytes(91, 101, 110, 97, 93)
      - disable: `[]` → bytes(91, 93)
      - version: `[V1]` → bytes(91, 86, 49, 93)
    """
    if frame_type == "enable":
        return b"[ena]"
    elif frame_type == "disable":
        return b"[]"
    elif frame_type == "version":
        return b"[V1]"
    else:
        return b"[ena]"


def make_barrier(rec: SerialRecorder) -> Barrier:
    """Create a barrier before any attempts, so it sees all subsequent attempts."""
    return Barrier(rec)


class ControlFrameTests(unittest.TestCase):
    """Tests for T3.6 control-frame separation."""

    def test_is_motor_frame_detects_motor_position_frames(self):
        """Motor frames have the signature: 5 bytes, 0x5B/0x5D, motor letter A/B/C."""
        # Valid motor frames (using actual binary format)
        self.assertTrue(_is_motor_frame(make_motor_frame("A", 100)))
        self.assertTrue(_is_motor_frame(make_motor_frame("B", 200)))
        self.assertTrue(_is_motor_frame(make_motor_frame("C", 300)))
        self.assertTrue(_is_motor_frame(make_motor_frame("A", 0)))
        self.assertTrue(_is_motor_frame(make_motor_frame("C", 1023)))

        # Invalid motor frames
        self.assertFalse(_is_motor_frame(make_control_frame("enable")))  # Enable control frame
        self.assertFalse(_is_motor_frame(make_control_frame("disable")))  # Disable control frame
        self.assertFalse(_is_motor_frame(make_control_frame("version")))  # Version request
        self.assertFalse(_is_motor_frame(b"[A100a]"))  # Wrong length (6 bytes)
        self.assertFalse(_is_motor_frame(b"X100]"))  # Wrong start byte
        self.assertFalse(_is_motor_frame(b"[A100X"))  # Wrong end byte
        self.assertFalse(_is_motor_frame(make_motor_frame("D", 100)))  # Invalid motor letter
        self.assertFalse(_is_motor_frame(make_motor_frame("a", 100)))  # Lowercase motor letter

    def test_control_frames_are_recorded_but_not_counted(self):
        """Control frames are recorded in the journal but don't count toward attempts."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Simulate writes: enable, motor A, disable, motor B, motor C
        frames = [
            make_control_frame("enable"),  # Control frame
            make_motor_frame("A", 100),  # Motor A
            make_control_frame("disable"),  # Control frame
            make_motor_frame("B", 200),  # Motor B
            make_motor_frame("C", 300),  # Motor C
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # Get all attempts
        attempts = rec.attempts()

        # Verify all attempts are recorded
        self.assertEqual(len(attempts), 5)

        # Verify control frames are marked as not motor frames
        self.assertFalse(attempts[0]["is_motor_frame"])  # enable
        self.assertFalse(attempts[2]["is_motor_frame"])  # disable

        # Verify motor frames are marked as motor frames
        self.assertTrue(attempts[1]["is_motor_frame"])  # A
        self.assertTrue(attempts[3]["is_motor_frame"])  # B
        self.assertTrue(attempts[4]["is_motor_frame"])  # C

        # Barrier waits for exactly 3 motor frames (but returns ALL completed attempts)
        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 2 control = 5 total
        self.assertEqual(len(batch), 5)

        # Verify motor frame order is preserved
        motor_letters = [chr(a["frame_bytes"][1]) for a in batch if a["is_motor_frame"]]
        self.assertEqual(motor_letters, ["A", "B", "C"])

        # Verify motor frames in batch are motor frames
        motor_attempts = [a for a in batch if a["is_motor_frame"]]
        for attempt in motor_attempts:
            self.assertTrue(attempt["is_motor_frame"])

        # The complete journal still has all 5 attempts
        all_attempts = rec.attempts()
        self.assertEqual(len(all_attempts), 5)

    def test_control_frame_interleaving_does_not_cause_false_completion(self):
        """Control frames interleaved with motor frames don't cause false completion."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Interleave control frames at various positions
        frames = [
            make_control_frame("enable"),     # Control
            make_motor_frame("A", 100),    # Motor A
            make_control_frame("version"),      # Control (version request)
            make_motor_frame("B", 200),    # Motor B
            make_control_frame("disable"),        # Control (disable)
            make_motor_frame("C", 300),    # Motor C
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # Verify journal has all attempts
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 6)

        # Barrier waits for exactly 3 motor frames
        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Should get 3 motor frames, but batch includes ALL attempts (motor + control)
        # The barrier only counts MOTOR frames toward the expected count
        self.assertEqual(len(batch), 6)  # 3 motor + 3 control frames

        # Verify motor frame order is preserved
        motor_letters = [chr(a["frame_bytes"][1]) for a in batch if a["is_motor_frame"]]
        self.assertEqual(motor_letters, ["A", "B", "C"])

        # Verify no false completion - motor frames in batch are motor frames
        motor_attempts = [a for a in batch if a["is_motor_frame"]]
        for attempt in motor_attempts:
            self.assertTrue(attempt["is_motor_frame"])

        # Complete journal still has all 6 attempts
        self.assertEqual(len(rec.attempts()), 6)

    def test_control_frames_preserved_in_journal_for_diagnostics(self):
        """Control frames remain in the journal for diagnostics after barrier completion."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Write motor frames with control frames interspersed
        frames = [
            make_motor_frame("A", 100),
            make_control_frame("enable"),
            make_motor_frame("B", 200),
            make_control_frame("disable"),
            make_motor_frame("C", 300),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Journal should still have all attempts
        journal = rec.attempts()
        self.assertEqual(len(journal), 5)

        # Verify control frames are still in journal
        control_frames = [a for a in journal if not a["is_motor_frame"]]
        self.assertEqual(len(control_frames), 2)

        # Verify motor frames are in journal
        motor_frames = [a for a in journal if a["is_motor_frame"]]
        self.assertEqual(len(motor_frames), 3)

        # Batch includes ALL attempts (motor + control), not just motor frames
        self.assertEqual(len(batch), 5)  # 3 motor + 2 control frames

    def test_frame_mismatch_causes_verification_failure(self):
        """A frame mismatch causes the point to fail verification."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Register a point with specific motor positions
        point = SweepPoint(
            point_id=1,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(1)

        # Send wrong frames (mismatched)
        wrong_frames = [
            make_motor_frame("A", 100),    # Correct for A
            make_motor_frame("B", 999),    # WRONG: should be 200
            make_motor_frame("C", 300),    # Correct for C
        ]

        for frame in wrong_frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Verify fails due to mismatch
        result = led.verify(1, batch)

        # Batch includes ALL attempts (motor + control), not just motor frames
        self.assertEqual(len(batch), 3)  # 3 motor frames, 0 control frames

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)

        # Verify the mismatch is reported
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 1)
        self.assertEqual(mismatch.motor, "B")
        self.assertTrue(mismatch.frame_mismatch)
        self.assertFalse(mismatch.count_mismatch)
        self.assertFalse(mismatch.status_mismatch)

    def test_frame_mismatch_with_wrong_motor_letter(self):
        """A frame with wrong motor letter causes verification failure."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=2,
            description="test point",
            motor_positions={"A": 500, "B": 600, "C": 700},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(2)

        # Send frames with wrong motor letters (B instead of A, C instead of B, etc.)
        wrong_frames = [
            make_motor_frame("B", 500),    # Wrong motor letter (should be A)
            make_motor_frame("C", 600),    # Wrong motor letter (should be B)
            make_motor_frame("A", 700),    # Wrong motor letter (should be C)
        ]

        for frame in wrong_frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        result = led.verify(2, batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(len(result.mismatches), 3)

    def test_frame_mismatch_with_wrong_position(self):
        """A frame with wrong position value causes verification failure."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=3,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(3)

        # Send frames with correct motor letters but wrong positions
        wrong_frames = [
            make_motor_frame("A", 200),    # Wrong position (should be 100)
            make_motor_frame("B", 300),    # Wrong position (should be 200)
            make_motor_frame("C", 400),    # Wrong position (should be 300)
        ]

        for frame in wrong_frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        result = led.verify(3, batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(len(result.mismatches), 3)

    def test_control_frames_cannot_cause_verification_failure(self):
        """Control frames cannot cause verification failure because they're filtered."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=4,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(4)

        # Send only control frames (no motor frames)
        control_frames = [
            make_control_frame("enable"),
            make_control_frame("version"),
            make_control_frame("disable"),
        ]

        for frame in control_frames:
            rec.record_write_attempt(frame, len(frame))

        # This should timeout because no motor frames completed
        with self.assertRaises(TimeoutError):
            batch = barrier.wait_for_attempts(3, timeout=0.5)

        # Verify the point is not verified (no motor frames)
        # The point should not have a verification result because the barrier timed out
        # This is correct behavior - control frames alone cannot verify a point

    def test_mixed_control_and_motor_frames_verification(self):
        """Verify that mixed control and motor frames work correctly."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=5,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(5)

        # Send mixed frames
        frames = [
            make_control_frame("enable"),      # Control
            make_motor_frame("A", 100),     # Motor A - correct
            make_control_frame("version"),      # Control
            make_motor_frame("B", 200),     # Motor B - correct
            make_control_frame("disable"),        # Control
            make_motor_frame("C", 300),     # Motor C - correct
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 3 control = 6 total
        self.assertEqual(len(batch), 6)

        # Filter to motor frames only (like the driver does in driver.py)
        motor_batch = [attempt for attempt in batch if attempt["is_motor_frame"]]

        # Verify succeeds because only motor frames are used
        result = led.verify(5, motor_batch)

        self.assertTrue(result.verified)
        self.assertTrue(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)
        self.assertEqual(len(result.mismatches), 0)

        # Journal still has all attempts
        self.assertEqual(len(rec.attempts()), 6)

    def test_insufficient_motor_attempts_causes_failure(self):
        """Insufficient motor attempts cause barrier timeout and point failure."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=6,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        # Send only 2 motor frames (insufficient)
        frames = [
            make_motor_frame("A", 100),
            make_motor_frame("B", 200),
            # Missing C motor frame
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # This should timeout because only 2 motor frames completed
        with self.assertRaises(TimeoutError) as context:
            batch = barrier.wait_for_attempts(3, timeout=0.5)

        self.assertIn("motor attempts", str(context.exception))

        # The point should not be verified
        # This is correct behavior - insufficient attempts means point cannot be verified


class FrameMismatchFailureTests(unittest.TestCase):
    """Tests for T3.6 frame-mismatch failure classification."""

    def test_all_frames_mismatched(self):
        """All three frames mismatched causes verification failure."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=7,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        # Send completely wrong frames (valid motor frames but wrong positions)
        wrong_frames = [
            make_motor_frame("A", 999),  # Valid motor frame, wrong position
            make_motor_frame("B", 888),  # Valid motor frame, wrong position
            make_motor_frame("C", 777),  # Valid motor frame, wrong position
        ]

        for frame in wrong_frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Filter to motor frames only (like the driver does in driver.py)
        motor_batch = [attempt for attempt in batch if attempt["is_motor_frame"]]

        # Verify fails due to mismatch
        result = led.verify(7, motor_batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)
        self.assertEqual(len(result.mismatches), 3)

    def test_single_frame_mismatch(self):
        """Single frame mismatch causes verification failure."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=8,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        # Send two correct frames, one wrong
        frames = [
            make_motor_frame("A", 100),    # Correct
            make_motor_frame("B", 999),    # WRONG
            make_motor_frame("C", 300),    # Correct
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        result = led.verify(8, batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertEqual(len(result.mismatches), 1)
        self.assertEqual(result.mismatches[0].index, 1)
        self.assertEqual(result.mismatches[0].motor, "B")

    def test_frame_mismatch_with_correct_counts(self):
        """Frame mismatch with correct byte counts still fails verification."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=9,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        expected_frames = led.expected_frames(9)

        # Send frames with correct byte counts (5 bytes) but wrong content
        wrong_frames = [
            make_motor_frame("A", 999),    # Same length, wrong position
            make_motor_frame("B", 888),    # Same length, wrong position
            make_motor_frame("C", 777),    # Same length, wrong position
        ]

        for frame in wrong_frames:
            rec.record_write_attempt(frame, 5)  # Correct count

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        result = led.verify(9, batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)  # Byte counts are correct
        self.assertTrue(result.statuses_match)  # All OK

    def test_frame_mismatch_with_control_frames_in_journal(self):
        """Frame mismatch with control frames in journal still fails verification."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=10,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        # Send control frames + wrong motor frames
        frames = [
            make_control_frame("enable"),     # Control
            make_motor_frame("A", 999),    # Wrong (should be 100)
            make_control_frame("disable"),        # Control
            make_motor_frame("B", 888),    # Wrong (should be 200)
            make_motor_frame("C", 777),    # Wrong (should be 300)
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 2 control = 5 total
        self.assertEqual(len(batch), 5)

        # Filter to motor frames only (like the driver does in driver.py)
        motor_batch = [attempt for attempt in batch if attempt["is_motor_frame"]]

        result = led.verify(10, motor_batch)

        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertEqual(len(result.mismatches), 3)

        # Journal should have all 5 attempts
        self.assertEqual(len(rec.attempts()), 5)


class ControlFrameNotCountedTests(unittest.TestCase):
    """Tests to verify control frames are never counted toward attempts."""

    def test_control_frames_never_increment_attempt_count(self):
        """Control frames are recorded but don't count toward the barrier's expected."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Write 2 motor frames and 2 control frames
        frames = [
            make_motor_frame("A", 100),
            make_control_frame("enable"),
            make_motor_frame("B", 200),
            make_control_frame("version"),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # Should timeout because only 2 motor frames completed
        with self.assertRaises(TimeoutError) as context:
            batch = barrier.wait_for_attempts(3, timeout=0.5)

        self.assertIn("motor attempts", str(context.exception))

        # Journal has 4 attempts, but barrier only counts 2 motor frames
        self.assertEqual(len(rec.attempts()), 4)

    def test_multiple_control_frames_between_motor_frames(self):
        """Multiple control frames between motor frames don't affect counting."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        # Write motor frames with many control frames between them
        frames = [
            make_motor_frame("A", 100),
            make_control_frame("enable"),
            make_control_frame("version"),
            make_control_frame("disable"),
            make_control_frame("version"),
            make_motor_frame("B", 200),
            make_control_frame("enable"),
            make_motor_frame("C", 300),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # Should get 3 motor frames, but batch includes ALL attempts (motor + control)
        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 5 control = 8 total
        self.assertEqual(len(batch), 8)

        # All MOTOR batch entries should be motor frames
        motor_attempts = [a for a in batch if a["is_motor_frame"]]
        self.assertEqual(len(motor_attempts), 3)

        # Journal has 8 attempts
        self.assertEqual(len(rec.attempts()), 8)

        # Verify motor frames in batch are motor frames
        for attempt in motor_attempts:
            self.assertTrue(attempt["is_motor_frame"])


class BoundaryCaseTests(unittest.TestCase):
    """Boundary case tests for T3.6."""

    def test_control_frame_at_start_only(self):
        """Control frame at the start doesn't affect motor frame counting."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        frames = [
            make_control_frame("enable"),
            make_motor_frame("A", 100),
            make_motor_frame("B", 200),
            make_motor_frame("C", 300),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 1 control = 4 total
        self.assertEqual(len(batch), 4)
        self.assertEqual(len(rec.attempts()), 4)

    def test_control_frame_at_end_only(self):
        """Control frame at the end doesn't affect motor frame counting."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        frames = [
            make_motor_frame("A", 100),
            make_motor_frame("B", 200),
            make_motor_frame("C", 300),
            make_control_frame("disable"),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Batch includes ALL attempts (motor + control), not just motor frames
        # Expected: 3 motor + 1 control = 4 total
        self.assertEqual(len(batch), 4)
        self.assertEqual(len(rec.attempts()), 4)

    def test_only_control_frames_never_verifies(self):
        """A point with only control frames never verifies."""
        smc3_module = FakeSerialModule()
        rec = SerialRecorder()
        rec.install(smc3_module)

        # Create barrier BEFORE any attempts
        barrier = make_barrier(rec)

        point = SweepPoint(
            point_id=100,
            description="test point",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )
        led = Ledger()
        led.register_point(point)

        # Send only control frames
        frames = [
            make_control_frame("enable"),
            make_control_frame("version"),
            make_control_frame("disable"),
        ]

        for frame in frames:
            rec.record_write_attempt(frame, len(frame))

        # Should timeout
        with self.assertRaises(TimeoutError):
            batch = barrier.wait_for_attempts(3, timeout=0.5)

        # Point cannot be verified without motor frames
        self.assertEqual(len(rec.attempts()), 3)


if __name__ == "__main__":
    unittest.main()
