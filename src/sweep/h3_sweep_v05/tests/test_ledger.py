"""Software-only tests for the v0.5 ledger module (tasks T1.4, T3.2 and T3.3).

The T1.4 tests fix the structural contract: ledger.py imports from the
package and carries its documented responsibility from Implementation.md
section 3.

The T3.2 tests fix the Phase 2 layer: the driver-owned ledger generates
one expected frame per sweep point and per archived motor, through the
archived v0.3.5.1 command encoder (MotorCommand / encode_command),
preserving the exact archived motor order and exact archived encoded
bytes. The archived smc3.py is re-executed verbatim here as an
independent reference; the module under test is never asked to
re-implement it. Nothing here touches hardware.

The T3.3 tests exercise the verification layer: the driver's three closed
write-attempt records for a point are compared, in journal order
(``attempt_seq``), against the three expected frames the ledger
registered, and the ledger's answer must say verified only when every
submitted frame matched its expected bytes, byte counts and status
exactly. Missing frames, extra attempts, SHORT writes and ERROR
records, wrong frames and wrong motor order all refuse verification and
are reported as mismatches, never raised; a malformed batch does raise.
The attempt records here are spelled out in the recorder's closed-attempt
schema (Implementation.md section 5, task T2.5/T2.6) because the ledger
does not import the recorder; nothing here opens a serial device.

Run directly:
    python src/sweep/h3_sweep_v05/tests/test_ledger.py
"""
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../h3_sweep_v05/tests
sys.path.insert(0, str(HERE.parent.parent))         # .../src/sweep holds h3_sweep_v05

from h3_sweep_v05 import ledger
from h3_sweep_v05.ledger import (
    ARCHIVE_DIR,
    ARCHIVE_MOTOR_ORDER,
    REQUIRED_RECORD_FIELDS,
    ExpectedFrame,
    FrameMismatch,
    LedgerError,
    SweepPoint,
    VerificationResult,
    expected_frames,
    Ledger,
)

# The ledger deliberately does not import the recorder (task T1.4), and the
# archived recorder guard (task T2.8) allows the OK/SHORT/ERROR words to be
# bound in exactly one module, so the tests pin the canonical OK word from
# recorder.py rather than expecting the ledger to define its own copy.
from h3_sweep_v05.recorder import ATTEMPT_STATUS_OK

STATUS_OK = ATTEMPT_STATUS_OK

ARCHIVE_HARNESS = (
    HERE.parents[3]
    / "ChatGPT-Archive"
    / "H3_v0.3.5.1_commandhub_diagnostic"
)
ARCHIVED_SMC3_PATH = ARCHIVE_HARNESS / "smc3.py"

LEDGER_PATH = HERE.parent / "ledger.py"      # the module under test
LEDGER_SOURCE = LEDGER_PATH.read_text(encoding="utf-8")
LEDGER_DOC = ledger.__doc__ or ""


def load_archived_encoder():
    """exec the archived smc3.py verbatim, exactly like the ledger does.

    The archived source opens with ``import serial``; a stub is installed
    for the duration of the exec only (no port exists, nothing is sent) and
    any pre-existing ``serial`` entry is restored afterwards.
    """
    src = ARCHIVED_SMC3_PATH.read_text(encoding="utf-8")
    mod = {}
    stub = None
    if "serial" not in sys.modules:
        stub = types.SimpleNamespace()
        sys.modules["serial"] = stub
    try:
        exec(src, mod)
    finally:
        if stub is not None:
            del sys.modules["serial"]
    return mod


# ---------------------------------------------------------------- Phase 1 — T1.4


class LedgerTests(unittest.TestCase):
    def test_ledger_module_is_importable(self):
        """The ledger module imports from the package without error."""
        self.assertEqual(ledger.__name__, "h3_sweep_v05.ledger")
        self.assertEqual(ledger.__file__, str(LEDGER_PATH))

    def test_package_identity(self):
        self.assertEqual(ledger.__package__, "h3_sweep_v05")

    def test_module_docstring_describes_responsibility(self):
        """The ledger's docstring states its documented responsibility."""
        self.assertIn("expected-frame ledger", LEDGER_DOC)
        self.assertIn("archived v0.3.5.1 command encoder", LEDGER_DOC)
        self.assertIn("exact motor order", LEDGER_DOC)
        self.assertIn("exact encoded bytes", LEDGER_DOC)

    def test_no_siblings_imported(self):
        """T1.4 placeholders stay independent: ledger.py imports no sibling."""
        for sibling in ("recorder", "driver", "eventslog", "csvlog"):
            self.assertNotIn(f"from {sibling} import", LEDGER_SOURCE)
            self.assertNotIn(f"from h3_sweep_v05.{sibling} import", LEDGER_SOURCE)
            self.assertNotIn(f"import {sibling}", LEDGER_SOURCE)


# ---------------------------------------------------------------- Phase 2 — T3.2


class ExpectedFrameTests(unittest.TestCase):
    """The expected-frame layer must agree with the archived encoder."""

    def test_generated_frames_match_archived_encoder_bytes_exactly(self):
        """Every ledger frame is byte-for-byte the archived encode_command."""
        arch = load_archived_encoder()
        point = SweepPoint(
            point_id=7,
            description="triad",
            motor_positions={"A": 100, "B": 1023, "C": 0},
        )
        frames = expected_frames(point)
        expected = [
            arch["encode_command"](m, point.motor_positions[m])
            for m in ledger.ARCHIVE_MOTOR_ORDER
        ]
        self.assertEqual([bytes(f.frame_bytes) for f in frames], expected)

    def test_motor_order_matches_archive(self):
        """Frames follow the archived MOTORS order regardless of input order."""
        arch = load_archived_encoder()
        point = SweepPoint(
            point_id=1,
            description="center",
            motor_positions={"C": 10, "A": 11, "B": 12},
        )
        frames = expected_frames(point)
        self.assertEqual([f.motor for f in frames], list(arch["MOTORS"]))
        self.assertEqual(list(ARCHIVE_MOTOR_ORDER), list(arch["MOTORS"]))

    def test_positions_are_archived_motor_command_values(self):
        """The ledger's per-frame position equals the archived MotorCommand's."""
        arch = load_archived_encoder()
        point = SweepPoint(
            point_id=3,
            description="asymmetric",
            motor_positions={"A": 5, "B": 1023, "C": 0},
        )
        frames = expected_frames(point)
        self.assertEqual(
            [f.position for f in frames],
            [arch["MotorCommand"](m, point.motor_positions[m]).position
             for m in arch["MOTORS"]],
        )

    def test_ledger_registers_points_and_frames(self):
        """Sweep-point association is the documented ledger interface."""
        sweep = Ledger()
        points = [
            SweepPoint(
                point_id=i,
                description=f"p{i}",
                motor_positions={
                    m: i * 100 + k for k, m in enumerate(ledger.ARCHIVE_MOTOR_ORDER)
                },
            )
            for i in (1, 2, 3)
        ]
        for p in points:
            self.assertEqual(len(sweep.register_point(p)), 3)
        self.assertEqual([p.point_id for p in sweep.known_points()], [1, 2, 3])
        for p in points:
            self.assertEqual(
                [bytes(f.frame_bytes) for f in sweep.expected_frames(p.point_id)],
                [bytes(f.frame_bytes) for f in expected_frames(p)],
            )
            self.assertEqual(
                [bytes(f.frame_bytes) for f in sweep.frames_for(p.point_id)],
                [bytes(f.frame_bytes) for f in expected_frames(p)],
            )

    def test_ledger_rejects_incomplete_or_unknown_motors(self):
        """A sweep point must cover exactly the archived motors."""
        sweep = Ledger()
        with self.assertRaises(LedgerError):
            sweep.register_point(
                SweepPoint(point_id=4, description="missing", motor_positions={"A": 1})
            )
        with self.assertRaises(LedgerError):
            sweep.register_point(
                SweepPoint(point_id=4, description="unknown", motor_positions={"D": 1})
            )
        self.assertEqual(sweep.known_points(), ())

    def test_ledger_point_ids_must_be_unique(self):
        sweep = Ledger()
        sweep.register_point(
            SweepPoint(point_id=5, description="a", motor_positions={"A": 1, "B": 2, "C": 3})
        )
        with self.assertRaises(LedgerError):
            sweep.register_point(
                SweepPoint(point_id=5, description="b", motor_positions={"A": 4, "B": 5, "C": 6})
            )
        self.assertIsNone(sweep.expected_frames(99))

    def test_ledger_never_mutates_its_input(self):
        """register_point leaves the caller's point and its mapping alone."""
        motors = {"A": 10, "B": 20, "C": 30}
        point = SweepPoint(point_id=6, description="frozen", motor_positions=motors)
        sweep = Ledger()
        frames = sweep.register_point(point)
        self.assertEqual(motors, {"A": 10, "B": 20, "C": 30})
        self.assertEqual(
            [bytes(f.frame_bytes) for f in sweep.expected_frames(6)],
            [bytes(f.frame_bytes) for f in expected_frames(point)],
        )

    def test_ledger_archive_path_helpers(self):
        """The ledger locates the archived encoder, not the sweep package."""
        self.assertEqual(str(ARCHIVE_DIR), str(ARCHIVE_HARNESS.parent))
        self.assertIn("ChatGPT-Archive", str(ARCHIVE_DIR))


# ---------------------------------------------------------------- Phase 2 — T3.3


def attempt_record(seq, frame_bytes, status=STATUS_OK, returned=None, expected=None):
    """One closed write-attempt record, in the recorder's attempt schema.

    Task T1.4 keeps the ledger independent of the recorder, so the tests
    spell out the record the recorder writes (Implementation.md section 5,
    tasks T2.5 and T2.6) rather than importing it: ``frame_bytes`` is what
    the attempt tried to send, ``returned_count`` is the byte count the
    serial proxy reported (``None`` when the write raised), ``expected_count``
    is the payload length taken before the write, and ``status`` is the
    recorder's OK/SHORT/ERROR vocabulary. Timestamps are fixed, so every
    batch is deterministic.
    """
    frame_bytes = bytes(frame_bytes)
    return {
        "attempt_seq": seq,
        "timestamp": f"2026-11-06T00:00:{seq:02d}.000000",
        "monotonic_timestamp": 1000.0 + seq,
        "frame_bytes": frame_bytes,
        "returned_count": len(frame_bytes) if returned is None else returned,
        "expected_count": len(frame_bytes) if expected is None else expected,
        "status": status,
        "exception": None,
    }


def fresh_ledger_with_point(point_id, positions):
    """A ledger holding exactly one registered point, plus its frames."""
    sweep = Ledger()
    frames = sweep.register_point(
        SweepPoint(point_id=point_id, description=f"p{point_id}", motor_positions=dict(positions))
    )
    return sweep, frames


class VerificationTests(unittest.TestCase):
    """``Ledger.verify``: closed attempt batches against registered frames."""

    def test_attempt_helper_carries_the_full_attempt_schema(self):
        """The helper records are the schema the ledger will accept."""
        self.assertEqual(
            set(attempt_record(1, b"\x02\x03\x04\x05\x06")), REQUIRED_RECORD_FIELDS
        )

    def test_verified_point_reports_no_mismatches(self):
        """Three exact frames, all OK: the point is verified."""
        sweep, frames = fresh_ledger_with_point(11, {"A": 100, "B": 600, "C": 900})
        batch = tuple(attempt_record(seq, frame.frame_bytes)
                      for seq, frame in enumerate(frames, start=4))
        result = sweep.verify(11, batch)
        self.assertEqual(result, VerificationResult(
            point_id=11, verified=True, frames_match=True, counts_match=True,
            statuses_match=True, mismatches=(),
        ))

    def test_sequence_numbers_need_no_absolute_value(self):
        """Verification reads order, not the point's snapshot baseline."""
        sweep, frames = fresh_ledger_with_point(12, {"A": 1, "B": 2, "C": 3})
        batch = tuple(attempt_record(seq, frame.frame_bytes)
                      for seq, frame in enumerate(frames, start=97))
        self.assertTrue(sweep.verify(12, batch).verified)

    def test_verified_batch_agrees_with_archived_encoder_bytes(self):
        """Bytes the archived encoder produced verify against the ledger."""
        arch = load_archived_encoder()
        positions = {"A": 12, "B": 340, "C": 1023}
        sweep, frames = fresh_ledger_with_point(13, positions)
        batch = tuple(
            attempt_record(seq, arch["encode_command"](motor, positions[motor]))
            for seq, motor in enumerate(arch["MOTORS"], start=1)
        )
        self.assertEqual([bytes(r["frame_bytes"]) for r in batch],
                         [bytes(f.frame_bytes) for f in frames])
        self.assertTrue(sweep.verify(13, batch).verified)

    def test_wrong_frame_bytes_fail_verification(self):
        """A frame the ledger never expected fails the point."""
        sweep, frames = fresh_ledger_with_point(14, {"A": 100, "B": 600, "C": 900})
        arch = load_archived_encoder()
        wrong = arch["encode_command"]("B", 601)
        batch = [attempt_record(seq, frame.frame_bytes)
                 for seq, frame in enumerate(frames, start=1)]
        batch[1]["frame_bytes"] = wrong
        result = sweep.verify(14, tuple(batch))
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 1)
        self.assertEqual(mismatch.motor, "B")
        self.assertEqual(mismatch.position, frames[1].position)
        self.assertEqual(bytes(mismatch.frame_bytes), bytes(frames[1].frame_bytes))
        self.assertEqual(bytes(mismatch.recorded["frame_bytes"]), bytes(wrong))
        self.assertTrue(mismatch.frame_mismatch)
        self.assertFalse(mismatch.count_mismatch)
        self.assertFalse(mismatch.status_mismatch)

    def test_frames_of_the_wrong_motor_order_fail_verification(self):
        """Exact bytes are still checked in the archived motor order."""
        sweep, frames = fresh_ledger_with_point(15, {"A": 11, "B": 222, "C": 333})
        batch = tuple(
            attempt_record(seq, frame.frame_bytes)
            for seq, frame in enumerate((frames[0], frames[2], frames[1]), start=1)
        )
        result = sweep.verify(15, batch)
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)
        self.assertEqual([m.index for m in result.mismatches], [1, 2])
        self.assertEqual([m.motor for m in result.mismatches], ["B", "C"])

    def test_missing_attempt_leaves_an_expected_frame_unmatched(self):
        """Two closed attempts cannot verify a three-frame point."""
        sweep, frames = fresh_ledger_with_point(16, {"A": 100, "B": 200, "C": 300})
        batch = tuple(attempt_record(seq, frame.frame_bytes)
                      for seq, frame in enumerate(frames[:2], start=1))
        result = sweep.verify(16, batch)
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertFalse(result.counts_match)
        self.assertFalse(result.statuses_match)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 2)
        self.assertEqual(mismatch.motor, "C")
        self.assertIsNone(mismatch.recorded)
        self.assertTrue(mismatch.frame_mismatch)
        self.assertTrue(mismatch.count_mismatch)
        self.assertTrue(mismatch.status_mismatch)

    def test_extra_attempt_is_reported_as_unexpected(self):
        """A fourth closed attempt never matches a three-frame point."""
        sweep, frames = fresh_ledger_with_point(17, {"A": 5, "B": 512, "C": 1023})
        arch = load_archived_encoder()
        batch = tuple(attempt_record(seq, frame.frame_bytes)
                      for seq, frame in enumerate(frames, start=1))
        extra = attempt_record(4, arch["encode_command"]("A", 5))
        result = sweep.verify(17, batch + (extra,))
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertTrue(result.counts_match)
        self.assertTrue(result.statuses_match)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 3)
        self.assertIsNone(mismatch.motor)
        self.assertIsNone(mismatch.position)
        self.assertIsNone(mismatch.frame_bytes)
        self.assertIs(mismatch.recorded, extra)
        self.assertTrue(mismatch.frame_mismatch)
        self.assertFalse(mismatch.count_mismatch)
        self.assertFalse(mismatch.status_mismatch)

    def test_short_write_never_verifies(self):
        """Fewer returned bytes than expected fails the point (T2.8/§6 rule)."""
        sweep, frames = fresh_ledger_with_point(18, {"A": 700, "B": 1, "C": 2})
        batch = [attempt_record(seq, frame.frame_bytes)
                 for seq, frame in enumerate(frames, start=1)]
        batch[1]["returned_count"] = 3
        batch[1]["status"] = "SHORT"
        result = sweep.verify(18, tuple(batch))
        self.assertFalse(result.verified)
        self.assertTrue(result.frames_match)
        self.assertFalse(result.counts_match)
        self.assertFalse(result.statuses_match)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 1)
        self.assertEqual(mismatch.motor, "B")
        self.assertFalse(mismatch.frame_mismatch)
        self.assertTrue(mismatch.count_mismatch)
        self.assertTrue(mismatch.status_mismatch)

    def test_error_record_never_verifies(self):
        """A raised write leaves no returned count and fails the point."""
        sweep, frames = fresh_ledger_with_point(19, {"A": 3, "B": 4, "C": 5})
        batch = [attempt_record(seq, frame.frame_bytes)
                 for seq, frame in enumerate(frames, start=1)]
        batch[0]["returned_count"] = None
        batch[0]["status"] = "ERROR"
        batch[0]["exception"] = "OSError: transport closed mid-write"
        result = sweep.verify(19, tuple(batch))
        self.assertFalse(result.verified)
        self.assertTrue(result.frames_match)
        self.assertFalse(result.counts_match)
        self.assertFalse(result.statuses_match)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.index, 0)
        self.assertEqual(mismatch.motor, "A")
        self.assertFalse(mismatch.frame_mismatch)
        self.assertTrue(mismatch.count_mismatch)
        self.assertTrue(mismatch.status_mismatch)
        self.assertEqual(mismatch.recorded["exception"], "OSError: transport closed mid-write")

    def test_every_failure_is_reported_together(self):
        """A point with several problems lists one mismatch per index."""
        sweep, frames = fresh_ledger_with_point(20, {"A": 40, "B": 50, "C": 60})
        arch = load_archived_encoder()
        batch = (
            attempt_record(1, frames[0].frame_bytes),
            attempt_record(2, arch["encode_command"]("B", 51), status="SHORT", returned=4),
            attempt_record(3, frames[2].frame_bytes, status="ERROR", returned=None),
        )
        result = sweep.verify(20, batch)
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertFalse(result.counts_match)
        self.assertFalse(result.statuses_match)
        self.assertEqual([m.index for m in result.mismatches], [1, 2])

    def test_verify_rejects_unregistered_point(self):
        """Nothing can be compared against a point the ledger never owned."""
        sweep, _frames = fresh_ledger_with_point(21, {"A": 1, "B": 2, "C": 3})
        with self.assertRaises(LedgerError):
            sweep.verify(22, ())

    def test_verify_rejects_unordered_batch(self):
        """Positional comparison needs the Barrier's journal order."""
        sweep, frames = fresh_ledger_with_point(23, {"A": 1, "B": 2, "C": 3})
        unordered = tuple(attempt_record(seq, frame.frame_bytes)
                          for seq, frame in zip((1, 3, 2), frames))
        with self.assertRaises(LedgerError):
            sweep.verify(23, unordered)

    def test_verify_rejects_records_that_are_not_closed_attempts(self):
        """A partial or foreign record cannot stand in for an attempt."""
        sweep, frames = fresh_ledger_with_point(24, {"A": 1, "B": 2, "C": 3})
        partial = attempt_record(1, frames[0].frame_bytes)
        del partial["exception"]
        del partial["monotonic_timestamp"]
        with self.assertRaises(LedgerError):
            sweep.verify(24, (partial,) + tuple(
                attempt_record(seq, frame.frame_bytes)
                for seq, frame in enumerate(frames[1:], start=2)
            ))
        with self.assertRaises(LedgerError):
            sweep.verify(24, (frames[0], frames[1], frames[2]))
        with self.assertRaises(LedgerError):
            sweep.verify(24, {"attempt_seq": 1})

    def test_verify_never_mutates_the_ledger_or_the_batch(self):
        """A failed comparison leaves ledger frames and records untouched."""
        sweep, frames = fresh_ledger_with_point(25, {"A": 10, "B": 20, "C": 30})
        batch = [attempt_record(seq, frame.frame_bytes)
                 for seq, frame in enumerate(frames, start=1)]
        batch[2]["frame_bytes"] = b"\x02\x03\x04"
        batch[2]["status"] = "SHORT"
        # snapshot both sides before the comparison; verify may not move either
        ledger_before = [bytes(f.frame_bytes) for f in sweep.expected_frames(25)]
        records_before = [(bytes(r["frame_bytes"]), r["status"]) for r in batch]
        result = sweep.verify(25, batch)
        self.assertFalse(result.verified)
        self.assertEqual(ledger_before,
                         [bytes(f.frame_bytes) for f in sweep.expected_frames(25)])
        self.assertEqual(records_before,
                         [(bytes(r["frame_bytes"]), r["status"]) for r in batch])
        self.assertEqual([bytes(r["frame_bytes"]) for r in batch],
                         [bytes(frames[0].frame_bytes), bytes(frames[1].frame_bytes),
                          b"\x02\x03\x04"])
        self.assertEqual(batch[0]["status"], STATUS_OK)
        # the report hands out copies, so a caller cannot mutate ledger frames
        mismatch = result.mismatches[0]
        self.assertIsInstance(mismatch.frame_bytes, bytes)

    def test_control_frames_are_not_a_shortcut_for_motor_frames(self):
        """Five-byte frames that are not the point's frames still fail."""
        sweep, frames = fresh_ledger_with_point(26, {"A": 1, "B": 2, "C": 3})
        arch = load_archived_encoder()
        control = arch["encode_command"]("A", arch["CENTER_POSITION"])
        batch = (attempt_record(1, control), attempt_record(2, control),
                 attempt_record(3, control))
        result = sweep.verify(26, batch)
        self.assertFalse(result.verified)
        self.assertFalse(result.frames_match)
        self.assertEqual([m.index for m in result.mismatches], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
