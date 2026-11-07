"""Frame ledger for the H3 sweep (v0.5).

Phase 2 (task T3.2) adds the driver-owned expected-frame ledger. Expected
motor frames for every sweep point are generated through the archived v0.3.5.1 command encoder
(``MotorCommand`` and ``encode_command``), so the ledger
preserves the exact motor order and exact encoded bytes of the archived
baseline: this module never re-implements the encoding.

The ledger keeps the mapping from sweep points to their generated expected
frames. Association with attempt records and exact frame verification is
task T3.3, provided by ``Ledger.verify``: this module generates the
expected side and compares one closed write-attempt batch against it.
Point classification remains a later task.

The ledger never touches hardware: the archived encoder is loaded as source,
and its ``serial`` import is satisfied by a stub that is never used, so no
serial port is opened, and frames are generated, never sent.

T3.3 note: ``Ledger.verify`` compares one closed write-attempt batch with
the expected frames registered for a point. The batch must carry the
closed-attempt schema the recorder writes (Implementation.md section 5,
task T2.6), and it must be in journal order: the Barrier hands attempts
to the driver ordered by ``attempt_seq``, and the ledger's expected
frames are in the archived ``MOTORS`` order, so batch entry *i* is
checked against expected frame *i*. Comparison is exact: the ledger's
frame bytes, the returned and expected byte counts (which must agree with
each other and with the ledger frame's length), and the recorded status,
which must be the recorder's OK for a match. A missing attempt leaves
its expected frame unmatched; an unexpected extra attempt never matches.
Frame, byte-count and status mismatches are reported in the result
(the sweep records the problem); only a malformed batch raises.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from collections import namedtuple

ExpectedFrame = namedtuple(
    "ExpectedFrame", ["motor", "position", "frame_bytes"]
)
"""One expected frame for a sweep point, straight from the archived encoder.

``frame_bytes`` is a ``memoryview`` over the archived frame bytes, so
comparisons cannot hand out a mutable buffer."""

SweepPoint = namedtuple(
    "SweepPoint", ["point_id", "description", "motor_positions"]
)
"""A point the driver wants to sweep: an id, a label, and motor targets."""

REQUIRED_RECORD_FIELDS = frozenset(
    (
        "attempt_seq",
        "timestamp",
        "monotonic_timestamp",
        "frame_bytes",
        "returned_count",
        "expected_count",
        "status",
        "exception",
    )
)
"""The closed-attempt schema the recorder writes (Implementation.md section 5,
task T2.6).

The ledger compares the fields the sweep rules name — ``frame_bytes``,
``returned_count``, ``expected_count`` and ``status`` — and requires the
whole schema to be present, so a partial or foreign record can never be
mistaken for a closed attempt. The ledger deliberately does not import
the recorder (task T1.4 keeps the modules independent), so the schema is
restated here as the ledger's own view of that contract. ``status`` is
the recorder's OK/SHORT/ERROR vocabulary; only OK can match. That word is
not restated here as a module constant: the archived recorder guard
(task T2.8) requires recorder.py to be the only v0.5 module that binds it,
so ``verify`` names the word inline and points at recorder.py by comment."""

FrameMismatch = namedtuple(
    "FrameMismatch",
    (
        "index",
        "motor",
        "position",
        "frame_bytes",
        "recorded",
        "frame_mismatch",
        "count_mismatch",
        "status_mismatch",
    ),
)
"""One expected frame that did not match what was recorded.

``index`` is the position inside the point's expected frames, which follow
the archived ``MOTORS`` order. ``motor``, ``position`` and ``frame_bytes``
describe the ledger's own expected frame, and ``recorded`` is the attempt
record closed at that position — ``None`` when the batch closed none,
which leaves the expected frame unmatched. ``frame_mismatch``,
``count_mismatch`` and ``status_mismatch`` say which of the three checks
failed, so the driver can record the problem without re-comparing. An
unexpected extra attempt is reported the same way, with the expected
side set to ``None``."""

VerificationResult = namedtuple(
    "VerificationResult",
    (
        "point_id",
        "verified",
        "frames_match",
        "counts_match",
        "statuses_match",
        "mismatches",
    ),
)
"""The ledger's whole-point answer for one write-attempt batch.

``verified`` is true only when every submitted frame matched exactly
(T3.3 rule 5: the point may only be classified after that). The three
summary flags report the individual rules: ``frames_match`` is true only
when every expected frame has a recorded attempt with identical bytes,
``counts_match`` only when every recorded attempt returned exactly its
expected byte count and that count is the ledger frame's length, and
``statuses_match`` only when every comparison closed with status OK.
``mismatches`` holds one FrameMismatch per comparison index that failed
anything, in expected-frame order. A point may only be classified once
``verified`` is true.
"""

# ---------------------------------------------------------------------------
# The archived v0.3.5.1 command encoder (source of exact bytes)
# ---------------------------------------------------------------------------

ARCHIVE_DIR = Path(__file__).resolve().parents[3] / "ChatGPT-Archive"
"""Where the archived H3 baselines live (repo root / ChatGPT-Archive)."""

ARCHIVE_ENCODER_NAME = "h3_sweep_v05_archived_smc3_encoder"
"""The archived smc3.py is exec'd verbatim into a private module object.

The archived source opens with ``import serial`` (archived smc3.py line 14).
Loading it registers a stub ``serial`` module in ``sys.modules`` for the
duration of the exec only — no port exists and nothing is ever sent — and
restores whatever ``serial`` entry was there before (pyserial, or none).
"""

ARCHIVED_MOTORS = None  # the archived MOTORS tuple, bound by _load_archive()
ARCHIVE_MOTOR_ORDER = None
CENTER_POSITION = None


def _is_function(value):
    """Duck-test a function without pulling in the inspect module."""
    return callable(value) and hasattr(value, "__code__")


def _load_archive():
    """Exec the archived smc3.py verbatim; return its encoder primitives.

    The archived source is compiled and run unmodified. Two entries are in
    ``sys.modules`` only for the duration of the exec: ``serial`` (the
    archived top-level ``import serial``; a stub, since no port exists and
    frames are generated, never sent) and the archive module itself, which
    ``dataclasses`` needs to resolve ``MotorCommand``'s annotations. Both
    are removed or restored right after the exec.
    """
    src_path = ARCHIVE_DIR / "H3_v0.3.5.1_commandhub_diagnostic" / "smc3.py"
    source = src_path.read_text(encoding="utf-8")
    module = types.ModuleType(ARCHIVE_ENCODER_NAME)
    module.__file__ = str(src_path)
    previous_serial = sys.modules.get("serial")
    previous_archive = sys.modules.get(ARCHIVE_ENCODER_NAME)
    sys.modules["serial"] = types.SimpleNamespace()  # stub: satisfies `import serial`
    sys.modules[ARCHIVE_ENCODER_NAME] = module
    try:
        exec(source, module.__dict__)
    finally:
        if previous_serial is None:
            del sys.modules["serial"]
        else:
            sys.modules["serial"] = previous_serial
        if previous_archive is None:
            del sys.modules[ARCHIVE_ENCODER_NAME]
        else:
            sys.modules[ARCHIVE_ENCODER_NAME] = previous_archive
    encode = module.__dict__.get("encode_command")
    command = module.__dict__.get("MotorCommand")
    motors = module.__dict__.get("MOTORS")
    if not _is_function(encode) or command is None or motors is None:
        raise RuntimeError(
            "archived smc3.py lacks encode_command/MotorCommand/MOTORS"
        )
    return module


_ARCHIVED = _load_archive()
encode_command = _ARCHIVED.encode_command
MotorCommand = _ARCHIVED.MotorCommand
ARCHIVED_MOTORS = tuple(_ARCHIVED.MOTORS)
ARCHIVE_MOTOR_ORDER = ARCHIVED_MOTORS
CENTER_POSITION = _ARCHIVED.CENTER_POSITION
del _ARCHIVED  # the encoder functions keep the archive namespace alive


class LedgerError(Exception):
    """Raised when the ledger is asked about something it does not own."""


def _point_fields(point):
    """Coerce a SweepPoint or a plain mapping into (id, positions)."""
    if isinstance(point, SweepPoint):
        return point.point_id, dict(point.motor_positions)
    if isinstance(point, dict):
        return point.get("point_id"), dict(point.get("motor_positions", {}))
    raise LedgerError(f"unsupported sweep-point form: {point!r}")


def _clamp_position(motor, value):
    """Clamp through the archived MotorCommand (never ledger math)."""
    return MotorCommand(motor, value).position


def expected_frames(point):
    """The exact expected frames for one sweep point, in archived order.

    Every frame comes from the archived encoder (``MotorCommand``
    validates and clamps, ``encode_command`` builds the bytes), and the
    order is exactly the archived ``MOTORS`` order.
    """
    _, positions = _point_fields(point)
    missing = [m for m in ARCHIVE_MOTOR_ORDER if m not in positions]
    unknown = [m for m in positions if m not in ARCHIVE_MOTOR_ORDER]
    if missing or unknown:
        raise LedgerError(
            f"sweep point motors {sorted(positions)!r} must cover exactly "
            f"the archived motors {list(ARCHIVE_MOTOR_ORDER)!r} "
            f"(missing={missing}, unknown={unknown})"
        )
    frames = []
    for motor in ARCHIVE_MOTOR_ORDER:
        position = _clamp_position(motor, positions[motor])
        frame = encode_command(motor, position)
        frames.append(
            ExpectedFrame(
                motor=motor,
                position=position,
                frame_bytes=memoryview(bytes(frame)),
            )
        )
    return tuple(frames)


def _validate_attempt_batch(batch):
    """Check the shape of a batch before comparing it: an ordered sequence.

    The ledger refuses anything that cannot be a closed write-attempt
    batch: a mapping, a bare record, or a sequence whose entries are not
    complete attempt records, and a sequence whose ``attempt_seq`` values
    do not strictly increase (that field is the journal order the Barrier
    hands back, and comparison is positional, so an unordered batch
    cannot be interpreted).
    """
    if isinstance(batch, (list, tuple)):
        previous_seq = None
        for position, record in enumerate(batch):
            if not isinstance(record, dict):
                raise LedgerError(
                    f"batch entry {position} is not an attempt record: {record!r}"
                )
            missing = REQUIRED_RECORD_FIELDS - set(record)
            if missing:
                raise LedgerError(
                    f"batch entry {position} lacks attempt-schema fields: "
                    f"{sorted(missing)}"
                )
            seq = record["attempt_seq"]
            if not isinstance(seq, int) or isinstance(seq, bool):
                raise LedgerError(
                    f"batch entry {position} attempt_seq must be an integer: {seq!r}"
                )
            if previous_seq is not None and seq <= previous_seq:
                raise LedgerError(
                    f"attempt_seq values must strictly increase: {seq!r} at batch "
                    f"entry {position}"
                )
            previous_seq = seq
        return
    raise LedgerError(
        f"expected a sequence of closed attempt records, got {type(batch).__name__}"
    )


class Ledger:
    """Driver-owned ledger mapping sweep points to their expected frames.

    ``register_point`` generates the point's frames through the archived
    encoder and records them under the point id. Expected frames are
    looked up by point id; the ledger never mutates what the driver asked
    it to register. ``verify`` compares one closed write-attempt batch
    against those frames and reports whether the point can be classified.
    """

    def __init__(self):
        self._points = {}      # point_id -> registered SweepPoint
        self._expected = {}    # point_id -> tuple of ExpectedFrame

    def register_point(self, point):
        """Record one sweep point and return its generated frames."""
        point_id, _positions = _point_fields(point)
        frames = expected_frames(point)
        if point_id in self._points:
            raise LedgerError(f"duplicate point id: {point_id!r}")
        self._points[point_id] = point
        self._expected[point_id] = frames
        return frames

    def expected_frames(self, point_id):
        """The point's expected frames, or None when unregistered."""
        return self._expected.get(point_id)

    def frames_for(self, point_id):
        """Alias of expected_frames used by association code (T3.5+)."""
        return self.expected_frames(point_id)

    def verify(self, point_id, batch):
        """Compare a closed write-attempt batch with the point's frames.

        Steps 5-7 of Implementation.md section 6 ("Per-point execution")
        and the section 7 ledger rule "Verify that actual recorded bytes
        match expected bytes": compare the recorded frames against the
        expected ledger, verify the returned byte counts, and verify the
        statuses. The point is verified only when every submitted frame
        matched exactly, which is what allows step 8 ("Record the point
        result") and step 9 ("Only then proceed to the next point").

        ``batch`` is the three attempts the Barrier closed for this point,
        in journal order (ordered by ``attempt_seq``). Comparison is
        positional, so expected frame *i* (archived ``MOTORS`` order: A,
        B, C) is compared with batch entry *i*:

        - the recorded ``frame_bytes`` must equal the expected frame's
          bytes exactly;
        - ``expected_count`` must equal the expected frame's length, and
          ``returned_count`` must equal ``expected_count`` (so a SHORT
          record, whose returned count is lower, never matches);
        - ``status`` must be OK (the recorder uses ERROR when the write
          raised, in which case there is no returned count at all).

        A batch shorter than the point's frames leaves those expected
        frames unmatched (``recorded`` is None); a longer batch reports
        the extra attempts as unexpected (expected side None). Mismatches
        never raise — a frame mismatch is a reportable software error,
        and the sweep records it — but an unregistered point or a
        malformed batch raises LedgerError. Neither the ledger nor the
        batch is mutated.
        """
        expected = self._expected.get(point_id)
        if expected is None:
            raise LedgerError(f"point {point_id!r} is not registered in the ledger")
        _validate_attempt_batch(batch)

        mismatches = []
        frames_match = counts_match = statuses_match = True
        n_expected = len(expected)
        n_recorded = len(batch)
        for index in range(max(n_expected, n_recorded)):
            want = expected[index] if index < n_expected else None
            got = batch[index] if index < n_recorded else None
            if want is not None and got is None:
                # nothing was closed for this expected frame: no bytes,
                # no count agreement, no status
                frame_mismatch = count_mismatch = status_mismatch = True
            elif want is None and got is not None:
                # an attempt the ledger never expected for this point
                frame_mismatch = True
                count_mismatch = status_mismatch = False
            else:
                frame_mismatch = bytes(want.frame_bytes) != bytes(got["frame_bytes"])
                count_mismatch = (
                    got["expected_count"] != len(want.frame_bytes)
                    or got["returned_count"] != got["expected_count"]
                )
                # the canonical OK word is ``recorder.ATTEMPT_STATUS_OK``
                # (recorder.py line 230); the ledger keeps modules
                # independent (T1.4) and the recorder guard forbids binding
                # it here, so the word is spelled out at the comparison
                status_mismatch = got["status"] != "OK"
            if not (frame_mismatch or count_mismatch or status_mismatch):
                continue
            if frame_mismatch:
                frames_match = False
            if count_mismatch:
                counts_match = False
            if status_mismatch:
                statuses_match = False
            mismatches.append(
                FrameMismatch(
                    index=index,
                    motor=None if want is None else want.motor,
                    position=None if want is None else want.position,
                    frame_bytes=None if want is None else bytes(want.frame_bytes),
                    recorded=got,
                    frame_mismatch=frame_mismatch,
                    count_mismatch=count_mismatch,
                    status_mismatch=status_mismatch,
                )
            )

        return VerificationResult(
            point_id=point_id,
            verified=not mismatches,
            frames_match=frames_match,
            counts_match=counts_match,
            statuses_match=statuses_match,
            mismatches=tuple(mismatches),
        )

    def known_points(self):
        """The registered sweep points, in point-id order."""
        return tuple(self._points[key] for key in sorted(self._points))


__all__ = [
    "ARCHIVE_DIR",
    "ARCHIVE_MOTOR_ORDER",
    "ARCHIVED_MOTORS",
    "CENTER_POSITION",
    "ExpectedFrame",
    "LedgerError",
    "SweepPoint",
    "expected_frames",
    "Ledger",
    "REQUIRED_RECORD_FIELDS",
    "FrameMismatch",
    "VerificationResult",
    "ARCHIVE_ENCODER_NAME",
    "encode_command",
    "MotorCommand",
]
