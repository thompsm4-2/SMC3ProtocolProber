"""Serial write recorder and attempt synchronization for the v0.5 driver.

Responsibility (Implementation.md sections 5-6, tasks T1.2/T2.x/T3.1):
serial proxy, write-attempt records, attempt synchronization, and
write status classification.

Injection point established by the archived smc3.py: it calls
serial.Serial(...) through its imported module attribute, so the
recorder installs a shim module at smc3.serial before the CommandHub
starts. The shim's Serial class delegates to the real pyserial
implementation while recording every write attempt. The shim must
preserve serial construction, port opening, baud configuration,
read/write timeouts, the existing two-second Arduino reset delay,
writes, and closing. The recorder is scoped to one run; the original
smc3.serial module reference is restored only after the worker can
no longer use the recorded serial. This module-level injection is
not thread-safe for concurrent independent runs.

Required attempt record fields (one record per write attempt):
attempt_seq, timestamp, monotonic_timestamp, frame_bytes,
returned_count, expected_count, status, exception, is_motor_frame.
Sequence numbers are monotonically increasing; monotonic time is used
for ordering and elapsed-time measurements. The recorder must be
thread-safe.

Attempt status vocabulary: OK (returned exactly the expected byte
count), SHORT (returned fewer), ERROR (write raised an exception; the
original exception is preserved and re-raised so the archived CommandHub
sees the same failure). Expected SMC3 frame length is five bytes.

Motor frame detection (Implementation.md section 7, line 312):
Motor-position frames have the exact signature: five bytes, starting
with 0x5B and ending with 0x5D. Control frames (enable, disable,
version request) have different byte patterns and must not count
toward a point's three motor-position attempts but must remain in
the recorder journal for diagnostics.

The Barrier class below is the attempt-synchronization primitive of
Implementation.md section 6: its declared interface came from task T1.4
and its behavior is implemented here by task T3.1.

Barrier ownership note (T1.2): under the accepted responsibility
assignment, barrier-based point sequencing (the decision to wait
between points) is a driver.py responsibility, while this class is
the recorder's attempt-synchronization primitive. It is declared in
this module because its contract observes the recorder's closed
write-attempt records; the driver will call it as part of its
sequencing. This placement is the judgment call recorded in T1.1:
neither Implementation.md nor the T1.2 responsibility table assigns
the Barrier class to a specific module, so it remains the recorder's
synchronization primitive here, now carrying the task T3.1 behavior.

Task T2.1 (this change): implements the serial-module injection
shim. create_serial_shim(real_serial_module, recorder) builds a
module-like stand-in for the archived smc3.py's `import serial`
attribute; the shim copies every other attribute of the real serial
module and replaces only `Serial` with a delegating class, so
serial construction, port opening, baud configuration, read/write
timeouts, and closing pass through to the real pyserial
implementation unchanged (the archived two-second Arduino reset
delay lives in the archived SerialTransport.open() itself, outside
the shim, and is therefore never bypassed). recorder.install(smc3)
writes the shim to smc3.serial and must run before CommandHub
starts (the archived CommandHub worker resolves smc3.serial.Serial
lazily; installing mid-run would race the worker thread). Each
shim Serial.write() delegates to the real Serial.write() and then
records the raw attempt data (frame bytes, returned byte count,
monotonic sequence number, wall and monotonic timestamps) under a
lock, because the archived CommandHub worker calls write() from its
own thread.

Task T2.5 (this change): completes the full attempt-record schema.
Every record written by record_write_attempt now contains exactly
the required fields attempt_seq, timestamp,
monotonic_timestamp/frame_bytes/returned_count/expected_count/
status/exception: attempt_seq values are monotonically increasing
sequence numbers (assigned under the existing lock, so numbering is
stable across threads); wall-clock timestamp and monotonic_timestamp
are captured at the top of record_write_attempt immediately before
entering the lock, and monotonic time is what ordering and
elapsed-time measurements use because it is unaffected by system
clock adjustments. frame_bytes snapshots the payload as it was
before write(), and expected_count is derived from the payload
(Implementation.md section 13 requires populating expected from the
expected frame length; the ledger CSV schema's expected_count is
this same observation) — never from the write result, so the
attempt's expected byte count can be reconstructed even if
returned_count never arrives. returned_count remains the raw byte
count the underlying write() reported, kept distinct from the
known-before-write data. status and exception fields are present as
placeholders (None) so every record has the complete schema, but
they are not populated with meaning yet: the status vocabulary is
task T2.6, classifying an attempt by setting that status is task
T2.8, and the record-then-reraise exception policy that fills
exception is task T2.7 — this change adds no
try/except anywhere and invents no status vocabulary. The recorder
remains thread-safe: sequence assignment and record appending stay
inside the single non-nested lock, so concurrent shim writes
interleave only at whole-record granularity.

Still deferred to later tasks and NOT implemented here: everything from
phase 3 and later except task T3.1, whose Barrier implementation is now
provided below (the T2.8 completed-write status classification is
implemented in record_write_attempt).

Task T2.6 (this change): establishes the canonical serial write-attempt
status vocabulary. Implementation.md section 5.3 fixes exactly three
statuses, so recorder.py now owns one canonical module-level definition
of them: ATTEMPT_STATUS_OK ('OK' — write() returned exactly the
expected byte count), ATTEMPT_STATUS_SHORT ('SHORT' — write() returned
fewer bytes than expected), and ATTEMPT_STATUS_ERROR ('ERROR' — write()
raised an exception), collected in the ATTEMPT_STATUSES tuple. Plain
uppercase str values are used, not an enum, so the same words stay
byte-compatible with the TX CSV status column of Implementation.md
section 11 and with the v0.4.1 archived h3_characterize.py TX logs.
These names replace what would otherwise be bare 'OK'/'SHORT'/'ERROR'
literals scattered through the driver. No status word is defined
anywhere else in the v0.5 package, and no competing or additional
status word is invented: PARTIAL, FAILED, TIMEOUT and similar words do
not appear as attempt statuses (the unrelated SENSOR_RESPONSE_STATUSES
in driver.py classify sensor replies, not write attempts, and are not
touched). This change is only the agreed naming: it adds no
classification logic, so record_write_attempt still leaves the status
field None in every record, still adds no try/except, and still
propagates write exceptions to the caller; those behaviours remain T2.7
and T2.8. The schema, sequencing, timestamps, locking, thread-safety,
snapshots, shim and one-run lifecycle behaviour of T2.1-T2.5 are
unchanged.

Task T2.8 (this change): classifies COMPLETED write attempts from the
real write() return value inside record_write_attempt. The attempt's
status is ATTEMPT_STATUS_OK when write() returned exactly expected_count
and ATTEMPT_STATUS_SHORT for any other returned count, per Implementation.md
section 5.3; the returned count and the five-byte expected count stay
separate fields (task T2.3's rule that short counts survive unchanged is
untouched). Classification is one label on an already-recorded attempt:
it invents no retry, retransmission, recovery, exception handling,
synchronization or logging sink, and the shim still returns the real
write() count untouched. ERROR stays exclusive to record_exception_attempt
(task T2.7), whose record-then-reraise path is unchanged.

Task T2.7 (this change): implements the record-then-reraise exception
policy of Implementation.md section 5.3. When the underlying Serial.
write() raises, ShimSerial.write catches the exception at the shim
boundary (the single try/except in this module), calls
SerialRecorder.record_exception_attempt, and then bare-raises so the
archived CommandHub sees the exact same failure it would have seen
without the recorder: the original exception object propagates
untouched, nothing is swallowed, converted, or replaced, and no
exception is ever turned into a successful return. record_exception_
attempt appends exactly one record with the full T2.5 schema - same
lock, same monotonically increasing attempt_seq counter, same wall and
monotonic timestamps, same frame_bytes payload snapshot and payload-
derived expected_count - with returned_count None because the failed
write reported no byte count, status set to the canonical
ATTEMPT_STATUS_ERROR from the T2.6 vocabulary, and the exception
field holding the original exception object itself so its type and
arguments are preserved unchanged for later ledger/CSV presentation.
Sequence numbering is shared with completed writes, so a failed
attempt never renumbers or shifts the surrounding records and the
next completed write keeps taking the next sequence number.
Successful-write behaviour is untouched by the exception path: completed
records keep the schema, sequencing, timestamps and pass-through return
of task T2.5; the completed attempt's status is now classified OK or
SHORT by task T2.8 (see the T2.8 note below).
T2.1-T2.6 behaviour (schema, sequencing, timestamps, locking,
thread-safety, snapshots, shim pass-through, one-run lifecycle, and
the single canonical vocabulary) is unchanged.

Task T2.4 (this change): scopes the recorder to one run. A
SerialRecorder instance owns exactly one install/restore pairing:
install() refuses to stack a second shim on a recorder that
already owns one, and after restore() the recorder is closed, so
a new run must start a fresh SerialRecorder. restore() puts the
original serial module object back at each installed target
module's `serial` attribute (the archived smc3.py's `import
serial` injection point). It is a cleanup mechanism only: the
caller contract, from Implementation.md section 8 step 11 and
task T4.1, is to invoke it only after the CommandHub worker can
no longer use the recorded serial object; the archived worker
resolves smc3.serial.Serial at call time, so restoring earlier
would race a live write, and the recorder's own guard is that
restore() refuses to run without an installed shim, refuses a
second restore, and refuses to write the original back when the
target attribute no longer holds exactly this recorder's shim
(restoring then would clobber a foreign injection and could
interfere with an active run). Recorded attempt data is never
discarded by restore(): shutdown sequencing (T4.x) keeps classifying
post-close/shutdown-overlap attempts until no worker can access
the recorder. The module-level attribute injection limitation
remains documented and accepted: injection is process-global, one
install/restore pairing at a time, and is not thread-safe for
concurrent independent runs; runs must be sequential.

Task T3.1 (this change): implements the write-attempt completion barrier
of Implementation.md section 6. Barrier.recorder is a cursor into the
recorder's attempt journal: wait_for_attempts(expected, timeout) hands
over a batch only when the recorder has actually appended expected new
attempt records after the barrier was built, and a record exists only
once the host's Serial.write() call has returned or raised — so
synchronizing with the barrier synchronizes with the completion of real
serial write attempts, never with queue emptiness, buffer flushing, or
the serial object's pending-response state (the wait_for_idle/tx_count
patterns section 6.1 rejects are not consulted: the barrier holds no
serial object at all). Completion means a terminal status from the T2.6
vocabulary (OK, SHORT or ERROR), so a failed write attempt still counts
as completed while its classification stays intact: batches are journal
records in journal order, and a SHORT write remains distinguishable from
a complete one through the barrier (the section 6 required test). The
wait is bounded: it polls until the deadline derived from timeout and
raises TimeoutError — a plain raise, not a new status word or a
swallowed failure, and this module keeps its single try/except in the
shim write — when the attempts never complete; a timeout consumes
nothing, so a later wait still sees every completed attempt. More
completions than expected are all returned, never dropped, so T3.7 can
still see an unexpected extra attempt. The journal cursor advances only
on a successful handover, so each completed attempt is handed over
exactly once. No retry, no retransmission, no logging sink, no new
statuses, and T2.1-T2.8 behaviour (schema, sequencing, timestamps,
locking, thread-safety, snapshots, shim pass-through, one-run
lifecycle, vocabulary, classification, record-then-reraise) is
unchanged.
"""
from __future__ import annotations

import threading
import time
from types import ModuleType

# Canonical serial write-attempt status vocabulary (task T2.6).
# Implementation.md section 5.3 fixes exactly three statuses, and this
# single module-level definition is the only canonical home for them in
# the v0.5 package: the ledger and event log writers, the CSV writer,
# and any future analyzer must all read these same values. Plain
# uppercase str values (not an enum) keep the words byte-compatible
# with the TX CSV status column of Implementation.md section 11 and
# with the archived v0.4.1 h3_characterize.py TX logs.
ATTEMPT_STATUS_OK = "OK"  # write() returned exactly the expected byte count
ATTEMPT_STATUS_SHORT = "SHORT"  # write() returned fewer bytes than expected
ATTEMPT_STATUS_ERROR = "ERROR"  # write() raised an exception
ATTEMPT_STATUSES = (
    ATTEMPT_STATUS_OK,
    ATTEMPT_STATUS_SHORT,
    ATTEMPT_STATUS_ERROR,
)

# Element alias for the Barrier.wait_for_attempts contract (task T1.4
# declared `-> AttemptBatch`; the annotation stays that name under
# `from __future__ import annotations`). A batch is a list of the
# recorder's journal records — the closed eight-field attempt dicts of
# task T2.5, in journal order, never copies and never re-derivations.
AttemptBatch = list[dict]  # completed write-attempt records

# Motor frame signature (Implementation.md section 7, line 312):
# Motor-position frames are exactly five bytes, starting with 0x5B
# and ending with 0x5D. Control frames have different patterns.
MOTOR_FRAME_SIGNATURE = (0x5B, 0x5D)  # (first_byte, last_byte)


def _is_motor_frame(frame_bytes: bytes) -> bool:
    """Detect if frame_bytes is a motor-position frame.

    Motor frames have exactly 5 bytes, start with 0x5B, end with 0x5D,
    and have a motor letter (A=0x41, B=0x42, C=0x43) as the second byte.
    Control frames (enable, disable, version request) may also be 5 bytes
    starting with 0x5B and ending with 0x5D, but their second byte is
    not a motor letter, so they return False.

    Motor frame signature (Implementation.md section 7, line 312):
    - 5 bytes total
    - Byte 0: 0x5B (opening bracket)
    - Byte 1: Motor letter (0x41='A', 0x42='B', 0x43='C')
    - Bytes 2-3: Position value (0-1023)
    - Byte 4: 0x5D (closing bracket)
    """
    if len(frame_bytes) != 5:
        return False
    if frame_bytes[0] != 0x5B or frame_bytes[-1] != 0x5D:
        return False
    # Motor letters are A (0x41), B (0x42), C (0x43)
    motor_letters = (0x41, 0x42, 0x43)
    if frame_bytes[1] not in motor_letters:
        return False
    return True


class SerialRecorder:
    """Write-attempt recorder behind the injected serial shim (task T2.1).

    Scope: one install/shim pairing (Implementation.md section 5).
    Module-level attribute injection is not thread-safe for
    concurrent independent runs; that limitation is documented and
    accepted. The attempt log itself is lock-guarded because the
    archived CommandHub worker calls write() from its own thread.

    Every record written by record_write_attempt contains exactly
    the required schema fields attempt_seq, timestamp,
    monotonic_timestamp, frame_bytes, returned_count,
    expected_count, status, and exception (task T2.5): attempt_seq
    is a monotonically increasing sequence number, monotonic
    timestamps give the ordering used for elapsed-time measurements,
    frame_bytes/expected_count are the known-before-write payload
    observation, and returned_count is the data the underlying write
    reported. A completed write's status is classified by task T2.8 from
    the returned count: ATTEMPT_STATUS_OK when write() returned exactly
    expected_count, ATTEMPT_STATUS_SHORT for any other returned count. Its
    exception stays None because a returned write has no exception.
    For a write that raised, the shim routes the failure to
    record_exception_attempt (task T2.7), which appends exactly one
    record with status ATTEMPT_STATUS_ERROR and the original
    exception object in the exception field before the shim re-raises
    it. Task T2.6 fixed the names of the three allowed status values
    at module level above this class.
    """

    SHIM_MARKER = "h3_sweep_v05_serial_shim"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: list[dict] = []
        self._next_seq = 0
        self._installed: list[tuple[object, object, object]] = []
        # (target module, original module object, shim module) triples
        # recorded so restore (task T2.4) can put smc3.serial back after
        # the worker can no longer use the recorded serial.
        self._run_closed = False  # set by restore: one run per instance

    def install(self, smc3_module) -> None:
        """Install the shim over smc3_module.serial; keep the original.

        Must be called before CommandHub starts: the archived worker
        thread resolves the module attribute at call time, so
        installing mid-run would race a live write.
        """
        if self._run_closed:
            raise RuntimeError(
                "this recorder was already restored during cleanup and"
                " is scoped to one run; start a new SerialRecorder for a"
                " new run"
            )
        if self._installed:
            raise RuntimeError(
                "a recorder instance is scoped to one install/restore"
                " pairing (one run); it already owns an installed shim"
            )
        original = getattr(smc3_module, "serial", None)
        if original is None:
            raise ValueError(
                "target module has no 'serial' attribute to inject the"
                " shim at (expected the archived smc3.py module attribute)"
            )
        if getattr(original, self._marker_key(), False):
            raise RuntimeError("shim already installed at this module")
        shim = create_serial_shim(original, self)
        smc3_module.serial = shim
        self._installed.append((smc3_module, original, shim))

    def _marker_key(self) -> str:
        return self.SHIM_MARKER

    def restore(self, smc3_module=None) -> None:
        """Restore the original serial module object(s) (task T2.4).

        Run-scoped cleanup from Implementation.md section 5 and
        section 8 step 11 ("restore the original smc3.serial
        reference only when doing so cannot interfere with an
        active run"). The caller contract: invoke this only after
        the CommandHub worker can no longer use the recorded
        serial object (transport closed, lingering worker past
        reachability); sequencing that moment belongs to the
        driver shutdown procedure (task T4.1), and the archived
        worker resolving smc3.serial.Serial at call time is why
        restoring mid-run would race a live write.

        Guards: a restore with nothing installed is a bug and
        raises; so is a second restore after the first consumed
        the install; and if the target module's `serial` attribute
        no longer holds exactly this recorder's shim, a foreign
        injection owns that attribute, so restoring now could
        interfere with an active run and this method refuses to
        clobber it. After a successful restore the install entry
        is consumed and this recorder is closed: one recorder
        instance covers exactly one run.

        Recorded attempt data is never cleared here: shutdown
        tasks (T4.x) keep post-close/shutdown-overlap attempts
        classifiable until no worker can access the recorder.
        """
        targets = [
            entry
            for entry in self._installed
            if smc3_module is None or entry[0] is smc3_module
        ]
        if not targets:
            raise ValueError(
                "no installed shim on this recorder to restore"
                + (" at the requested module" if smc3_module is not None else "")
            )
        for module, original, shim in targets:
            current = getattr(module, "serial", None)
            if current is not shim:
                raise RuntimeError(
                    "target module's serial attribute no longer holds"
                    " this recorder's shim; restoring the original now"
                    " would clobber a foreign injection and could"
                    " interfere with an active run"
                )
            module.serial = original
            self._installed.remove((module, original, shim))
        self._run_closed = True

    def record_write_attempt(self, data: bytes, returned_count) -> None:
        """Append one attempt record with the full T2.5 schema plus
        is_motor_frame (lock-guarded).

        Called by the shim after the real Serial.write() returned;
        exceptions raised by the real write never reach here — the
        shim routes them to record_exception_attempt instead (task
        T2.7), which records the failed attempt and re-raises.

        Data known before write(): frame_bytes (the payload snapshot)
        and expected_count (derived from the payload, never from the
        write result, so the attempt's expected byte count survives
        even if returned_count never arrives). returned_count is the
        separate observation reported by the underlying write.
        exception stays None: only record_exception_attempt (task T2.7)
        ever populates that field, because a write that raised is routed
        there by the shim. status is classified here by task T2.8 from the
        returned count: ATTEMPT_STATUS_OK when write() returned exactly
        expected_count, ATTEMPT_STATUS_SHORT for any other returned count.
        Classification invents no retry, recovery, retransmission or
        logging sink - it only labels the attempt that was already made.
        attempt_seq is a monotonically increasing sequence number and
        the monotonic_timestamp taken here orders records for
        elapsed-time measurements; both are assigned under the lock.
        is_motor_frame is set by detecting the motor-position frame
        signature: exactly five bytes, starting with 0x5B and ending
        with 0x5D (Implementation.md section 7, line 312).
        """
        frame_bytes = bytes(data)  # payload snapshot taken before the write
        expected_count = len(frame_bytes)
        # Task T2.8: classify the completed attempt from the real return
        # value. OK means returned exactly expected_count; any other returned
        # count is SHORT (T2.3 pinned that short counts survive unchanged).
        # ERROR stays reserved for record_exception_attempt (task T2.7): a
        # write that raised never reaches this helper.
        status = ATTEMPT_STATUS_OK if returned_count == expected_count else ATTEMPT_STATUS_SHORT
        is_motor = _is_motor_frame(frame_bytes)
        with self._lock:
            timestamp = time.time()
            monotonic_timestamp = time.monotonic()
            self._next_seq += 1
            self._attempts.append(
                {
                    "attempt_seq": self._next_seq,
                    "timestamp": timestamp,
                    "monotonic_timestamp": monotonic_timestamp,
                    "frame_bytes": frame_bytes,
                    "returned_count": returned_count,
                    "expected_count": expected_count,
                    "status": status,
                    "exception": None,
                    "is_motor_frame": is_motor,
                }
            )

    def record_exception_attempt(self, data, exception) -> None:
        """Append one ERROR attempt record (record-then-reraise, task T2.7).

        Called by the shim's write when the real Serial.write() raised:
        Implementation.md section 5.3 fixes the policy - record the
        attempt as ERROR, preserve the exception information, then let
        the shim re-raise the original exception so the archived
        CommandHub sees the same failure it would have seen without
        the recorder. Nothing here catches or converts anything: this
        method only appends the record, and the exception object it
        receives is stored unchanged in the exception field (type,
        arguments, and traceback preserved for later presentation).

        The record carries exactly the T2.5 schema and shares the
        lock and the attempt_seq counter with completed writes, so a
        failed attempt interleaves at whole-record granularity without
        renumbering any surrounding record. returned_count is None
        because the failed write reported no byte count; frame_bytes
        and expected_count keep the payload observation taken before
        the write, so the attempted frame survives the failure.
        is_motor_frame is set by detecting the motor-position frame
        signature (Implementation.md section 7, line 312).
        """
        frame_bytes = bytes(data)
        expected_count = len(frame_bytes)
        is_motor = _is_motor_frame(frame_bytes)
        with self._lock:
            timestamp = time.time()
            monotonic_timestamp = time.monotonic()
            self._next_seq += 1
            self._attempts.append(
                {
                    "attempt_seq": self._next_seq,
                    "timestamp": timestamp,
                    "monotonic_timestamp": monotonic_timestamp,
                    "frame_bytes": frame_bytes,
                    "returned_count": None,
                    "expected_count": expected_count,
                    "status": ATTEMPT_STATUS_ERROR,
                    "exception": exception,
                    "is_motor_frame": is_motor,
                }
            )

    def attempts(self) -> list[dict]:
        """Snapshot of the recorded attempts (monotonic by sequence)."""
        with self._lock:
            return list(self._attempts)

    def _original_module(self, smc3_module):
        """Original module reference saved by install (restore consumes it)."""
        for module, original, _shim in self._installed:
            if module is smc3_module:
                return original
        return None


def create_serial_shim(real_serial_module, recorder):
    """Build the module-like shim installed at smc3.serial (task T2.1).

    The shim mirrors every other attribute of the real serial module
    (so SerialException and any future attribute keep the real
    behavior) and replaces only `Serial` with a class that
    delegates construction, writes and closing to the real
    pyserial Serial while recording each write attempt - completed
    or failed (task T2.7) - through `recorder`.
    """
    if not hasattr(real_serial_module, "Serial"):
        raise ValueError(
            "the real serial module being shimmed must expose Serial"
        )
    real_serial_cls = real_serial_module.Serial

    class ShimSerial:
        """pyserial.Serial stand-in that delegates and records (T2.1)."""

        def __init__(self, *args, **kwargs):
            self._delegate = real_serial_cls(*args, **kwargs)

        def write(self, data):
            # T2.7 record-then-reraise: when the real write raises,
            # record the attempt as ERROR first, then bare-raise so
            # the archived CommandHub sees the exact same exception
            # object it would have seen without the recorder (the
            # failure is never swallowed, replaced, or converted
            # into a successful return). Successful-write behaviour
            # below is the untouched T2.1/T2.5 path.
            try:
                returned = self._delegate.write(data)
            except Exception as exc:
                recorder.record_exception_attempt(data, exc)
                raise
            recorder.record_write_attempt(data, returned)
            return returned

        def __getattr__(self, name):
            # Everything else (close, read, in_waiting, fileno,
            # closed, ...) delegates to the real Serial instance.
            return getattr(self._delegate, name)

    shim = ModuleType(f"{real_serial_module.__name__}__h3_sweep_shim")
    for name in dir(real_serial_module):
        if name != "Serial":
            setattr(shim, name, getattr(real_serial_module, name))
    shim.Serial = ShimSerial
    setattr(shim, SerialRecorder.SHIM_MARKER, True)
    return shim


class Barrier:
    """Write-attempt completion barrier (task T3.1).

    A cursor into the recorder's attempt journal. wait_for_attempts
    hands over a batch only when the recorder has appended `expected`
    new attempt records after this barrier was built, and a record
    exists only once the host's Serial.write() call has returned or
    raised — so synchronizing with the barrier synchronizes with the
    completion of actual serial write attempts, never with queue
    emptiness, buffer flushing, or the serial object's pending-response
    state (the wait_for_idle()/tx_count patterns of Implementation.md
    section 6.1 are not consulted: the barrier holds no serial object
    at all, only the recorder).

    Completion means a terminal status from the T2.6 vocabulary (OK,
    SHORT or ERROR), so a failed write attempt still satisfies the
    wait while its classification stays intact: the batch is the
    journal's own records in journal order, and a SHORT write remains
    distinguishable from a complete one through the barrier
    (Implementation.md section 6's required distinction).

    The wait is bounded: it polls the journal until the deadline
    derived from `timeout` and raises TimeoutError when the attempts
    never complete (Implementation.md section 6's terminal-state
    timeout; the driver's point-level FAILED handling is task T3.7 and
    is not done here). The raise consumes nothing: the cursor advances
    only on a successful handover, so a later wait still sees every
    completed attempt, and each attempt is handed over exactly once.
    If more attempts completed than expected, all of them are
    returned — surplus completions stay visible so T3.7 can tell an
    unexpected motor or missing frame apart.
    """

    POLL_INTERVAL_SECONDS = 0.002  # journal re-check cadence

    def __init__(self, recorder):
        self.recorder = recorder
        self._cursor = max(
            (attempt["attempt_seq"] for attempt in recorder.attempts()),
            default=0,
        )

    def _completed_attempts(self) -> list:
        """Terminal attempts the cursor has not handed over yet."""
        return [
            attempt
            for attempt in self.recorder.attempts()
            if attempt["attempt_seq"] > self._cursor
            and attempt["status"] in ATTEMPT_STATUSES
        ]

    def _motor_attempts(self, attempts: list) -> list:
        """Filter attempts to only motor-position frames.

        Implementation.md section 7, line 312: Control frames must not
        count toward a point's three motor-position frames. This method
        returns only attempts where is_motor_frame is True.
        """
        return [
            attempt
            for attempt in attempts
            if attempt.get("is_motor_frame", False)
        ]

    def wait_for_attempts(
        self,
        expected: int,
        timeout: float,
    ) -> AttemptBatch:
        """Block until `expected` new motor-position write attempts have
        completed.

        Returns the journal records of every completed attempt since the
        last handover (at least `expected` motor frames of them, surplus
        included), or raises TimeoutError after the bounded `timeout` if
        they never do. The wait observes the journal only: no queue
        emptiness, flush, or pending-response counter stands in for
        completion.

        Control frames are NOT counted toward `expected` but ARE returned
        in the batch so they remain in the recorder journal for diagnostics
        (Implementation.md section 7, line 312).
        """
        deadline = time.monotonic() + timeout
        while True:
            completed = self._completed_attempts()
            motor_count = len(self._motor_attempts(completed))
            if motor_count >= expected:
                self._cursor = completed[-1]["attempt_seq"]
                return completed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Barrier.wait_for_attempts({expected}) timed out "
                    f"after {timeout}s: only "
                    f"{motor_count} of {expected} motor attempts "
                    "completed"
                )
            time.sleep(min(remaining, self.POLL_INTERVAL_SECONDS))
