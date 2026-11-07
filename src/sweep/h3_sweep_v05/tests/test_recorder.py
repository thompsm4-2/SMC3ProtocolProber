"""Software-only tests for the v0.5 recorder module (task T1.4 + T2.1).

The T1.4 tests assert the Phase 1 structural contract: the Barrier
stub interface from Implementation.md section 6. Since task T3.1 the
wait behavior is implemented, and this file now exercises it; only its
declared interface (constructor call, parameters, and AttemptBatch
annotation) remains pinned here.

The T2.1 tests added here exercise the serial-module injection shim:
installation at a host module's `serial` attribute (the archived
smc3.py's `import serial` point), delegation to a fake serial
implementation, and recording of every completed write attempt. The
fake implementation is the archived ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/tests/serial.py
echo stub, loaded unmodified in place. A synthetic host module
mirrors the archived smc3.py call shapes (serial.Serial(port, baud,
timeout=0.5, write_timeout=0.5) at line 90; ser.write(data) at line
99; ser.close() at line 106) without the archived two-second Arduino
reset sleep so the tests stay fast and deterministic.

The T2.2 tests added here verify the shim's preservation contract from
Implementation.md section 5 (tasks T2.1/T2.2): serial construction, port
opening, baud configuration, read/write timeouts, the two-second Arduino
reset delay (instrumented on the archived smc3.py module attribute so it
is shown to run — not bypassed by the shim — without actually sleeping),
writes, and closing, exercised through the real archived smc3.py module
object (loaded verbatim, read-only) and the synthetic host.

The T2.3 tests added here prove the prohibition contract from
Implementation.md section 5 (task T2.3): the recorder never modifies
private SerialTransport._serial attributes, never opens a second serial
connection, and never bypasses the archived transport's write lock or
lifecycle. The recorder module's own source is AST-walked to show the
transport internals are never named, and behavioral probes run through
the archived smc3.py SerialTransport (loaded verbatim, read-only) with
the archived fake serial stub: a serial-less install, exactly one stub
Serial per transport.open(), the archived double-open guard, the
archived "not open" lifecycle guards before and after close, and a
held-lock instrument (same module-attribute technique T2.2 used for the
archived time module) showing the shimmed write ran inside the
transport's with-self._write_lock block while the recorder recorded the
attempt.

The T2.4 tests added here exercise the run-scoped restoration
contract from Implementation.md section 5 ("the recorder must be
scoped to one run. Restore the original smc3.serial module
reference during cleanup, after the worker can no longer use the
recorded serial object"): SerialRecorder.restore() puts the
original serial module object back at the injection point, one
recorder instance owns exactly one install/restore pairing (one
run, enforced), restore refuses to run without an installed
shim, refuses a second restore, and refuses to clobber a
foreign injection, restore never discards recorded attempt
data, and a fresh recorder can inject again only after the
previous run's shim was restored. Which cleanup moment is safe
(after the worker can no longer use the recorded serial) is
driver shutdown sequencing (task T4.1); T2.4 provides the
mechanism, its guards, and the documented caller contract. The
module-level injection limitation (not thread-safe for
concurrent independent runs) is asserted as documented.

Task T2.8 (this change) classifies completed attempts: its OK/SHORT cases
live in AttemptClassificationTests below, and the completed-write status
pins in the tests above now expect ATTEMPT_STATUS_OK. The full attempt-record schema is
tested by this file (task T2.5); the T2.7 record-then-reraise
exception policy is tested by ExceptionRecordingTests below: a
failed write now appends exactly one ERROR record and re-raises
the original exception. Completed records now leave only
exception as a None placeholder, because a returned write has no exception,
while status is classified OK or SHORT by task T2.8;
the try/except lives only in the shim's write (task T2.7), never
inside SerialRecorder.

Task T3.1 (this change) implements the write-attempt completion Barrier
and tests it in AttemptBarrierTests below: the barrier blocks until a
write-attempt blocked inside a host's write() really completes (a worker
thread parked between the write call and its return, released while the
barrier is still waiting), times out within its bound when the attempt
never completes, returns records in journal order with the schema's
status classification intact (so SHORT and OK are distinguishable
through the barrier), isolates attempts recorded after its
construction, consumes each successful batch once, surfaces surplus
completed attempts instead of dropping them, and synchronizes on
completed write attempts only — never on queue emptiness, buffer
flushing, or the serial object's pending-response state.

Nothing here opens a serial port or touches hardware; no physical
device path is ever referenced.

Run directly:
    python src/sweep/h3_sweep_v05/tests/test_recorder.py
"""
import sys
import unittest
import ast
import inspect
import time
import threading
import importlib
import types
from pathlib import Path

_TIME = time  # stable alias: class bodies below shadow the name `time`

HERE = Path(__file__).resolve().parent              # .../h3_sweep_v05/tests
sys.path.insert(0, str(HERE.parent.parent))         # .../src/sweep holds h3_sweep_v05

from h3_sweep_v05 import recorder
from h3_sweep_v05.recorder import Barrier, SerialRecorder, create_serial_shim

ARCHIVE_HARNESS = (
    HERE.parents[3]
    / "ChatGPT-Archive"
    / "H3_v0.3.5.1_commandhub_diagnostic"
)
FAKE_SERIAL_PATH = ARCHIVE_HARNESS / "tests" / "serial.py"
ARCHIVED_SMC3_PATH = ARCHIVE_HARNESS / "smc3.py"

FAKE_SERIAL_NAME = "h3_sweep_v05_test_fake_serial"
HOST_NAME = "h3_sweep_v05_test_serial_host"
HOST_PORT = "software-only-test-port"
HOST_BAUD = 500_000
TEST_FRAME = bytes((0x5B, ord("C"), 0x00, 0x14, 0x5D))  # like the archived 5-byte SMC3 frames

RECORDER_PATH = HERE.parent / "recorder.py"      # the module under test
RECORDER_SOURCE = RECORDER_PATH.read_text(encoding="utf-8")
PACKAGE = HERE.parent                            # the h3_sweep_v05 package dir

# Task T2.6 helpers: the canonical status set restated here so the tests
# can show recorder.py defines these same three words and nothing else,
# and the sinks/paths the change must not have introduced.
STATUS_WORDS = ("OK", "SHORT", "ERROR")
DEVICE_PATH_PREFIXES = ("/dev/", "/dev/tty", "COM1")
PRESENTATION_WRITERS = frozenset(
    {
        "open",
        "print",
        "dump",
        "makedirs",
        "mkdir",
        "writerow",
        "writelines",
        "writeline",
        "write_text",
        "write_bytes",
    }
)


class TimeWithoutDelay:
    """Stand-in for smc3.py's `time` module in software-only tests.

    The archived two-second Arduino reset sleep inside SerialTransport.
    open() belongs to the archived transport, not to the shim; skipping
    it keeps the test fast and deterministic without touching anything
    else in the archived time module.
    """

    sleep = staticmethod(lambda seconds: None)
    time = staticmethod(lambda: _TIME.time())
    monotonic = staticmethod(lambda: _TIME.monotonic())


class DelayLoggingTime:
    """Stand-in for smc3.py's `time` module that records sleep calls.

    The archived two-second Arduino reset sleep inside SerialTransport.open()
    (archived smc3.py line 93) lives in the archived transport, outside the
    shim; T2.2 must show the shim never bypasses it. Instrumenting the sleep
    proves the delay still executes under an installed shim while keeping the
    suite fast and deterministic (nothing actually sleeps).
    """

    def __init__(self):
        self.slept: list[float] = []

    def sleep(self, seconds):
        self.slept.append(float(seconds))

    def time(self):
        return _TIME.time()

    def monotonic(self):
        return _TIME.monotonic()


class HeldLock:
    """Stand-in lock that reports whether it is currently held (task T2.3).

    The archived SerialTransport uses `threading.Lock()` and `with
    self._write_lock:` around `self._serial.write(data)` (archived smc3.py
    lines 85, 98-99). The shim must not bypass that lock. This test-only
    lock exposes a `held` flag so a probe serial can observe, at the
    moment the real serial write runs, whether the archived transport
    still held its write lock. It is a plain non-thread-shared double:
    single-threaded deterministic tests only.
    """

    def __init__(self):
        self.held = False

    def __enter__(self):
        self.held = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.held = False


class LockTrackingThreading:
    """Stand-in for the archived smc3 module's `threading` attribute (T2.3).

    SerialTransport.__init__ resolves `threading.Lock()` through that
    module attribute at call time (archived smc3.py line 85), so the
    tests can capture the exact lock object the archived transport then
    wraps its write in. Only `Lock` is exercised by these T2.3 tests;
    no CommandHub worker is started.
    """

    def __init__(self):
        self.locks: list[HeldLock] = []

    def Lock(self):
        lock = HeldLock()
        self.locks.append(lock)
        return lock


def make_lock_probe_serial_class(stub_serial_cls, watch_locks, observed):
    """Subclass of the archived fake Serial that snapshots lock state (T2.3).

    `write` records whether the archived transport's write lock was held
    at the moment the real (stub) serial write runs, then defers to the
    stub's own write, so writes and byte counts behave exactly as the
    archived fake stub does.
    """

    class LockProbeSerial(stub_serial_cls):
        def write(self, data):
            held = bool(watch_locks) and watch_locks[-1].held
            observed.append((held, len(bytes(data))))
            return stub_serial_cls.write(self, data)

    return LockProbeSerial


def load_archived_smc3():
    """Execute the archived smc3.py source verbatim with a fake `serial`.

    Read-only: the archived file is never modified or rewritten. The
    fake serial stub stands in for pyserial (`import serial` on line
    14) so the software-only suite never needs or imports pyserial.
    """
    mod = types.ModuleType("h3_sweep_v05_test_archived_smc3")
    code = compile(ARCHIVED_SMC3_PATH.read_text(encoding="utf-8"), str(ARCHIVED_SMC3_PATH), "exec")
    saved_serial = sys.modules.get("serial")
    # The module must be registered while its body executes so the archived
    # dataclass declarations resolve cls.__module__ (Python dataclasses look
    # it up in sys.modules).
    sys.modules[mod.__name__] = mod
    sys.modules["serial"] = load_fake_serial_module()
    try:
        exec(code, mod.__dict__)
    finally:
        sys.modules.pop(mod.__name__, None)
        if saved_serial is None:
            sys.modules.pop("serial", None)
        else:
            sys.modules["serial"] = saved_serial
    return mod


def load_fake_serial_module():
    """Load the archived tests/serial.py echo stub, unmodified, as a module."""
    mod = types.ModuleType(FAKE_SERIAL_NAME)
    code = compile(FAKE_SERIAL_PATH.read_text(encoding="utf-8"), str(FAKE_SERIAL_PATH), "exec")
    exec(code, mod.__dict__)
    return mod


def make_serial_host():
    """Host module mimicking the archived smc3.py serial call sites.

    Same module-attribute injection point (`host.serial`, resolved at
    call time exactly like smc3.py's `serial.Serial(...)` on line 90)
    and same call shapes for write (line 99) and close (line 106).
    No time.sleep here: the archived two-second reset delay lives in
    SerialTransport.open(), is unrelated to the shim, and is never
    exercised by software-only tests.
    """
    host = types.ModuleType(HOST_NAME)
    host.test_marker = "host"
    serial_mod = load_fake_serial_module()  # what `import serial` binds
    serial_mod.test_marker = "serial"
    host.serial = serial_mod

    def open_serial():
        return host.serial.Serial(HOST_PORT, HOST_BAUD, timeout=0.5, write_timeout=0.5)

    def write_serial(ser, data):
        return ser.write(data)

    def close_serial(ser):
        return ser.close()

    host.open_serial = open_serial
    host.write_serial = write_serial
    host.close_serial = close_serial
    return host


class RecorderTests(unittest.TestCase):
    def test_module_identity(self):
        self.assertEqual(recorder.__name__, "h3_sweep_v05.recorder")

    def test_barrier_declared(self):
        self.assertTrue(hasattr(Barrier, "wait_for_attempts"))

    def test_wait_for_attempts_signature(self):
        """Contract: wait_for_attempts(expected: int, timeout: float) -> AttemptBatch."""
        sig = inspect.signature(Barrier.wait_for_attempts)
        self.assertEqual([p for p in sig.parameters if p != "self"], ["expected", "timeout"])
        # recorder.py uses `from __future__ import annotations`, so
        # annotations are strings rather than evaluated objects.
        self.assertEqual(sig.parameters["expected"].annotation, "int")
        self.assertEqual(sig.parameters["timeout"].annotation, "float")
        self.assertEqual(str(sig.return_annotation).strip("'\""), "AttemptBatch")

    def test_barrier_no_longer_raises_the_t31_stub(self) -> None:
        """T3.1 replaced the stub: an empty journal times out, bounded."""
        with self.assertRaises(TimeoutError):
            Barrier(recorder.SerialRecorder()).wait_for_attempts(1, 0.05)

    def test_module_documents_contract(self):
        doc = recorder.__doc__ or ""
        self.assertIn("serial proxy", doc)
        self.assertIn("Barrier", doc)

    # -- task T2.1: serial-module injection shim ----------------------

    def test_install_replaces_module_serial_attribute(self):
        """Shim lands exactly at the host's `serial` module attribute."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        self.assertIsNot(host.serial, original)
        self.assertTrue(getattr(host.serial, SerialRecorder.SHIM_MARKER, False))
        # the host resolves through the new attribute at call time, like
        # archived smc3.py line 90 (serial.Serial(...), never cached)
        self.assertEqual(host.serial.test_marker, "serial")
        self.assertIsNot(host.serial.Serial, original.Serial)

    def test_install_keeps_original_reference_for_cleanup(self):
        """T2.1 installs only; the original is kept for T2.4 restoration."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        self.assertIs(rec._original_module(host), original)

    def test_install_requires_serial_attribute(self):
        """Injection point must exist; never invent it on an empty module."""
        host = types.ModuleType("h3_sweep_v05_test_no_serial_host")
        rec = SerialRecorder()
        with self.assertRaises(ValueError):
            rec.install(host)

    def test_double_install_rejected(self):
        """One injection per module attribute: installing twice is a bug."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        with self.assertRaises(RuntimeError):
            rec.install(host)

    def test_shim_preserves_other_module_attributes(self):
        """SerialException etc. stay the real ones; only Serial is swapped."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        self.assertIs(host.serial.SerialException, original.SerialException)

    def test_shim_serial_construction_delegates(self):
        """Construction arguments pass through to the real Serial untouched:
        port opening, baud configuration, read timeout, write timeout."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()  # host.serial.Serial(...) under the shim
        self.assertEqual(len(fake.Serial.instances), 1)
        built = fake.Serial.instances[0]
        self.assertEqual(built.port, HOST_PORT)
        self.assertEqual(built.baudrate, HOST_BAUD)
        self.assertEqual(built.timeout, 0.5)
        self.assertEqual(built.write_timeout, 0.5)

    def test_write_delegates_returns_real_value(self):
        """write() returns the real pyserial return value unchanged."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        returned = host.write_serial(ser, TEST_FRAME)
        self.assertEqual(returned, len(TEST_FRAME))
        self.assertEqual(fake.Serial.instances[0].writes, [TEST_FRAME])

    def test_write_attempt_recorded(self):
        """Every completed write attempt produces one raw record."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 1)
        attempt = attempts[0]
        self.assertEqual(attempt["attempt_seq"], 1)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
        self.assertEqual(attempt["returned_count"], len(TEST_FRAME))
        for key in ("timestamp", "monotonic_timestamp"):
            self.assertIsInstance(attempt[key], float)
        # T2.5 updated this assertion: the full attempt-record schema
        # must now be present, with expected_count derived from the
        # payload; T2.6 gives the status words, T2.7 records failures as
        # ERROR, T2.8 classifies completed writes, and T3.3 adds
        # is_motor_frame to distinguish motor-position frames from
        # control frames.
        self.assertEqual(
            set(attempt),
            {
                "attempt_seq",
                "timestamp",
                "monotonic_timestamp",
                "frame_bytes",
                "returned_count",
                "expected_count",
                "status",
                "exception",
                "is_motor_frame",
            },
        )
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_OK)
        self.assertIsNone(attempt["exception"])
        # T3.3: motor frames are detected by signature (5 bytes, 0x5B start, 0x5D end)
        self.assertTrue(attempt["is_motor_frame"])

    def test_every_write_attempt_recorded_in_order(self):
        """Sequence numbers increase monotonically across writes."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        second = bytes((0x5B, ord("A"), 0x01, 0x00, 0x5D))
        host.write_serial(ser, TEST_FRAME)
        host.write_serial(ser, second)
        host.write_serial(ser, TEST_FRAME)
        attempts = rec.attempts()
        self.assertEqual([a["attempt_seq"] for a in attempts], [1, 2, 3])
        self.assertEqual([a["frame_bytes"] for a in attempts], [TEST_FRAME, second, TEST_FRAME])
        monotonic = [a["monotonic_timestamp"] for a in attempts]
        self.assertEqual(monotonic, sorted(monotonic))

    def test_write_exceptions_propagate_recorded_once(self):
        """T2.7 record-then-reraise: the real exception reaches the transport
        untouched, and the failed write appended exactly one ERROR record."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        raised = None
        try:
            host.write_serial(ser, TEST_FRAME)
            self.fail("the archived failure must propagate to the caller")
        except fake.SerialException as exc:
            raised = exc
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], recorder.ATTEMPT_STATUS_ERROR)
        self.assertIs(attempts[0]["exception"], raised)

    def test_close_delegates_through_shim(self):
        """Closing delegates to the real implementation via __getattr__."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        self.assertEqual(ser.close, fake.Serial.instances[0].close)
        host.close_serial(ser)
        self.assertTrue(fake.Serial.instances[0].closed)

    def test_installs_are_independent_per_host(self):
        """Each host/shim/recorder pairing records only its own attempts."""
        host_a = make_serial_host()
        host_b = make_serial_host()
        rec_a, rec_b = SerialRecorder(), SerialRecorder()
        rec_a.install(host_a)
        rec_b.install(host_b)
        ser_a = host_a.open_serial()
        ser_b = host_b.open_serial()
        host_a.write_serial(ser_a, TEST_FRAME)
        self.assertEqual(len(rec_a.attempts()), 1)
        self.assertEqual(rec_b.attempts(), [])
        host_b.write_serial(ser_b, TEST_FRAME)
        host_b.write_serial(ser_b, TEST_FRAME)
        self.assertEqual([a["attempt_seq"] for a in rec_a.attempts()], [1])
        self.assertEqual([a["attempt_seq"] for a in rec_b.attempts()], [1, 2])

    def test_recorder_records_are_thread_safe(self):
        """Lock-guarded log: concurrent recording never loses attempts."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        writers = 4
        per_writer = 8
        barrier = threading.Barrier(writers + 1)

        def record_repeated(writer_index):
            for _ in range(per_writer):
                rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
            barrier.wait()  # barrier joins the writers and the main thread

        threads = [
            threading.Thread(target=record_repeated, args=(i,))
            for i in range(writers)
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=10.0)  # deterministic: each thread waits for all
        for thread in threads:
            thread.join()
        attempts = rec.attempts()
        self.assertEqual(len(attempts), writers * per_writer)
        self.assertEqual(
            sorted(a["attempt_seq"] for a in attempts),
            list(range(1, writers * per_writer + 1)),
            "sequence numbers must be unique despite interleaving",
        )

    def test_shim_installed_on_archived_smc3_module(self):
        """Injection target test: the shim works on the archived module itself.

        The archived smc3.py is loaded verbatim into a private module object
        (read-only; the archive is never modified), with the archived tests'
        fake serial stub substituted for pyserial. The archived module's
        `time` attribute is swapped for a delay-free stand-in so the two-
        second Arduino-reset sleep inside the archived SerialTransport.open()
        — which is outside the shim — does not slow the suite.
        """
        smc3_mod = load_archived_smc3()
        rec = SerialRecorder()
        rec.install(smc3_mod)  # replaces smc3_mod.serial, the archived `import serial`
        smc3_mod.time = TimeWithoutDelay  # skip the archived 2 s reset sleep
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        shim_serial = transport._serial  # ShimSerial built by archived open()
        transport.write(TEST_FRAME)
        transport.close()
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["frame_bytes"], bytes(TEST_FRAME))
        self.assertEqual(attempts[0]["returned_count"], len(TEST_FRAME))
        # Shim introspection: delegation reached the real stub instance, and
        # the archived transport's write/close side effects survived it.
        stub_instance = shim_serial._delegate
        self.assertEqual(len(stub_instance.writes), 1)
        self.assertEqual(bytes(stub_instance.writes[0]), TEST_FRAME)
        self.assertTrue(stub_instance.closed)



class ShimBehaviorPreservationTests(unittest.TestCase):
    """Task T2.2: the shim preserves every serial behavior it wraps.

    One test per preservation item from Implementation.md section 5
    (serial construction, port opening, baud-rate configuration, read and
    write timeouts, the two-second Arduino reset delay, serial writes,
    serial closing). The archived smc3.py module object is the primary
    target since it is the real injection point; the synthetic host adds
    the non-default baud/timeout settings the archived call site does
    not exercise. Software-only: the archived fake serial stub stands in
    for pyserial and the archived reset sleep is recorded, not waited.
    """

    def install_on_archived(self, delay_logger):
        """Load the archived smc3.py verbatim and install the shim on it."""
        smc3_mod = load_archived_smc3()
        real_serial_mod = smc3_mod.serial  # the archived fake serial stub
        rec = SerialRecorder()
        rec.install(smc3_mod)
        # T2.4 owns restoring smc3_mod.serial; here we only instrument the
        # archived module's `time` attribute so the 2 s reset delay is
        # recorded instead of slept (that delay lives outside the shim).
        smc3_mod.time = delay_logger
        return smc3_mod, rec, real_serial_mod

    def test_t22_serial_construction_preserved(self):
        """Archived open() (line 90: serial.Serial(...)) resolves through the
        shim: the transport's serial object is the shim's Serial class and it
        delegates construction to the real implementation."""
        smc3_mod, _rec, _real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        shim_serial = transport._serial
        self.assertEqual(type(shim_serial).__name__, "ShimSerial")
        delegate = shim_serial._delegate
        self.assertEqual(type(delegate).__name__, "Serial")

    def test_t22_port_opening_preserved(self):
        """The port reaches the real implementation via the shim and exactly
        one connection is constructed for it (no second serial object)."""
        smc3_mod, _rec, real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        delegate = transport._serial._delegate
        self.assertEqual(delegate.port, HOST_PORT)
        self.assertEqual(len(real_mod.Serial.instances), 1)
        self.assertIs(delegate, real_mod.Serial.instances[0])

    def test_t22_baud_configuration_preserved(self):
        """The archived BAUD_RATE passes through untouched, and so does a
        non-default baud given directly to the shimmed Serial."""
        smc3_mod, _rec, _real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        delegate = transport._serial._delegate
        self.assertEqual(delegate.baudrate, smc3_mod.BAUD_RATE)
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        custom_baud = 1234
        host.serial.Serial(HOST_PORT, custom_baud)  # shim forwards args verbatim
        built = original.Serial.instances[-1]
        self.assertEqual(built.baudrate, custom_baud)

    def test_t22_read_and_write_timeouts_preserved(self):
        """timeout and write_timeout keyword args pass through the shim
        unchanged: the archived 0.5/0.5 pair and a distinct custom pair."""
        smc3_mod, _rec, _real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        delegate = transport._serial._delegate
        self.assertEqual(delegate.timeout, 0.5)
        self.assertEqual(delegate.write_timeout, 0.5)
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        host.serial.Serial(HOST_PORT, HOST_BAUD, timeout=0.25, write_timeout=0.75)
        built = original.Serial.instances[-1]
        self.assertEqual(built.timeout, 0.25)
        self.assertEqual(built.write_timeout, 0.75)

    def test_t22_two_second_arduino_reset_delay_preserved(self):
        """Archived open() still sleeps 2.0 s after constructing Serial
        (smc3.py line 93): the delay belongs to the archived transport, not
        the shim, and the shim never bypasses it (recorded here, not waited)."""
        delay = DelayLoggingTime()
        smc3_mod, _rec, _real_mod = self.install_on_archived(delay)
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        self.assertEqual(delay.slept, [2.0])

    def test_t22_writes_preserved(self):
        """write() forwards the bytes untouched and returns the real
        implementation's return value, while recording the attempt."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        returned = host.write_serial(ser, TEST_FRAME)
        built = original.Serial.instances[-1]
        self.assertEqual(built.writes, [TEST_FRAME])
        self.assertEqual(returned, len(built.writes[-1]))
        self.assertEqual(len(rec.attempts()), 1)

    def test_t22_closing_preserved_through_shim(self):
        """close() is not a shim method: it delegates via __getattr__ to the
        real Serial, whose closed state then takes effect."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        self.assertFalse(ser.closed)
        ser.close()
        built = original.Serial.instances[-1]
        self.assertTrue(built.closed)
        with self.assertRaises(original.SerialException):
            ser.write(TEST_FRAME)  # the real closed-port behavior survives

    def test_t22_closing_preserved_through_archived_transport(self):
        """Archived transport.close() (line 106) still clears and closes the
        serial object the shim created: the transport lifecycle is intact."""
        smc3_mod, _rec, _real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        delegate = transport._serial._delegate
        transport.close()
        self.assertTrue(delegate.closed)
        self.assertIsNone(transport._serial)  # archived close() clears its slot

class RecorderProhibitionTests(unittest.TestCase):
    """Task T2.3: prove the serial shim never dodges the archived transport.

    Prohibition contract (Implementation.md section 5): the recorder must not
    (1) modify private SerialTransport._serial attributes to dodge write
    failures, (2) open a second serial connection, or (3) bypass the archived
    transport's write lock or lifecycle guards. Static evidence is an AST scan
    of recorder.py source; behavioral evidence comes from the archived smc3.py
    SerialTransport loaded verbatim (read-only) with the archived fake serial
    stub.
    """

    def install_on_archived(self, time_replacement):
        """Load the archived smc3.py verbatim and install the shim on it."""
        smc3_mod = load_archived_smc3()
        real_serial_mod = smc3_mod.serial  # the archived fake serial stub
        rec = SerialRecorder()
        rec.install(smc3_mod)
        # The archived 2 s Arduino reset sleep lives in the archived open(),
        # outside the shim; instrument the archived module's `time` attribute
        # so tests stay fast (T2.2 already proves the delay is preserved).
        smc3_mod.time = time_replacement
        return smc3_mod, rec, real_serial_mod

    def test_t23_recorder_never_reopens_or_fakes_record_when_write_fails(self):
        """Task T2.3: the archived serial must stay open and owned by the
        transport: the recorder may not modify private SerialTransport._serial
        attributes to dodge write failures. When the connection dies, the
        write must raise the real implementation's exception, the failed
        write must appear in the attempt ledger as exactly one ERROR record
        (task T2.7), and the recorder must not reopen or replace the
        connection: the transport's serial slot keeps the same shim object,
        the same delegate stays there (still marked dead), and no new
        connection is constructed (prohibition 1 and, via the reopen check,
        prohibition 2)."""
        smc3_mod, rec, real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        shim_serial = transport._serial
        delegate = shim_serial._delegate
        self.assertIsInstance(delegate, real_mod.Serial)

        attempts_before = len(rec.attempts())
        connections_before = len(real_mod.Serial.instances)
        delegate.close()  # pretend the port connection died (test harness)
        with self.assertRaises(real_mod.SerialException):
            transport.write(TEST_FRAME)
        attempts = rec.attempts()
        self.assertEqual(len(attempts), attempts_before + 1)
        self.assertEqual(attempts[-1]["status"], recorder.ATTEMPT_STATUS_ERROR)
        self.assertEqual(len(real_mod.Serial.instances), connections_before)
        self.assertIs(transport._serial, shim_serial)
        self.assertIs(transport._serial._delegate, delegate)
        self.assertTrue(delegate.closed)

    def test_t23_recorder_source_never_names_transport_privates(self):
        """Task T2.3: static proof of prohibition 1 — recorder.py source
        never uses the archived transport's private identifiers `_serial`
        or `_write_lock` (no local names, no attribute gets/sets, no
        keyword arguments). Docstrings that merely describe the contract
        are constants, not executed code, and are intentionally not part
        of the scan. The transport's own attributes are only touched by
        tests, never by the recorder."""
        tree = ast.parse((HERE.parent / "recorder.py").read_text(encoding="utf-8"))
        forbidden = {"_serial", "_write_lock", "SerialTransport"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                offenders.append(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in forbidden:
                offenders.append(node.attr)
            elif isinstance(node, ast.keyword) and node.arg in forbidden:
                offenders.append(node.arg)
        self.assertEqual(offenders, [])

    def test_t23_recorder_source_never_subclasses_serial_or_constructs_it(self):
        """Task T2.3: static proof of prohibitions 1-2 — no class in
        recorder.py derives from a base class whose name mentions Serial
        (the shim's ShimSerial delegates instead), and recorder.py never
        calls a constructor named `Serial` or `....Serial(...)` directly
        (the shim binds the real class once per install and delegates to
        it; the archived transport's own serial.Serial call stays the only
        way a connection is built)."""
        tree = ast.parse((HERE.parent / "recorder.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                    if name:
                        self.assertNotIn("serial", name.lower())
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name:
                    self.assertNotEqual(name, "Serial")

    def test_t23_install_alone_constructs_no_serial_connection(self):
        """Prohibition 2 (static install path): installing the shim
        constructs no connection of its own — the archived fake stub's
        instance count stays zero until the transport itself opens."""
        smc3_mod, rec, real_mod = self.install_on_archived(TimeWithoutDelay())
        self.assertEqual(len(real_mod.Serial.instances), 0)

    def test_t23_exactly_one_serial_connection_per_transport_open(self):
        """Prohibition 2 (behavioral): the only connection ever built is
        the archived transport.open() asks for. Counting fake-stub
        constructions, the first open adds exactly one, which is the
        object behind the shim the transport stores; a repeat open hits
        the archived idempotency guard and adds none; the shim opens
        none of its own and never replaces the transport's serial slot."""
        smc3_mod, rec, real_mod = self.install_on_archived(TimeWithoutDelay())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        self.assertEqual(len(real_mod.Serial.instances), 0)
        transport.open()
        self.assertEqual(len(real_mod.Serial.instances), 1)
        connection = real_mod.Serial.instances[0]
        self.assertIs(transport._serial._delegate, connection)
        transport.open()  # archived guard: already open
        self.assertEqual(len(real_mod.Serial.instances), 1)
        self.assertIs(transport._serial._delegate, connection)
        self.assertEqual(len(rec.attempts()), 0)  # opening is not a write

    def test_t23_archived_not_open_guard_enforced_when_write_fails_without_open(self):
        """Prohibition 3 (lifecycle half): the recorder must not bypass the
        archived write() guard. Before open(), transport.write() still raises
        the archived RuntimeError("Serial transport is not open"), the
        recorder records no phantom attempt, and no connection was
        constructed to satisfy the failed write."""
        smc3_mod, rec, real_mod = self.install_on_archived(TimeWithoutDelay())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        with self.assertRaisesRegex(RuntimeError, "not open"):
            transport.write(TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 0)
        self.assertEqual(len(real_mod.Serial.instances), 0)

    def test_t23_recorded_writes_run_under_archived_write_lock(self):
        """Prohibition 3 (lock half): the shim installs at the module's
        `serial` attribute and must not wrap transport.write(), so the
        archived `with self._write_lock:` still surrounds the real write.
        A probe bound to the archived module's Serial slot runs inside
        that with-statement and snapshots the lock the transport is holding
        (captured via the archived module's `threading.Lock`), so bypassing
        the lock or the archived transport's own lock object would be
        detected. The identity of the transport's `_write_lock` attribute
        is checked unchanged while held."""
        real_mod = load_fake_serial_module()
        smc3_mod = load_archived_smc3()
        watch_locks: list[HeldLock] = []
        observed: list[tuple[bool, int]] = []
        threading_proxy = LockTrackingThreading()
        smc3_mod.threading = threading_proxy
        smc3_mod.time = TimeWithoutDelay()
        smc3_mod.serial.Serial = make_lock_probe_serial_class(
            real_mod.Serial, watch_locks, observed
        )
        rec = SerialRecorder()
        rec.install(smc3_mod)
        transport = smc3_mod.SerialTransport(HOST_PORT)
        self.assertEqual(len(threading_proxy.locks), 1)
        self.assertIs(transport._write_lock, threading_proxy.locks[0])
        # Hand the archived transport's own lock object to the probe: the
        # probe reads the last watched lock when the real write runs, so
        # it snapshots exactly the lock the transport is holding then.
        watch_locks.append(threading_proxy.locks[0])
        transport_lock = transport._write_lock
        transport.open()
        rec_before = len(rec.attempts())
        transport.write(TEST_FRAME)
        # the probe ran while the archived transport held its lock, and the
        # transport's lock identity did not change while it was held
        self.assertEqual(observed, [(True, len(TEST_FRAME))])
        self.assertIs(transport._write_lock, transport_lock)
        self.assertEqual(len(rec.attempts()), rec_before + 1)
        self.assertEqual(watch_locks[0].held, False)  # lock released after write

    def test_t23_archived_lifecycle_guards_enforced_after_close(self):
        """Prohibition 3 (lifecycle half): after the transport closes, its
        serial slot is cleared by the archived close() and further writes
        hit the archived "not open" guard — the recorder must not reopen or
        fake-record around it. No phantom attempt is recorded and no new
        connection is built."""
        smc3_mod, rec, real_mod = self.install_on_archived(TimeWithoutDelay())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        transport.write(TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)
        transport.close()
        self.assertIsNone(transport._serial)  # archived close() clears its slot
        self.assertEqual(len(real_mod.Serial.instances), 1)  # never reopened
        with self.assertRaisesRegex(RuntimeError, "not open"):
            transport.write(TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)  # guard blocked the write

    def test_t23_failed_write_raises_archived_exception_records_error_once(self):
        """Prohibition 1 companion: when the connection dies, the write
        raises the archived implementation's exception unchanged, records
        exactly one ERROR attempt (task T2.7 record-then-reraise), and the
        recorder never reopens or replaces the
        transport's serial slot (identity preserved)."""
        smc3_mod, rec, real_mod = self.install_on_archived(DelayLoggingTime())
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        shim_serial = transport._serial
        delegate = shim_serial._delegate
        self.assertIsInstance(delegate, real_mod.Serial)

        attempts_before = len(rec.attempts())
        connections_before = len(real_mod.Serial.instances)
        delegate.close()  # pretend the port connection died (test harness)
        with self.assertRaises(real_mod.SerialException):
            transport.write(TEST_FRAME)
        attempts = rec.attempts()
        self.assertEqual(len(attempts), attempts_before + 1)
        self.assertEqual(attempts[-1]["status"], recorder.ATTEMPT_STATUS_ERROR)
        self.assertEqual(len(real_mod.Serial.instances), connections_before)
        self.assertIs(transport._serial, shim_serial)
        self.assertIs(transport._serial._delegate, delegate)
        self.assertTrue(delegate.closed)


class RunScopedRestorationTests(unittest.TestCase):
    """Task T2.4: the recorder is scoped to one run via one install/restore
    pairing. restore() puts the original serial module object back at the
    injection point, refuses to run without an installed shim, refuses a
    second restore, and refuses to clobber a foreign injection; recorded
    attempt data is never discarded by restore; after restore the recorder
    is closed so a new run needs a fresh SerialRecorder; the module-level
    injection limitation (not thread-safe for concurrent independent runs)
    stays documented. The safe cleanup moment itself (restore only once the
    worker can no longer use the recorded serial) is driver shutdown
    sequencing (task T4.1); T2.4 provides the mechanism and guards."""

    def test_t24_restore_puts_original_serial_module_back(self):
        """restore(host) (targeted form) puts the exact original module
        object back at host.serial and the shim marker is gone."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        shim = host.serial
        self.assertTrue(getattr(shim, SerialRecorder.SHIM_MARKER, False))
        self.assertFalse(getattr(original, SerialRecorder.SHIM_MARKER, False))
        rec.restore(host)
        self.assertIs(host.serial, original)
        self.assertFalse(getattr(host.serial, SerialRecorder.SHIM_MARKER, False))
        self.assertEqual(host.serial.test_marker, "serial")

    def test_t24_restore_without_install_raises(self):
        """A restore with nothing installed is a bug: ValueError, and the
        recorder is not (falsely) closed by the refused call."""
        rec = SerialRecorder()
        with self.assertRaisesRegex(ValueError, "no installed shim"):
            rec.restore()
        self.assertFalse(rec._run_closed)

    def test_t24_second_restore_rejected(self):
        """The first restore consumes the install entry, so a second
        restore hits the nothing-installed guard; the restored attribute
        and the closed state are untouched by the refused call."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        rec.restore()
        self.assertIs(host.serial, original)
        with self.assertRaisesRegex(ValueError, "no installed shim"):
            rec.restore()
        self.assertTrue(rec._run_closed)

    def test_t24_install_after_restore_rejected(self):
        """One recorder instance covers one run: after restore the
        recorder is closed, so installing again raises and the second
        host module stays untouched."""
        host_a = make_serial_host()
        host_b = make_serial_host()
        rec = SerialRecorder()
        rec.install(host_a)
        rec.restore(host_a)
        with self.assertRaisesRegex(RuntimeError, "already restored"):
            rec.install(host_b)
        self.assertEqual(host_b.serial.test_marker, "serial")

    def test_t24_second_install_before_restore_rejected(self):
        """A recorder may not stack a second shim on a recorder that
        already owns an install: the pairing is one run per instance."""
        host_a = make_serial_host()
        host_b = make_serial_host()
        rec = SerialRecorder()
        rec.install(host_a)
        with self.assertRaisesRegex(RuntimeError, "already owns an installed shim"):
            rec.install(host_b)
        self.assertEqual(host_b.serial.test_marker, "serial")

    def test_t24_restore_refuses_to_clobber_foreign_injection(self):
        """If the target attribute no longer holds exactly this
        recorder's shim, a foreign injection owns it and restoring now
        could interfere with an active run, so restore refuses. After
        the refused call, the foreign shim still owns the attribute and
        this recorder is not closed; putting this recorder's shim back
        lets its own restore succeed."""
        host = make_serial_host()
        original = host.serial
        rec = SerialRecorder()
        rec.install(host)
        own_shim = host.serial
        other_rec = SerialRecorder()
        other_shim = create_serial_shim(original, other_rec)
        host.serial = other_shim  # simulate a foreign injection
        with self.assertRaisesRegex(RuntimeError, "foreign injection"):
            rec.restore()
        self.assertIs(host.serial, other_shim)  # foreign shim kept
        self.assertFalse(rec._run_closed)  # refused restore did not close
        host.serial = own_shim
        rec.restore()
        self.assertIs(host.serial, original)

    def test_t24_fresh_recorder_injects_after_previous_run_restored(self):
        """A new run starts with a fresh SerialRecorder: after the
        previous run's recorder installed and restored, a new recorder
        installs cleanly and records its run's write."""
        host = make_serial_host()
        original = host.serial
        first = SerialRecorder()
        first.install(host)
        first.restore()
        second = SerialRecorder()
        second.install(host)
        self.assertIsNot(host.serial, original)
        self.assertTrue(getattr(host.serial, SerialRecorder.SHIM_MARKER, False))
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        self.assertEqual(len(second.attempts()), 1)

    def test_t24_writes_after_restore_not_recorded(self):
        """After restore the shim is gone from the injection point, so
        the host's writes run on the original module and this recorder
        sees nothing new."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)
        rec.restore()
        ser_after = host.open_serial()
        host.write_serial(ser_after, TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)

    def test_t24_restore_never_discards_attempt_data(self):
        """Shutdown sequencing (T4.x) keeps post-close attempts
        classifiable: restore leaves the recorded ledger intact."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        before = rec.attempts()
        rec.restore()
        self.assertEqual(rec.attempts(), before)
        self.assertEqual(len(before), 1)

    def test_t24_archived_smc3_restore_round_trip(self):
        """Full contract on the real archived smc3.py module object
        (loaded verbatim, read-only): install, transport open/write/close
        through the shim, restore puts the archived fake serial stub
        back at smc3.serial marker-free, and a second transport run
        after restore is no longer recorded by the closed recorder."""
        smc3_mod = load_archived_smc3()
        original = smc3_mod.serial
        smc3_mod.time = TimeWithoutDelay()
        rec = SerialRecorder()
        rec.install(smc3_mod)
        transport = smc3_mod.SerialTransport(HOST_PORT)
        transport.open()
        transport.write(TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)
        transport.close()
        rec.restore()
        self.assertIs(smc3_mod.serial, original)
        self.assertFalse(getattr(smc3_mod.serial, SerialRecorder.SHIM_MARKER, False))
        transport_after = smc3_mod.SerialTransport(HOST_PORT)
        transport_after.open()
        transport_after.write(TEST_FRAME)
        self.assertEqual(len(rec.attempts()), 1)  # post-restore write unseen

    def test_t24_injection_limitation_remains_documented(self):
        """The accepted limitation stays written where users see it: the
        module docstring and the SerialRecorder class docstring both
        state the injection is not thread-safe for concurrent
        independent runs, and restore's docstring documents the
        foreign-injection refusal."""
        module_doc = " ".join(recorder.__doc__.split())
        self.assertIn("not thread-safe", module_doc)
        self.assertIn("concurrent", module_doc)
        class_doc = " ".join(SerialRecorder.__doc__.split())
        self.assertIn("not thread-safe", class_doc)
        self.assertIn("concurrent", class_doc)
        restore_doc = " ".join(SerialRecorder.restore.__doc__.split())
        self.assertIn("foreign injection", restore_doc)


# ----------------------------------------------------------------------
# Task T2.5 — complete attempt-record schema, ordering, and thread safety.
# ----------------------------------------------------------------------


class AttemptSchemaTests(unittest.TestCase):
    """Task T2.5: every write-attempt record carries the full required
    schema: attempt_seq, timestamp, monotonic_timestamp, frame_bytes,
    returned_count, expected_count, status, and exception (Implementation.md
    section 5, "Required attempt record").

    Proven here: the exact eight-field shape and per-field types; monotonic
    sequence numbers and monotonic timestamps (timestamps are taken under the
    recorder lock, so record order and time order can never disagree); that
    frame_bytes/expected_count are data known before write() while returned_count
    is separate write-result data; that a completed write's status is the
    ATTEMPT_STATUS_OK classified by task T2.8 while its exception stays None
    (only task T2.7's record_exception_attempt records exceptions); and thread-safety under contention (Implementation.md
    section 5: "The recorder must be thread-safe because CommandHub writes
    from its own worker thread").
    """

    SCHEMA_FIELDS = (
        "attempt_seq",
        "timestamp",
        "monotonic_timestamp",
        "frame_bytes",
        "returned_count",
        "expected_count",
        "status",
        "exception",
        "is_motor_frame",
    )

    def test_record_helper_signature_stays_stable(self):
        """T2.5 did not change the shim-facing record_write_attempt(data,
        returned_count) signature from T2.1/T2.3."""
        sig = inspect.signature(SerialRecorder.record_write_attempt)
        self.assertEqual(
            [p for p in sig.parameters if p != "self"], ["data", "returned_count"]
        )

    def test_completed_write_record_contains_exact_required_schema(self):
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        records = rec.attempts()
        self.assertEqual(len(records), 1)
        (attempt,) = records
        self.assertEqual(
            set(attempt),
            set(self.SCHEMA_FIELDS),
            "the record must carry exactly the required schema fields",
        )
        self.assertEqual(len(attempt), 9)
        self.assertEqual(attempt["attempt_seq"], 1)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
        self.assertEqual(attempt["returned_count"], len(TEST_FRAME))
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_OK)
        self.assertIsNone(attempt["exception"])
        # T3.3: motor frames are detected by signature (5 bytes, 0x5B start, 0x5D end)
        self.assertTrue(attempt["is_motor_frame"])

    def test_schema_fields_have_expected_types(self):
        """attempt_seq is an int; wall/monotonic times are floats; frame
        bytes are bytes; counts are ints; a completed write's status is the
        classified ATTEMPT_STATUS_OK and its exception stays None."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        (attempt,) = rec.attempts()
        self.assertIsInstance(attempt["attempt_seq"], int)
        self.assertNotIsInstance(attempt["attempt_seq"], bool)
        self.assertIsInstance(attempt["timestamp"], float)
        self.assertIsInstance(attempt["monotonic_timestamp"], float)
        self.assertIsInstance(attempt["frame_bytes"], bytes)
        self.assertIsInstance(attempt["returned_count"], int)
        self.assertIsInstance(attempt["expected_count"], int)
        self.assertIsInstance(attempt["is_motor_frame"], bool)
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_OK)
        self.assertIsNone(attempt["exception"])

    def test_recorder_class_invents_no_status_or_try_except(self):
        """T2.6 fixed the canonical vocabulary at module level; the
        `SerialRecorder` class itself still invents no status string and
        no try/except block - the record-then-reraise ERROR policy lives
        at the shim write boundary (task T2.7); task T2.8 classifies completed
        attempts with the canonical module constants, never new status words."""
        tree = ast.parse(inspect.getsource(SerialRecorder))
        vocabulary = {"OK", "ERROR", "SHORT", "PARTIAL", "FAILED",
                      "EXCEPTION", "TIMEOUT"}
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertEqual(
            literals & vocabulary,
            set(),
            "the status vocabulary lives at module level (T2.6); the"
            " SerialRecorder class must not inline status strings or"
            " invent extra ones",
        )
        try_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]
        self.assertEqual(
            try_nodes, [], "T2.5/T2.6 added no try/except block: the record-then-"
            "reraise ERROR policy is task T2.7"
        )

    def test_expected_count_derives_from_payload_not_write_result(self):
        """Data known before write(): expected_count is the frame length,
        independent of whatever the underlying write later reports."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        payload = TEST_FRAME + b"extended-payload"
        ser = host.open_serial()
        host.write_serial(ser, payload)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["expected_count"], len(payload))
        self.assertEqual(attempt["expected_count"], len(attempt["frame_bytes"]))

    def test_expected_count_follows_payload_length_not_five_byte_frame(self):
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        payload = TEST_FRAME + b"extra"
        ser = host.open_serial()
        host.write_serial(ser, payload)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["expected_count"], len(payload))

    def test_frame_bytes_snapshot_survives_payload_mutation(self):
        """frame_bytes is the payload snapshot, never a live reference the
        caller can mutate after the fact."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        payload = bytearray(TEST_FRAME)
        ser = host.open_serial()
        host.write_serial(ser, payload)
        (attempt,) = rec.attempts()
        payload[:] = b"\x00" * len(payload)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
        self.assertNotEqual(attempt["frame_bytes"], bytes(payload))

    def test_attempt_sequence_numbers_are_monotonically_increasing(self):
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        for _ in range(4):
            host.write_serial(ser, TEST_FRAME)
        records = rec.attempts()
        self.assertEqual(
            [record["attempt_seq"] for record in records],
            list(range(1, 5)),
            "attempt_seq numbers records in strictly increasing order",
        )

    def test_monotonic_timestamps_increase_across_writes(self):
        """monotonic_timestamp gives the ordering used for elapsed-time
        measurements (Implementation.md section 5)."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        for _ in range(3):
            host.write_serial(ser, TEST_FRAME)
        stamps = [record["monotonic_timestamp"] for record in rec.attempts()]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(len(stamps), 3)

    def test_monotonic_timestamps_survive_wall_clock_adjustments(self):
        """The wall-clock timestamp may go backwards (NTP-style rewind)
        while monotonic timestamps keep advancing, which is why elapsed-
        time measurements use the monotonic one."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        from unittest import mock

        wall = [1_000_000.0, 1_000_002.0, 900_000.0, 900_001.0, 900_002.0]
        mono = [500.0, 501.5, 503.25, 504.0, 505.0]
        with mock.patch.object(time, "time", side_effect=wall), mock.patch.object(
            time, "monotonic", side_effect=mono
        ):
            for _ in range(3):
                host.write_serial(ser, TEST_FRAME)
        records = rec.attempts()
        wall_values = [record["timestamp"] for record in records]
        mono_values = [record["monotonic_timestamp"] for record in records]
        self.assertLess(mono_values[0], mono_values[1])
        self.assertLess(mono_values[1], mono_values[2])
        self.assertEqual(mono_values, sorted(mono_values))
        self.assertLess(wall_values[0], wall_values[1])
        self.assertLess(wall_values[2], wall_values[1])
        self.assertEqual(len(wall_values), 3)

    def test_recorder_is_thread_safe(self):
        """Implementation.md section 5 requires: "The recorder must be
        thread-safe because CommandHub writes from its own worker thread."
        """
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        writers = 8
        barrier = threading.Barrier(writers * 2 + 1)

        def recorded_write():
            barrier.wait(timeout=10.0)
            host.write_serial(ser, TEST_FRAME)

        def direct_record():
            barrier.wait(timeout=10.0)
            rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))

        threads = [threading.Thread(target=recorded_write) for _ in range(writers)]
        threads += [threading.Thread(target=direct_record) for _ in range(writers)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=10.0)
        for thread in threads:
            thread.join(timeout=10.0)
        self.assertEqual(
            [thread.is_alive() for thread in threads], [False] * len(threads),
            "no worker thread may hang or still be running when sharing"
            " one recorder",
        )
        records = rec.attempts()
        self.assertEqual(len(records), writers * 2)
        sequences = [record["attempt_seq"] for record in records]
        self.assertEqual(sorted(sequences), list(range(1, writers * 2 + 1)))
        stamps = [record["monotonic_timestamp"] for record in records]
        self.assertEqual(stamps, sorted(stamps))

    def test_concurrent_direct_record_calls_get_unique_sequences(self):
        """Thread safety: contention on the sequence counter hands each
        record a unique attempt_seq even under a same-start-time barrier."""
        rec = SerialRecorder()
        writers = 16
        barrier = threading.Barrier(writers + 1)

        def direct_record():
            barrier.wait(timeout=10.0)
            rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))

        threads = [threading.Thread(target=direct_record) for _ in range(writers)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=10.0)
        for thread in threads:
            thread.join(timeout=10.0)
        self.assertEqual(
            [thread.is_alive() for thread in threads], [False] * writers,
            "no thread may crash or time out while contending on one"
            " recorder",
        )
        records = rec.attempts()
        self.assertEqual(len(records), writers)
        sequences = [record["attempt_seq"] for record in records]
        self.assertEqual(len(set(sequences)), writers)
        self.assertEqual(sorted(sequences), list(range(1, writers + 1)))
        stamps = [record["monotonic_timestamp"] for record in records]
        self.assertEqual(stamps, sorted(stamps))

    def test_records_written_under_contention_are_never_partially_written(self):
        """Lock-guarded appends: every contended record carries all eight
        schema fields, and frame_bytes/expected_count belong to the same
        call rather to another thread's attempt."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        payload_a = TEST_FRAME
        payload_b = TEST_FRAME + b"\xaa\xbb"
        barrier = threading.Barrier(9)

        def contended_write(payload):
            barrier.wait(timeout=10.0)
            host.write_serial(ser, payload)

        def contended_record(payload):
            barrier.wait(timeout=10.0)
            rec.record_write_attempt(payload, len(payload))

        threads = []
        for index in range(8):
            payload = payload_a if index % 2 == 0 else payload_b
            if index % 4 < 2:
                target = lambda payload=payload: contended_write(payload)
            else:
                target = lambda payload=payload: contended_record(payload)
            threads.append(threading.Thread(target=target))
        for thread in threads:
            thread.start()
        barrier.wait(timeout=10.0)
        for thread in threads:
            thread.join(timeout=10.0)
        records = rec.attempts()
        self.assertEqual(len(records), 8)
        for record in records:
            self.assertEqual(
                set(record),
                set(self.SCHEMA_FIELDS),
                "no record may be missing a schema field under contention",
            )
            self.assertEqual(record["expected_count"], len(record["frame_bytes"]))
            self.assertEqual(
                record["returned_count"], len(record["frame_bytes"])
            )

    def test_error_record_carries_full_schema_under_failed_write(self):
        """T2.7 record-then-reraise: even under the full T2.5 schema, a raised
        write propagates and appends exactly one record that keeps the whole
        eight-field shape - frame_bytes/expected_count survive the failure,
        returned_count is None (no byte count was reported), status is the
        canonical ERROR, and exception is populated (Implementation.md 5.3)."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        records = rec.attempts()
        assert len(records) == 1, "one failed write must append exactly one record"
        attempt = records[0]
        assert list(attempt) == list(self.SCHEMA_FIELDS), (
            "the ERROR record must keep the T2.5 schema"
        )
        assert attempt["frame_bytes"] == TEST_FRAME
        assert attempt["expected_count"] == len(TEST_FRAME)
        assert attempt["returned_count"] is None
        assert attempt["status"] is recorder.ATTEMPT_STATUS_ERROR
        assert isinstance(attempt["exception"], fake.SerialException)

    def test_attempt_record_survives_restore(self):
        """T2.4 keeps attempt data across restore; T2.5 makes that
        surviving data complete: the pre-restore record keeps all nine
        schema fields and its content is unchanged afterwards."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        (before,) = rec.attempts()
        self.assertEqual(len(before), 9)
        rec.restore(host)
        records = rec.attempts()
        self.assertEqual(len(records), 1)
        (after,) = records
        self.assertEqual(
            set(after),
            set(self.SCHEMA_FIELDS),
            "attempt data survives restore and stays schema-complete",
        )
        self.assertEqual(after, before)


# ----------------------------------------------------------------------------
# Task T2.6 - canonical serial write-attempt status vocabulary
# ----------------------------------------------------------------------------


class StatusVocabularyTests(unittest.TestCase):
    """The three status words are defined once, in ``recorder.py`` itself.

    T2.6 is the vocabulary step only: it names the three statuses that
    :meth:`SerialRecorder.record_write_attempt` uses, and adds no
    classification, no exception recording, and no failed-write
    presentation. Tasks T2.7 and T2.8 later apply those same words to
    failures and to completed attempts; these tests pin the agreed
    representation and check that nothing earlier than T2.6 invented a
    competing set of status words.
    """

    STATUS_WORDS = ("OK", "SHORT", "ERROR")

    def test_recorder_defines_the_vocabulary(self) -> None:
        """The three status constants and their aggregate exist."""
        for name in (
            "ATTEMPT_STATUS_OK",
            "ATTEMPT_STATUS_SHORT",
            "ATTEMPT_STATUS_ERROR",
            "ATTEMPT_STATUSES",
        ):
            assert hasattr(recorder, name), f"{name} missing from recorder.py"

    def test_exactly_three_vocabulary_values(self) -> None:
        """``OK``, ``SHORT``, and ``ERROR`` are the whole set."""
        values = (
            recorder.ATTEMPT_STATUS_OK,
            recorder.ATTEMPT_STATUS_SHORT,
            recorder.ATTEMPT_STATUS_ERROR,
        )
        assert len(values) == 3
        assert len(set(values)) == 3, "status values must be distinct"
        assert sorted(values) == sorted(self.STATUS_WORDS), (
            "canonical status set must be exactly OK, SHORT, and ERROR"
        )

    def test_named_constants_match_tuple(self) -> None:
        """The constants and the tuple are two views of the same three."""
        assert recorder.ATTEMPT_STATUSES == (
            recorder.ATTEMPT_STATUS_OK,
            recorder.ATTEMPT_STATUS_SHORT,
            recorder.ATTEMPT_STATUS_ERROR,
        )
        assert sorted(recorder.ATTEMPT_STATUSES) == sorted(self.STATUS_WORDS)

    def test_canonical_repr_is_plain_str(self) -> None:
        """Uppercase plain strings, so CSV and JSON stay byte-compatible."""
        for value in recorder.ATTEMPT_STATUSES:
            assert type(value) is str, f"{value!r} must be a plain str"
            assert value.isupper(), f"{value!r} must use uppercase status words"

    def test_single_non_conflicting_definition(self) -> None:
        """One canonical module, no duplicate or conflicting status words."""
        tree = ast.parse(RECORDER_SOURCE)
        body = list(tree.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]  # the module docstring is not a definition

        candidates = {"OK", "SHORT", "ERROR", "PARTIAL", "EXCEPTION", "FAILED", "TIMEOUT"}

        def str_constants(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return [node.value]
            if isinstance(node, ast.Tuple):
                out = []
                for item in node.elts:
                    out.extend(str_constants(item))
                return out
            return []

        status_defs = []
        for node in body:
            if not isinstance(node, ast.Assign):
                continue
            strs = str_constants(node.value)
            if strs and any(word in candidates for word in strs):
                status_defs.append((node, strs))

        words = {word for _, strs in status_defs for word in strs}
        assert words == set(STATUS_WORDS), (
            f"module-level status words were {sorted(words)}; canonical set is "
            "ERROR, OK, SHORT"
        )

        single = sorted(strs for _, strs in status_defs if len(strs) == 1)
        assert single == [["ERROR"], ["OK"], ["SHORT"]], (
            "each status word must be bound exactly once as a named constant"
        )

        target_names = sorted(
            target.id
            for node, _ in status_defs
            for target in node.targets
            if isinstance(target, ast.Name)
        )
        assert target_names == [
            "ATTEMPT_STATUS_ERROR",
            "ATTEMPT_STATUS_OK",
            "ATTEMPT_STATUS_SHORT",
        ], "each status word must be bound exactly once as a named constant"
        for node, strs in status_defs:
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if len(strs) == 1:
                    assert name.endswith(strs[0]), (
                        f"{name} = {strs[0]!r} conflicts with its name"
                    )

        aggregate_assigns = [
            node
            for node in body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Tuple)
            and len(node.value.elts) == 3
            and all(isinstance(element, ast.Name) for element in node.value.elts)
        ]
        assert len(aggregate_assigns) == 1, (
            "exactly one aggregate of the three statuses is allowed"
        )
        referenced = sorted(
            element.id for element in aggregate_assigns[0].value.elts
        )
        assert referenced == [
            "ATTEMPT_STATUS_ERROR",
            "ATTEMPT_STATUS_OK",
            "ATTEMPT_STATUS_SHORT",
        ], "the aggregate must name exactly the three canonical status constants"

    def test_vocabulary_defined_once_across_package(self) -> None:
        """No other v0.5 module binds a bare status word at module level."""
        other_modules = sorted(
            path for path in PACKAGE.glob("*.py")
            if path.name not in {"__init__.py", "recorder.py"}
        )
        status_words = set(self.STATUS_WORDS)
        for path in other_modules:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                value = node.value
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                assert value.value not in status_words, (
                    f"{path.name} would define a competing status constant"
                )

    def test_existing_tests_stay_intact(self) -> None:
        """The T2.5 schema contract is still asserted by the existing file."""
        schema_source = (
            inspect.getsource(RecorderTests)
            + inspect.getsource(AttemptSchemaTests)
        )
        # Task T2.8 retargets the completed-write status pins from None to
        # ATTEMPT_STATUS_OK, so the intact contract here is that three or
        # more schema cases still pin a completed write's status, however
        # that status is represented before or after classification.
        status_pins = schema_source.count('IsNone(attempt["status"])') + schema_source.count(
            "recorder.ATTEMPT_STATUS_OK"
        )
        exception_none = schema_source.count('IsNone(attempt["exception"])')
        assert status_pins >= 3, "at least three schema cases must pin completed-write status"
        assert exception_none >= 3, "at least three schema cases must pin exception to None"
        assert "test_recorder_class_invents_no_status_or_try_except" in {
            name for name in dir(AttemptSchemaTests) if name.startswith("test_")
        }, "the early-vocabulary guard must still run"

    def test_record_fields_remain_unchanged(self) -> None:
        """T2.6 changed no field name, order, or initial value."""
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)
        host.close_serial(ser)
        records = rec.attempts()
        assert len(records) == 1, "one write must yield exactly one record"
        attempt = records[0]
        assert list(attempt) == list(AttemptSchemaTests.SCHEMA_FIELDS), (
            "field names and order must stay the T2.5 schema"
        )
        assert attempt["status"] is recorder.ATTEMPT_STATUS_OK, (
            "task T2.8 classifies a full write as OK"
        )
        assert attempt["exception"] is None, "a returned write records no exception"

    def test_failed_write_record_becomes_error_once(self) -> None:
        """T2.7 is implemented: the vocabulary is now applied to failures - a
        failed write raises and appends exactly one record using the canonical
        ERROR word with the exception information preserved."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        records = rec.attempts()
        assert len(records) == 1, "the failed write must yield exactly one record"
        assert records[0]["status"] is recorder.ATTEMPT_STATUS_ERROR, (
            "the failure must use the canonical T2.6 ERROR word"
        )
        assert records[0]["exception"] is not None, (
            "the exception information must survive in the record"
        )

    def test_t28_short_write_classified_when_present(self) -> None:
        """Task T2.8: a write that returned fewer bytes is labelled SHORT.
        The archived stub never short-returns, so this calls the helper
        directly with a returned count that differs from expected."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, 1)  # a write that returned fewer bytes
        (attempt,) = rec.attempts()
        assert attempt["returned_count"] == 1, "the short count must still be preserved"
        assert attempt["expected_count"] == len(TEST_FRAME)
        assert attempt["status"] is recorder.ATTEMPT_STATUS_SHORT, (
            "task T2.8 classifies a non-exact returned count as SHORT"
        )

    def test_recorder_source_has_exactly_one_try(self) -> None:
        """Task T2.7 added exactly one try/except to recorder.py: the shim
        write's record-then-reraise. It must live inside the shim's write()
        and its handler must end in a bare raise so the original exception
        object always propagates untouched (never replaced or swallowed)."""
        tree = ast.parse(RECORDER_SOURCE)
        try_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
        assert len(try_nodes) == 1, (
            "exactly the one T2.7 record-then-reraise block in the shim's write"
        )
        (try_node,) = try_nodes
        shim_writes = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "write"
            and any(stmt is try_node for stmt in n.body)
        ]
        assert len(shim_writes) == 1, (
            "the one try/except must live at the top of the shim's write()"
        )
        handler = try_node.handlers[0]
        raise_nodes = [n for n in ast.walk(handler) if isinstance(n, ast.Raise)]
        assert len(raise_nodes) == 1, "the handler must end in a bare raise"
        (raise_node,) = raise_nodes
        assert raise_node.exc is None, (
            "the raise must be bare: the original exception is re-raised as-is"
        )

    def test_no_failure_handling_inside_recorders(self) -> None:
        """No failed-write or short-write presentation was added."""
        tree = ast.parse(RECORDER_SOURCE)
        recorders = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for node in recorders:
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            for stmt in body:
                assert not isinstance(stmt, ast.Try), (
                    f"{node.name} must not present failures yet"
                )

    def test_recorder_adds_no_presentation_sink(self) -> None:
        """T2.6 added no file, ledger, or CSV write."""
        tree = ast.parse(RECORDER_SOURCE)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name is not None:
                assert name not in PRESENTATION_WRITERS, (
                    f"{name}() would be a new presentation sink"
                )

    def test_recorder_owns_no_device_path(self) -> None:
        """T2.6 added no serial access or device path."""
        tree = ast.parse(RECORDER_SOURCE)
        assert not any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(DEVICE_PATH_PREFIXES)
            for node in ast.walk(tree)
        )


class ExceptionRecordingTests(unittest.TestCase):
    """Task T2.7: the record-then-reraise exception policy at the shim write.

    Pins Implementation.md section 5.3: an underlying write exception
    produces exactly one ERROR attempt record; the exception information
    (the original exception object: identity, type, arguments) is stored
    unchanged; the original exception propagates to the caller untouched
    and is never converted into a successful return; sequence numbering,
    timestamps, frame bytes and payload-derived expected counts keep the
    T2.5 contract across failures; concurrent failures still take unique
    sequence numbers through the shared lock and counter; and completed
    writes keep their untouched successful-write behaviour, now with the
    status classified OK or SHORT by task T2.8 while exception stays None.
    """

    def test_failed_write_records_exactly_one_error_attempt(self) -> None:
        """One raised write appends one record: ERROR status, no byte count."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        raised = None
        try:
            host.write_serial(ser, TEST_FRAME)
        except fake.SerialException as exc:
            raised = exc
        self.assertIsNotNone(raised, "the failure must propagate to the caller")
        attempts = rec.attempts()
        self.assertEqual(
            len(attempts), 1, "exactly one attempt record per failed write"
        )
        (attempt,) = attempts
        self.assertEqual(attempt["attempt_seq"], 1)
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_ERROR)
        self.assertIsNone(
            attempt["returned_count"], "a raised write reported no byte count"
        )

    def test_exception_information_recorded_unchanged(self) -> None:
        """The record holds the original exception object itself: same
        identity, type, and arguments as the exception the caller sees."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        raised = None
        try:
            host.write_serial(ser, TEST_FRAME)
        except fake.SerialException as exc:
            raised = exc
        self.assertIsNotNone(raised, "the failure must propagate to the caller")
        (attempt,) = rec.attempts()
        self.assertIs(
            attempt["exception"], raised, "the exact object the caller got"
        )
        self.assertEqual(attempt["exception"].args, ("port closed",))

    def test_original_exception_propagates_not_converted(self) -> None:
        """The shim never converts the failure into a successful return: the
        caller still sees the stub's SerialException, unchanged."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException) as caught:
            host.write_serial(ser, TEST_FRAME)
        (attempt,) = rec.attempts()
        self.assertIs(type(caught.exception), fake.SerialException)
        self.assertEqual(caught.exception.args, ("port closed",))
        self.assertIs(attempt["exception"], caught.exception)

    def test_sequence_timestamps_and_frames_survive_failures(self) -> None:
        """fail/good/fail keeps whole-record sequencing: sequence numbers
        1, 2, 3 with non-decreasing monotonic timestamps; every record
        keeps the attempted frame bytes and payload-derived expected
        count; the failed records carry ERROR while the completed middle
        record is classified OK by task T2.8, and exception stays None."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser_a = host.open_serial()
        host.close_serial(ser_a)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser_a, TEST_FRAME)
        ser_b = host.open_serial()
        returned = host.write_serial(ser_b, TEST_FRAME)
        host.close_serial(ser_b)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser_b, TEST_FRAME)
        attempts = rec.attempts()
        self.assertEqual(
            [a["attempt_seq"] for a in attempts], [1, 2, 3],
            "failures take their place in the sequence without renumbering",
        )
        self.assertEqual(
            [a["status"] for a in attempts],
            [
                recorder.ATTEMPT_STATUS_ERROR,
                recorder.ATTEMPT_STATUS_OK,
                recorder.ATTEMPT_STATUS_ERROR,
            ],
            "failures carry ERROR and the completed middle record is"
            " classified OK by task T2.8",
        )
        monotonic = [a["monotonic_timestamp"] for a in attempts]
        self.assertTrue(
            all(x <= y for x, y in zip(monotonic, monotonic[1:])),
            "record order and time order can never disagree",
        )
        for attempt in attempts:
            self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
            self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(
            [a["returned_count"] for a in attempts], [None, returned, None]
        )

    def test_concurrent_failures_take_unique_sequence_numbers(self) -> None:
        """Shared lock and counter: interleaved failed records never collide
        and every ERROR record keeps an exception object of its own."""
        rec = SerialRecorder()
        writers = 4
        per_writer = 8
        barrier = threading.Barrier(writers + 1)

        class ConcurrencyFailure(Exception):
            pass

        def record_repeated_failure(writer_index):
            for i in range(per_writer):
                rec.record_exception_attempt(
                    TEST_FRAME, ConcurrencyFailure(f"writer {writer_index}")
                )
            barrier.wait()  # barrier joins the writers and the main thread

        threads = [
            threading.Thread(target=record_repeated_failure, args=(i,))
            for i in range(writers)
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=10.0)  # deterministic: each thread waits for all
        for thread in threads:
            thread.join()
        attempts = rec.attempts()
        self.assertEqual(len(attempts), writers * per_writer)
        self.assertEqual(
            sorted(a["attempt_seq"] for a in attempts),
            list(range(1, writers * per_writer + 1)),
            "sequence numbers must be unique despite interleaving",
        )
        self.assertEqual(
            [a["status"] for a in attempts],
            [recorder.ATTEMPT_STATUS_ERROR] * writers * per_writer,
        )
        for attempt in attempts:
            self.assertIsInstance(
                attempt["exception"], ConcurrencyFailure,
                "the failed write's own exception must survive",
            )

    def test_t28_short_write_classification_applied(self) -> None:
        """Task T2.8: the helper labels a non-exact returned count SHORT
        (direct call, since the archived stub never short-returns); the
        partial-write data and both counts stay separate observations."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, 3)  # a write that returned fewer bytes
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], 3, "the short count survives")
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(
            attempt["status"], recorder.ATTEMPT_STATUS_SHORT,
            "task T2.8 classifies a non-exact returned count as SHORT",
        )
        self.assertIsNone(attempt["exception"], "a returned write has no exception")

    def test_successful_write_behaviour_untouched_by_t27(self) -> None:
        """The T2.1/T2.5 success path through the shim is unchanged: the
        real return value passes through and the record is classified OK
        by task T2.8 with a full payload observation and no exception."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        returned = host.write_serial(ser, TEST_FRAME)
        host.close_serial(ser)
        self.assertEqual(returned, len(TEST_FRAME), "the shim returned the real count")
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["attempt_seq"], 1)
        self.assertEqual(attempt["returned_count"], returned)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(
            attempt["status"], recorder.ATTEMPT_STATUS_OK,
            "task T2.8 classifies an exact returned count as OK",
        )
        self.assertIsNone(attempt["exception"], "the write did not raise")


class AttemptClassificationTests(unittest.TestCase):
    """Task T2.8: completed serial write attempts get an OK/SHORT label.
    Implementation.md section 5.3 fixes the three-way attempt status:
    OK only when write() returned exactly the payload-derived expected
    count, SHORT for any other returned count (the partial-write bytes
    stay in frame_bytes and both counts stay recorded separately), and
    ERROR only on the T2.7 record-then-reraise exception path, which
    stays exclusively reserved for record_exception_attempt. The
    classification is one label on an attempt that was already recorded:
    the shim still passes the real write() count through untouched, no
    retry, retransmission, recovery or logging sink is invented, and the
    five-byte SMC3 frame length is never hard-coded.
    """

    SHORT_RETURNED = 3
    OVER_RETURNED = len(TEST_FRAME) + 1

    def _shim_record(self):
        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        return host, rec, ser

    def test_exact_shim_write_classified_ok(self) -> None:
        """write() returned the whole payload, so the record is OK."""
        host, rec, ser = self._shim_record()
        returned = host.write_serial(ser, TEST_FRAME)
        host.close_serial(ser)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], returned, "the real count is stored")
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_OK)

    def test_short_count_classified_short(self) -> None:
        """Returned fewer than expected: the label is SHORT."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, self.SHORT_RETURNED)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], self.SHORT_RETURNED)
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_SHORT)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME, "partial-write data survives")

    def test_zero_byte_write_classified_short(self) -> None:
        """write() returned nothing at all: a completed zero-length attempt
        is still not exact, so it is SHORT, not ERROR."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, 0)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], 0)
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_SHORT)

    def test_over_returned_count_classified_short(self) -> None:
        """Only the exact count gets OK: any other returned count is SHORT,
        which keeps classification one comparison against expected_count."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, self.OVER_RETURNED)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], self.OVER_RETURNED)
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_SHORT)

    def test_five_byte_frame_expectation_survives(self) -> None:
        """The SMC3 frame is five bytes, but expected_count comes from the
        payload: a one-byte frame written in full is OK for that payload."""
        rec = SerialRecorder()
        rec.record_write_attempt(b"\x5b", 1)
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["frame_bytes"], b"\x5b")
        self.assertEqual(attempt["expected_count"], 1, "expected_count derives from the payload")
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_OK)

    def test_short_write_returns_its_real_count_untouched(self) -> None:
        """The shim still hands the caller exactly the underlying write()
        return value: labelling the attempt changes no return value, so a
        stub Serial whose write() reports a short count surfaces that
        count both to the caller and in the record (the shim never
        substitutes its own count)."""
        short_returned = self.SHORT_RETURNED

        class StubSerial:
            """pyserial.Serial stand-in whose write() reports a short count."""

            def __init__(self, *args, **kwargs):
                self._stub = True

            def write(self, data):
                return short_returned

            def close(self):
                pass

            def reset_input(self):
                pass

            def flush(self):
                pass

        stub_mod = types.ModuleType("h3_short_write_stub")
        stub_mod.Serial = StubSerial
        stub_mod.SerialException = Exception
        host = make_serial_host()
        rec = SerialRecorder()
        host.serial = create_serial_shim(stub_mod, rec)
        ser = host.open_serial()
        returned = host.write_serial(ser, TEST_FRAME)
        self.assertEqual(returned, short_returned, "the real short count passes through")
        (attempt,) = rec.attempts()
        self.assertEqual(attempt["returned_count"], short_returned)
        self.assertEqual(attempt["expected_count"], len(TEST_FRAME))
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_SHORT)

    def test_error_path_stays_exclusive_to_exception(self) -> None:
        """A write that raised records ERROR and never gets OK/SHORT; its
        returned_count stays None because no count was reported."""
        host, rec, ser = self._shim_record()
        fake = host.serial
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        (attempt,) = rec.attempts()
        self.assertIs(attempt["status"], recorder.ATTEMPT_STATUS_ERROR)
        self.assertIsNone(attempt["returned_count"], "a raised write reported no count")

    def test_ok_short_error_never_converted(self) -> None:
        """One OK, one SHORT and one ERROR attempt in time order keep their
        own labels and sequence numbers: classification never moves a
        failed attempt into the completed vocabulary."""
        host, rec, ser = self._shim_record()
        fake = host.serial
        host.write_serial(ser, TEST_FRAME)
        host.close_serial(ser)
        rec.record_write_attempt(TEST_FRAME, self.SHORT_RETURNED)
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        self.assertEqual([a["attempt_seq"] for a in rec.attempts()], [1, 2, 3])
        self.assertEqual(
            [a["status"] for a in rec.attempts()],
            [recorder.ATTEMPT_STATUS_OK, recorder.ATTEMPT_STATUS_SHORT, recorder.ATTEMPT_STATUS_ERROR],
        )
        self.assertEqual([a["exception"] for a in rec.attempts()], [None, None, rec.attempts()[-1]["exception"]])

    def test_no_retry_or_retransmission_invented(self) -> None:
        """Labelling one completed attempt creates exactly one attempt: no
        retry, extra write, synchronization object or logging sink."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, self.SHORT_RETURNED)
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 1, "one write attempt yields one record")
        self.assertEqual(attempts[0]["attempt_seq"], 1)

    def test_classification_uses_only_the_canonical_vocabulary(self) -> None:
        """The status written by task T2.8 is always one of the three T2.6
        words, never a new label or a non-string."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        rec.record_write_attempt(TEST_FRAME, self.SHORT_RETURNED)
        host, rec_host, ser = self._shim_record()
        fake = host.serial
        host.close_serial(ser)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        statuses = [a["status"] for a in rec.attempts()]
        self.assertEqual(statuses, [recorder.ATTEMPT_STATUS_OK, recorder.ATTEMPT_STATUS_SHORT])
        self.assertEqual(
            [a["status"] for a in rec_host.attempts()], [recorder.ATTEMPT_STATUS_ERROR]
        )
        for status in statuses + [recorder.ATTEMPT_STATUS_ERROR]:
            self.assertIn(status, recorder.ATTEMPT_STATUSES, "no vocabulary outside T2.6")


class AttemptBarrierTests(unittest.TestCase):
    """T3.1: write-attempt completion Barrier (Implementation.md section 6).

    The barrier must synchronize with the completion of an actual serial
    write attempt: a record appended when the host's write() call returns or
    raises. It may not complete on queue emptiness, buffer flushing, or the
    serial object's pending-response state, and it may not invent, drop or
    reorder records. Every scenario here is software-only: the worker that
    blocks inside a write attempt is the fake serial stub of this suite, so
    "blocked" means parked on a threading.Event between the write call and
    its return, never a device or a real thread-timing race.
    """

    STUBBED_TIMEOUT = 2.0

    def _install_blocking_serial(self, host, rec, started, released):
        """Shim `host` with `rec`, then wrap the shim Serial so returned
        handles park inside write() until `released` is set. `started` marks
        the moment write() is entered but not yet returned; the recorder sees
        no record until the parked write really returns."""
        rec.install(host)
        base_ctor = host.serial.Serial

        def blocking_ctor(*args, **kwargs):
            ser = base_ctor(*args, **kwargs)
            parked = types.SimpleNamespace(
                close=ser.close,
                write=lambda data: (
                    started.set(),
                    released.wait(),
                    ser.write(data),
                )[-1],
            )
            return parked

        host.serial.Serial = blocking_ctor

    def test_barrier_blocks_until_blocked_write_attempt_completes(self) -> None:
        """With a worker parked between the write() call and its return, the
        barrier for one attempt does not complete until that write attempt
        really completes: it keeps waiting while the journal is empty, and
        only after the parked write returns does it hand back the record."""
        host = make_serial_host()
        rec = SerialRecorder()
        started = threading.Event()
        released = threading.Event()
        self._install_blocking_serial(host, rec, started, released)

        write_results = []
        batches = []
        wait_started = threading.Event()
        barrier = Barrier(rec)

        def worker():
            ser = host.open_serial()
            write_results.append(host.write_serial(ser, TEST_FRAME))

        def waiter():
            wait_started.set()
            batches.append(barrier.wait_for_attempts(1, self.STUBBED_TIMEOUT))

        worker_thread = threading.Thread(target=worker, daemon=True)
        waiter_thread = threading.Thread(target=waiter, daemon=True)
        worker_thread.start()
        waiter_thread.start()

        started.wait(timeout=self.STUBBED_TIMEOUT)
        self.assertTrue(started.is_set(), "software-only worker reached write()")
        wait_started.wait(timeout=self.STUBBED_TIMEOUT)
        self.assertTrue(wait_started.is_set(), "the barrier wait has begun")
        # The worker is still parked inside write(): the barrier cannot have
        # counted the attempt, so no record exists yet.
        self.assertEqual(rec.attempts(), [], "no completed attempt while parked")

        released.set()
        worker_thread.join(timeout=self.STUBBED_TIMEOUT)
        waiter_thread.join(timeout=self.STUBBED_TIMEOUT)
        self.assertFalse(worker_thread.is_alive(), "worker's write attempt completed")
        self.assertFalse(waiter_thread.is_alive(), "barrier wait returned")

        self.assertEqual(len(write_results), 1)
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        returned = write_results[0]
        self.assertEqual(len(batch), 1, "one attempt completed the wait")
        attempt = batch[0]
        self.assertEqual(attempt["attempt_seq"], 1)
        self.assertEqual(attempt["status"], recorder.ATTEMPT_STATUS_OK)
        self.assertEqual(attempt["frame_bytes"], TEST_FRAME)
        self.assertEqual(attempt["returned_count"], returned)
        self.assertEqual(attempt["exception"], None)

    def test_barrier_times_out_while_write_attempt_still_parked(self) -> None:
        """Same parking, but never released: the bounded wait must time out
        at its deadline and raise TimeoutError, not fake success, and must
    not consume the attempt it never saw."""
        host = make_serial_host()
        rec = SerialRecorder()
        started = threading.Event()
        released = threading.Event()
        self._install_blocking_serial(host, rec, started, released)

        observed = []
        wait_started = threading.Event()
        barrier = Barrier(rec)

        def worker():
            ser = host.open_serial()
            host.write_serial(ser, TEST_FRAME)

        def waiter():
            wait_started.set()
            deadline = _TIME.monotonic()
            try:
                barrier.wait_for_attempts(1, 0.05)
            except TimeoutError as exc:
                observed.append((exc, _TIME.monotonic() - deadline))

        worker_thread = threading.Thread(target=worker, daemon=True)
        waiter_thread = threading.Thread(target=waiter, daemon=True)
        worker_thread.start()
        waiter_thread.start()

        started.wait(timeout=self.STUBBED_TIMEOUT)
        self.assertTrue(started.is_set(), "software-only worker reached write()")
        wait_started.wait(timeout=self.STUBBED_TIMEOUT)
        self.assertTrue(wait_started.is_set(), "the barrier wait has begun")
        waiter_thread.join(timeout=self.STUBBED_TIMEOUT)
        self.assertFalse(waiter_thread.is_alive(), "bounded wait returned")

        exc, elapsed = observed[0]
        self.assertIsInstance(exc, TimeoutError, "a stuck attempt fails the wait")
        self.assertGreaterEqual(elapsed, 0.05, "the wait kept its whole bound")
        self.assertLess(elapsed, 1.05, "the wait ended at its deadline, bounded")
        self.assertEqual(rec.attempts(), [], "a parked attempt is never counted")
        self.assertTrue(worker_thread.is_alive(), "the attempt is still in flight")
        released.set()
        worker_thread.join(timeout=self.STUBBED_TIMEOUT)
        self.assertFalse(worker_thread.is_alive())
        # the failed wait consumed nothing: the eventual attempt is still pending
        batch = barrier.wait_for_attempts(1, self.STUBBED_TIMEOUT)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["status"], recorder.ATTEMPT_STATUS_OK)

    def test_barrier_error_attempt_counts_as_completed_write(self) -> None:
        """A write attempt that raises still completed (the host call returned
        control after the shim recorded the failure): an ERROR record
        satisfies the barrier, so T3.7 can count missing frames even when
        writes fail."""
        host = make_serial_host()
        fake = host.serial
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()
        host.close_serial(ser)
        barrier = Barrier(rec)
        with self.assertRaises(fake.SerialException):
            host.write_serial(ser, TEST_FRAME)
        batch = barrier.wait_for_attempts(1, 0.05)
        self.assertEqual(len(batch), 1, "the ERROR attempt completed the wait")
        self.assertEqual(batch[0]["status"], recorder.ATTEMPT_STATUS_ERROR)

    def test_barrier_distinguishes_short_from_complete_through_batch(self) -> None:
        """Implementation.md section 6's required distinction: the batch
        handed back by the barrier keeps the T2.8 classification, so a short
        write is told apart from a complete one through the barrier."""
        rec = SerialRecorder()
        host = make_serial_host()
        rec.install(host)
        ser = host.open_serial()
        host.write_serial(ser, TEST_FRAME)  # complete write classified OK
        barrier = Barrier(rec)
        rec.record_write_attempt(TEST_FRAME, 1)  # synthetic SHORT attempt
        batch = barrier.wait_for_attempts(1, 0.05)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["status"], recorder.ATTEMPT_STATUS_SHORT)
        self.assertEqual(batch[0]["expected_count"], len(TEST_FRAME))
        self.assertEqual(batch[0]["returned_count"], 1)

    def test_barrier_isolates_attempts_recorded_after_construction(self) -> None:
        """The barrier is a journal cursor: attempts already recorded before
        it was built must not satisfy it."""
        rec = SerialRecorder()
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        barrier = Barrier(rec)
        with self.assertRaises(TimeoutError):
            barrier.wait_for_attempts(1, 0.05)
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        batch = barrier.wait_for_attempts(1, 0.05)
        self.assertEqual(len(batch), 1, "only the later attempt counts")
        self.assertEqual(batch[0]["attempt_seq"], 2)

    def test_barrier_consumes_each_success_once(self) -> None:
        """A completed batch is handed over once: waiting again for that
        consumed attempt times out instead of re-serving it, and only a new
        completion satisfies the next wait."""
        rec = SerialRecorder()
        barrier = Barrier(rec)
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        first = barrier.wait_for_attempts(1, 0.05)
        self.assertEqual([a["attempt_seq"] for a in first], [1])
        with self.assertRaises(TimeoutError):
            barrier.wait_for_attempts(1, 0.05)
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        second = barrier.wait_for_attempts(1, 0.05)
        self.assertEqual([a["attempt_seq"] for a in second], [2])

    def test_barrier_surplus_completed_attempts_are_visible(self) -> None:
        """More completions than the barrier was told to expect stay visible
        (T3.7 needs 'an unexpected motor or missing frame' to be detectable,
        so the surplus records must come back, not be dropped)."""
        rec = SerialRecorder()
        barrier = Barrier(rec)
        for _ in range(3):
            rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        batch = barrier.wait_for_attempts(2, 0.05)
        self.assertEqual(len(batch), 3, "every completion is visible")
        self.assertEqual([a["attempt_seq"] for a in batch], [1, 2, 3])

    def test_barrier_batch_order_is_journal_order(self) -> None:
        """The batch is the journal slice, never a re-derivation: the
        barrier hands back exactly the recorder's own records, in journal
        order, with strictly increasing sequences."""
        rec = SerialRecorder()
        barrier = Barrier(rec)
        rec.record_write_attempt(TEST_FRAME, len(TEST_FRAME))
        rec.record_write_attempt(TEST_FRAME, 1)
        batch = barrier.wait_for_attempts(2, 0.05)
        self.assertEqual(batch, rec.attempts(), "the barrier hands back the journal")
        self.assertEqual(
            [a["status"] for a in batch],
            [recorder.ATTEMPT_STATUS_OK, recorder.ATTEMPT_STATUS_SHORT],
            "journal order preserved, classification intact",
        )
        sequences = [a["attempt_seq"] for a in batch]
        self.assertEqual(sequences, [1, 2])
        self.assertEqual(sequences, sorted(sequences))

    def test_barrier_waits_on_write_attempts_only(self) -> None:
        """Static contract: the barrier synchronizes on the recorder's
        attempt journal — it has no serial-object state to consult at all,
        so queue emptiness, flushing, or pending-response counters cannot
        stand in for write-attempt completion (Implementation.md section
        6.1's rejected patterns)."""
        tree = ast.parse(inspect.getsource(Barrier))
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("attempts", calls, "the barrier reads the attempt journal")
        self.assertTrue(
            calls.isdisjoint(
                {"wait_for_idle", "in_waiting", "tx_count", "flush", "read"}
            ),
            "no queue-emptiness or pending-response synchronization",
        )
        self.assertEqual(calls & {"monotonic"}, {"monotonic"}, "the wait is bounded")


# ----------------------------------------------------------------------------
# Task T3.3 - Exclude Control Frames from Per-Point Attribution
# ----------------------------------------------------------------------------

class ControlFrameTests(unittest.TestCase):
    """T3.3: Control frames must be classified separately and must not
    count toward a point's three motor-position frames (Implementation.md
    section 7, line 312). Control frames remain in the recorder journal
    for diagnostics."""

    def setUp(self):
        self.host = make_serial_host()
        self.rec = SerialRecorder()
        self.rec.install(self.host)

    def test_motor_frames_detected_by_signature(self):
        """Motor frames have exactly 5 bytes, start with 0x5B, and end with 0x5D."""
        ser = self.host.open_serial()
        # Motor frame: 0x5B, motor letter, position bytes, 0x5D
        motor_frame = bytes((0x5B, ord("A"), 0x01, 0x00, 0x5D))
        self.host.write_serial(ser, motor_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]["is_motor_frame"])

    def test_enable_control_frame_not_motor(self):
        """Enable control frame b'[ena]' is not counted as a motor frame."""
        ser = self.host.open_serial()
        enable_frame = b"[ena]"  # 5 bytes: 0x5B, 0x5B, 0x61, 0x6E, 0x61
        self.host.write_serial(ser, enable_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertFalse(attempts[0]["is_motor_frame"])

    def test_disable_control_frame_not_motor(self):
        """Disable control frame b'[]' is not counted as a motor frame."""
        ser = self.host.open_serial()
        disable_frame = b"[]"  # 2 bytes: 0x5B, 0x5D
        self.host.write_serial(ser, disable_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertFalse(attempts[0]["is_motor_frame"])

    def test_version_control_frame_not_motor(self):
        """Version request control frame b'[ver]' is not counted as a motor frame."""
        ser = self.host.open_serial()
        version_frame = b"[ver]"  # 5 bytes: 0x5B, 0x5B, 0x76, 0x65, 0x72
        self.host.write_serial(ser, version_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 1)
        self.assertFalse(attempts[0]["is_motor_frame"])

    def test_control_frames_preserved_in_journal(self):
        """Control frames remain in the recorder journal for diagnostics."""
        ser = self.host.open_serial()
        enable_frame = b"[ena]"
        disable_frame = b"[]"
        version_frame = b"[ver]"
        self.host.write_serial(ser, enable_frame)
        self.host.write_serial(ser, disable_frame)
        self.host.write_serial(ser, version_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 3)
        # All control frames are preserved
        self.assertFalse(attempts[0]["is_motor_frame"])
        self.assertFalse(attempts[1]["is_motor_frame"])
        self.assertFalse(attempts[2]["is_motor_frame"])

    def test_mixed_motor_and_control_frames(self):
        """Motor and control frames can be mixed; only motor frames count."""
        ser = self.host.open_serial()
        enable_frame = b"[ena]"  # control
        motor_frame = bytes((0x5B, ord("A"), 0x01, 0x00, 0x5D))  # motor
        disable_frame = b"[]"  # control
        self.host.write_serial(ser, enable_frame)
        self.host.write_serial(ser, motor_frame)
        self.host.write_serial(ser, disable_frame)
        attempts = self.rec.attempts()
        self.assertEqual(len(attempts), 3)
        # Only the middle frame is a motor frame
        self.assertFalse(attempts[0]["is_motor_frame"])  # enable
        self.assertTrue(attempts[1]["is_motor_frame"])    # motor
        self.assertFalse(attempts[2]["is_motor_frame"])   # disable

    def test_barrier_counts_only_motor_frames(self):
        """Barrier.wait_for_attempts counts only motor frames toward expected."""
        # SerialRecorder and Barrier are already imported at module level (line 108)

        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()

        # Simulate: enable (control), motor A, disable (control), motor B, motor C
        enable_frame = b"[ena]"
        motor_a = bytes((0x5B, ord("A"), 0x01, 0x00, 0x5D))
        disable_frame = b"[]"
        motor_b = bytes((0x5B, ord("B"), 0x02, 0x00, 0x5D))
        motor_c = bytes((0x5B, ord("C"), 0x03, 0x00, 0x5D))

        # Create barrier BEFORE sending frames (simulating driver waiting for motor attempts)
        barrier = Barrier(rec)
        
        # Send all frames after creating the barrier
        host.write_serial(ser, enable_frame)
        host.write_serial(ser, motor_a)
        host.write_serial(ser, disable_frame)
        host.write_serial(ser, motor_b)
        host.write_serial(ser, motor_c)

        batch = barrier.wait_for_attempts(3, timeout=1.0)

        # Should return all 5 attempts (3 motor + 2 control)
        self.assertEqual(len(batch), 5)
        # But only 3 are motor frames
        motor_attempts = [a for a in batch if a["is_motor_frame"]]
        self.assertEqual(len(motor_attempts), 3)
        # Verify the motor attempts are A, B, C in order
        motor_letters = [chr(a["frame_bytes"][1]) for a in motor_attempts]
        self.assertEqual(motor_letters, ["A", "B", "C"])

    def test_barrier_times_out_with_control_frames_only(self):
        """Barrier times out if only control frames are present (no motor frames)."""
        import threading

        host = make_serial_host()
        rec = SerialRecorder()
        rec.install(host)
        ser = host.open_serial()

        def writer():
            # Only send control frames
            host.write_serial(ser, b"[ena]")
            host.write_serial(ser, b"[]")

        writer_thread = threading.Thread(target=writer, daemon=True)
        writer_thread.start()

        barrier = Barrier(rec)
        with self.assertRaises(TimeoutError):
            barrier.wait_for_attempts(3, timeout=0.1)

        # Control frames were still recorded
        attempts = rec.attempts()
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["is_motor_frame"])
        self.assertFalse(attempts[1]["is_motor_frame"])


if __name__ == "__main__":
    unittest.main()
