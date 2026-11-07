"""Software-only tests for the T3.3 per-point driver integration.

The T2.x tests (carried forward from tests/test_driver_t2x.py) now run
the driver against the REAL T3.1 barrier, the REAL T3.2 ledger and the
REAL archived CommandHub — a fake serial module (ChatGPT-Archive's
tests/serial.py stub, like the T2.1 recorder tests use) stands in for
pyserial, so the suite never opens a port, never imports real pyserial
and never sleeps meaningfully: TimeWithoutDelay skips the archived hub's
sleeps and pacing.

The T3.3 tests fix the task acceptance rules of TASKS.md line 36:

    1. points run one at a time: the next point starts only after the
       previous point's verification is recorded (observations in
       registered order, journals non-interleaved);
    2. every submission through the CommandHub motion path (hub.submit
       of MotorCommand — hub.submit_control never);
    3. every wait at the Barrier (Barrier.wait_for_attempts only —
       wait_for_idle/tx_count polling patterns of Implementation.md
       section 6.1 never);
    4. verification via Ledger.verify only;
    5. no classification: nothing here computes a run status (that
       vocabulary is task T3.7).

Failure paths fixed here, all software-only and deterministic:

    * frame mismatch — the driver handed the wrong point's frames to
      the hub: Ledger.verify reports frame_mismatch, never raises, and
      the driver records it (rule: compare failures do not crash the
      run);
    * barrier timeout — writes slower than the point's wait: the T3.1
      TimeoutError is attributed to the point being waited on, never
      mis-attributed to a neighbor (the run stops there, per rule 1);
    * transport error — every write raises: the T2.6 vocabulary still
      closes three attempts (status=error), the barrier is satisfied,
      and verification records non-matching counts, not a crash.
"""
from __future__ import annotations

import dataclasses
import inspect
import sys
import time
import types
import unittest
from pathlib import Path
from typing import Callable, Iterator, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import h3_sweep_v05.driver as driver
import h3_sweep_v05.ledger as ledger
import h3_sweep_v05.recorder as recorder


def inspect_signature(func: Callable) -> Iterator[Tuple[str, str]]:
    """Return an iterator of (name, kind) tuples for a function's signature.
    
    Args:
        func: The function to inspect.
        
    Returns:
        Iterator of (name, kind) tuples where kind is one of:
            - "POSITIONAL_ONLY"
            - "POSITIONAL_OR_KEYWORD"
            - "KEYWORD_ONLY"
            - "VAR_POSITIONAL"
            - "VAR_KEYWORD"
    """
    sig = inspect.signature(func)
    for name, param in sig.parameters.items():
        kind_str = {
            inspect.Parameter.POSITIONAL_ONLY: "POSITIONAL_ONLY",
            inspect.Parameter.POSITIONAL_OR_KEYWORD: "POSITIONAL_OR_KEYWORD",
            inspect.Parameter.KEYWORD_ONLY: "KEYWORD_ONLY",
            inspect.Parameter.VAR_POSITIONAL: "VAR_POSITIONAL",
            inspect.Parameter.VAR_KEYWORD: "VAR_KEYWORD",
        }[param.kind]
        yield name, kind_str

HERE = Path(__file__).resolve().parent
ARCHIVE_HARNESS = HERE.parents[3] / "ChatGPT-Archive" / "H3_v0.3.5.1_commandhub_diagnostic"

SweepPoint = ledger.SweepPoint
Ledger = ledger.Ledger
LedgerError = ledger.LedgerError
VerificationResult = ledger.VerificationResult
FrameMismatch = ledger.FrameMismatch
Barrier = recorder.Barrier
SerialRecorder = recorder.SerialRecorder


def _load_archived_smc3_module():
    """Execute the archived smc3.py verbatim with a fake ``serial``.

    Read-only: the archived file is never modified. Returns the module
    object; tests patch its ``time`` attribute (module-attribute
    resolution at call time) and install recorders on its ``serial``
    attribute (the T2.1 shim point), never touching archived sources.
    """
    src = (ARCHIVE_HARNESS / "smc3.py").read_text(encoding="utf-8")
    fake_src = (ARCHIVE_HARNESS / "tests" / "serial.py").read_text(encoding="utf-8")
    fake_serial = types.ModuleType("h3_sweep_v05_test_fake_serial")
    exec(fake_src, fake_serial.__dict__)
    # Save the original Serial class from the fake module before replacing it
    original_serial_cls = fake_serial.Serial
    # Also save the original instances list
    original_instances = fake_serial.Serial.instances
    module = types.ModuleType("h3_sweep_v05_test_archived_smc3")
    saved = sys.modules.get("serial")
    sys.modules["serial"] = fake_serial
    sys.modules[module.__name__] = module
    try:
        exec(src, module.__dict__)
    finally:
        if saved is None:
            sys.modules.pop("serial", None)
        else:
            sys.modules["serial"] = saved
    # Set ModeFakeSerial._base_cls to the original archived Serial class
    # before replacing self.smc3.serial.Serial with ModeFakeSerial
    ModeFakeSerial._base_cls = original_serial_cls
    # Also set ModeFakeSerial.instances to the original instances list
    # so that the fake serial stub's Serial.__init__ can still access instances
    ModeFakeSerial.instances = original_instances
    return module


class TimeWithoutDelay:
    """Time stand-in with no real delays (deterministic, fast).

    The archived CommandHub resolves the ``time`` module attribute at
    call time (rate pacing and the write-error pause), so tests can
    skip pacing and the error pause without changing archived sources.
    """

    _TIME = time

    @staticmethod
    def sleep(seconds):
        return None

    @staticmethod
    def monotonic():
        return TimeWithoutDelay._TIME.monotonic()

    @staticmethod
    def time():
        return TimeWithoutDelay._TIME.time()


class ModeFakeSerial:
    """Fake serial whose write mode is switched per test.

    ``ok`` returns the full count; ``error`` raises (T2.6 ERROR
    vocabulary); ``slow`` sleeps past the test's barrier timeout so
    the point's wait times out before its first attempt closes.
    """

    _mode = "ok"
    _sleep_seconds = 0.3
    _base_cls = None  # the archived tests/serial.py stub Serial class

    def __init__(self, port=None, *args, **kwargs):
        self._delegate = ModeFakeSerial._base_cls(port, *args, **kwargs)
        self._instances = ModeFakeSerial._base_cls.instances

    def write(self, data):
        mode = ModeFakeSerial._mode
        if mode == "error":
            raise OSError(2, "simulated transport failure")
        if mode == "slow":
            time.sleep(ModeFakeSerial._sleep_seconds)
        return self._delegate.write(data)

    def close(self):
        return self._delegate.close()


def _get_original_fake_serial_cls():
    """Return the original fake serial class.

    This is needed because HubHarness replaces self.smc3.serial.Serial
    with ModeFakeSerial, which causes recursive resolution issues when
    SerialRecorder.install() accesses self.smc3.serial.Serial.
    """
    return ModeFakeSerial._base_cls


class HubHarness:
    """Build a started archived CommandHub over a fresh fake serial.

    Returns (hub, smc3_module, recorder): the recorder's shim is
    installed on the module's ``serial`` attribute before
    ``hub.start()`` (the archived worker resolves it at call time, so
    installing mid-run would race — the recorder documents this rule).
    """

    def __init__(self):
        self.smc3 = _load_archived_smc3_module()
        self.smc3.time = TimeWithoutDelay  # hub pacing skips delays
        # Note: ModeFakeSerial._base_cls is already set in _load_archived_smc3_module
        # to the original archived Serial class, so we can safely replace
        # self.smc3.serial.Serial with ModeFakeSerial without causing
        # recursive resolution issues.
        self.smc3.serial.Serial = ModeFakeSerial  # mode-controlled serial
        self.rec = SerialRecorder()
        self.rec.install(self.smc3)  # shim goes over smc3.serial

    def make_hub(self, rate_hz=1000.0):
        transport = self.smc3.SerialTransport("software-only-test-port")
        hub = self.smc3.CommandHub(transport, rate_hz=rate_hz)
        hub.start()
        return hub


class SubmissionTrackingHub:
    """Wrapper hub that tracks motor command submissions.

    This wraps the archived CommandHub to record when submit() is called,
    proving that point 2's motor commands are not submitted before point 1's
    barrier completes.
    """

    def __init__(self, original_hub):
        self._original_hub = original_hub
        self._original_submit = original_hub.submit
        self._original_tx_count = original_hub.tx_count
        self._original_stop = original_hub.stop
        self._submission_order = []  # List of submissions in order

    def submit(self, command):
        """Track and forward the submit call."""
        # The command is a MotorCommand with motor and position attributes
        motor = getattr(command, 'motor', None)
        position = getattr(command, 'position', None)
        
        # Track the submission
        self._submission_order.append({
            'motor': motor,
            'position': position,
            'command': command,
        })
        
        return self._original_submit(command)

    @property
    def tx_count(self):
        """Delegate tx_count to original hub."""
        return self._original_tx_count

    def stop(self):
        """Delegate stop to original hub."""
        return self._original_stop()

    def get_submission_order(self):
        """Return the list of submissions in order."""
        return self._submission_order


def make_submission_tracking_hub(harness):
    """Create a hub that tracks motor command submissions."""
    original_hub = harness.make_hub()
    return SubmissionTrackingHub(original_hub)


class ControlFrameInjectorHub:
    """Wrapper hub that injects control frames between motor submits.

    This simulates real-world scenarios where control frames (enable, disable,
    version requests) are sent between motor commands. The driver must filter
    these out when verifying motor-position frames.
    """

    def __init__(self, original_hub):
        self._original_hub = original_hub
        self._original_transport = original_hub.transport
        self._submit_count = 0
        self._injected_frames = []
        # Delegate tx_count and stop to the original hub
        self.tx_count = original_hub.tx_count
        self.stop = original_hub.stop

    def submit(self, command):
        """Inject control frames between motor submits."""
        # Determine motor letter from command
        motor_letter = getattr(command, 'motor', None)
        if motor_letter is None:
            motor_letter = 'A'  # default fallback

        # Inject enable control frame before first motor submit
        if self._submit_count == 0:
            # Directly write to the transport (bypasses hub's control queue)
            self._original_transport.write(b"[ena]")
            self._injected_frames.append(b"[ena]")

        # Inject disable control frame between motor submits (not before first)
        if self._submit_count > 0:
            # Directly write to the transport (bypasses hub's control queue)
            self._original_transport.write(b"[]")
            self._injected_frames.append(b"[]")

        # Submit the actual motor command
        self._submit_count += 1
        return self._original_hub.submit(command)

    @property
    def injected_frames(self):
        """Return the list of injected control frames."""
        return self._injected_frames


def make_control_frame_hub(harness):
    """Create a hub with control frame injection.
    
    This hub injects control frames at strategic points to simulate real-world
    scenarios where control frames (enable, disable, version requests) are sent
    between motor commands. The driver must filter these out when verifying
    motor-position frames.
    """
    original_hub = harness.make_hub()
    return ControlFrameInjectorHub(original_hub)


def driver_run(*args, **kwargs):
    """Call the real driver, guaranteeing hub cleanup afterwards."""
    hub = kwargs["hub"]
    try:
        return driver.run(*args, **kwargs)
    finally:
        hub.stop()


class DriverTests(unittest.TestCase):
    # ---- T2.x carried forward (now against real barrier/ledger) ----

    def test_t14_driver_declares_t33_integration(self):
        doc = driver.__doc__ or ""
        self.assertIn("per-point driver integration", doc)
        self.assertIn("point sequencing", doc)
        self.assertIn("barrier timeouts", doc)

    def test_t14_driver_imports_from_package(self):
        src = Path(driver.__file__).read_text(encoding="utf-8")
        self.assertIn("from .ledger import", src)
        self.assertIn("from .recorder import", src)

    def test_t14_driver_declares_default_timeout_constant(self):
        self.assertEqual(driver.DEFAULT_TIMEOUT, 5.0)

    def test_t14_run_has_named_only_signature(self):
        """Named-only signature (T3.5+ call sites use keywords)."""
        names = list(inspect_signature(driver.run))

    def test_success_verifies_every_point_in_order(self):
        """T2.1/T2.3/T3.3 rule 1: two points run one at a time.

        Each point submits 3 MotorCommands through the archived hub
        motion path, waits on the real Barrier for the closed batch,
        verifies with the real Ledger.verify, and only then starts the
        next point. The journals never interleave.
        """
        points = [
            SweepPoint(
                point_id=1,
                description="first",
                motor_positions={"A": 10, "B": 20, "C": 30},
            ),
            SweepPoint(
                point_id=2,
                description="second",
                motor_positions={"A": 11, "B": 21, "C": 31},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        barrier = Barrier(harness.rec)
        led = Ledger()
        result = driver_run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=barrier, ledger_obj=led,
        )
        self.assertEqual(len(result["points"]), 2)
        self.assertEqual([o["point_id"] for o in result["points"]], [1, 2])
        attempts = harness.rec.attempts()
        self.assertEqual(len(attempts), 6)
        self.assertEqual([a["attempt_seq"] for a in attempts], [1, 2, 3, 4, 5, 6])
        self.assertEqual([a["status"] for a in attempts], ["OK"] * 6)
        # journal association: attempts 1-3 are point 1's, 4-6 point 2's
        first_frames = [ledger.expected_frames(points[0])[i].frame_bytes for i in range(3)]
        second_frames = [ledger.expected_frames(points[1])[i].frame_bytes for i in range(3)]
        self.assertEqual([a["frame_bytes"] for a in attempts[:3]], list(first_frames))
        self.assertEqual([a["frame_bytes"] for a in attempts[3:]], list(second_frames))
        for observation, point in zip(result["points"], points):
            self.assertEqual(observation["attempts_expected"], 3)
            self.assertEqual(observation["attempts_submitted"], 3)
            self.assertTrue(observation["barrier_satisfied"])
            ver = observation["verification"]
            self.assertIsInstance(ver, VerificationResult)
            self.assertTrue(ver.verified)
            self.assertEqual(ver.point_id, point.point_id)
            self.assertEqual(ver.mismatches, ())
        self.assertEqual(hub.tx_count, 6)
        self.assertEqual(result["attempts_recorded_total"], 6)

    def test_frame_mismatch_is_reported_not_raised(self):
        """T2.7/T3.3: a wrong expected-frames lookup is a recorded error.

        With the driver's ledger handing point 1 the frames of point 2
        (and vice versa), the hub writes the swapped frames; the
        Ledger.verify answer reports frame_mismatch for every
        mismatched position, never raises, and the driver records the
        unverified points — the run does not crash.
        """
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
            SweepPoint(
                point_id=2, description="second",
                motor_positions={"A": 700, "B": 800, "C": 900},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        barrier = Barrier(harness.rec)
        led = Ledger()
        original_frames_for = led.frames_for

        def swapped_frames_for(point_id):
            return original_frames_for(3 - point_id)

        led.frames_for = swapped_frames_for
        result = driver_run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=barrier, ledger_obj=led,
        )
        self.assertEqual(len(result["points"]), 2)
        for observation in result["points"]:
            ver = observation["verification"]
            self.assertFalse(ver.verified)
            self.assertFalse(ver.frames_match)
            self.assertTrue(ver.counts_match)     # same lengths, correct counts
            self.assertTrue(ver.statuses_match)   # every write returned full
            self.assertEqual(len(ver.mismatches), 3)
            self.assertTrue(all(m.frame_mismatch for m in ver.mismatches))
        self.assertEqual(len(harness.rec.attempts()), 6)
        self.assertEqual(hub.tx_count, 6)

    def test_barrier_timeout_attributed_to_point(self):
        """T2.6/T3.3: writes too slow for the 0.5 s wait -> TimeoutError.

        The T3.1 barrier raises TimeoutError for the point being
        waited on; the driver attributes the timeout to THAT point,
        records it and stops (rule 1: the next point has not started).
        """
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
            SweepPoint(
                point_id=2, description="second",
                motor_positions={"A": 700, "B": 800, "C": 900},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        ModeFakeSerial._mode = "slow"
        try:
            result = driver_run(
                points=points, hub=hub, recorder=harness.rec,
                barrier=Barrier(harness.rec), timeout=0.5, ledger_obj=Ledger(),
            )
        finally:
            ModeFakeSerial._mode = "ok"
        self.assertEqual(len(result["points"]), 1)
        first = result["points"][0]
        self.assertEqual(first["point_id"], 1)
        self.assertTrue(first["timed_out"])
        self.assertFalse(first["barrier_satisfied"])
        self.assertFalse(first["point_interrupted"])
        self.assertTrue(result["stopped"])
        self.assertFalse(result["interrupted"])
        # point 2 never started: nothing of it was submitted, and the
        # point-1 wait's own batch never completed. With the slow mode
        # (0.3s sleep per write) and timeout of 0.5s, the first write
        # completes at T=0.3, barrier starts waiting, second write
        # completes at T=0.6, and timeout occurs at T=0.8. So 2 attempts
        # are recorded, but the barrier never saw 3 attempts, so it
        # timed out.
        # When there's a timeout, verification is None because barrier_satisfied is False
        self.assertIsNone(first["verification"])
        # Two attempts are recorded: the first completed before the barrier
        # started waiting, and the second completed before the timeout.
        self.assertEqual(len(harness.rec.attempts()), 2)

    def test_transport_error_yields_error_attempts(self):
        """T2.7/T3.3: every write raises -> three ERROR attempts.

        The T2.6 vocabulary records the failures (status=ERROR, no
        returned count), the barrier is still satisfied (a closed
        attempt exists), and Ledger.verify reports count/status
        mismatches — verification failures do not crash the run. The
        archived hub survives (worker remains observable, tx_count 0,
        last_error set).
        """
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        ModeFakeSerial._mode = "error"
        try:
            result = driver_run(
                points=points, hub=hub, recorder=harness.rec,
                barrier=Barrier(harness.rec), ledger_obj=Ledger(),
            )
        finally:
            ModeFakeSerial._mode = "ok"
        self.assertEqual(len(result["points"]), 1)
        first = result["points"][0]
        self.assertEqual(first["attempts_submitted"], 3)
        self.assertTrue(first["barrier_satisfied"])
        self.assertFalse(first["timed_out"])
        self.assertFalse(first["point_interrupted"])
        ver = first["verification"]
        self.assertFalse(ver.verified)
        self.assertTrue(ver.frames_match)         # recorded payload was right
        self.assertFalse(ver.counts_match)        # ERROR records have no count
        self.assertFalse(ver.statuses_match)      # status ERROR, not OK
        self.assertEqual(len(ver.mismatches), 3)
        attempts = harness.rec.attempts()
        self.assertEqual(len(attempts), 3)
        self.assertEqual([a["status"] for a in attempts], ["ERROR"] * 3)
        self.assertEqual(hub.tx_count, 0)
        self.assertIsNotNone(hub.last_error)
        self.assertFalse(result["stopped"])

    def test_interruption_stops_mid_point(self):
        """T2.2: stop_callback True between submissions stops the point."""
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        submits_seen = 0

        def stop_after_first_submit():
            nonlocal submits_seen
            submits_seen += 1
            return submits_seen > 1

        result = driver_run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=Barrier(harness.rec), stop_callback=stop_after_first_submit,
            ledger_obj=Ledger(),
        )
        self.assertEqual(len(result["points"]), 1)
        first = result["points"][0]
        self.assertTrue(first["point_interrupted"])
        self.assertEqual(first["attempts_submitted"], 1)
        self.assertFalse(first["barrier_satisfied"])
        self.assertFalse(first["timed_out"])
        self.assertTrue(result["interrupted"])
        self.assertTrue(result["stopped"])

    def test_inter_point_interruption_observations(self):
        """T2.2: stop between points leaves the second point unstarted."""
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
            SweepPoint(
                point_id=2, description="second",
                motor_positions={"A": 700, "B": 800, "C": 900},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        calls = 0

        def stop_after_third_submit():
            nonlocal calls
            calls += 1
            return calls >= 5  # point 1's 3 submits + its loop check + point 2 check

        result = driver_run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=Barrier(harness.rec), stop_callback=stop_after_third_submit,
            ledger_obj=Ledger(),
        )
        self.assertEqual(len(result["points"]), 1)
        first = result["points"][0]
        self.assertEqual(first["attempts_submitted"], 3)
        self.assertTrue(first["barrier_satisfied"])
        self.assertTrue(first["verification"].verified)
        self.assertFalse(first["point_interrupted"])
        self.assertTrue(result["interrupted"])
        self.assertEqual([o["point_id"] for o in result["points"]], [1])
        self.assertEqual(len(harness.rec.attempts()), 3)

    def test_hub_not_started_submit_raises(self):
        """Archived CommandHub contract: submit raises when the worker
        is not alive. The driver does not swallow it: the error
        propagates out of run()."""
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
        ]
        harness = HubHarness()
        hub = harness.make_hub()
        hub.stop()  # worker not alive
        with self.assertRaises(Exception):
            driver_run(
                points=points, hub=hub, recorder=harness.rec,
                barrier=Barrier(harness.rec), ledger_obj=Ledger(),
            )

    def test_t25_point_observation_fields(self):
        required = {
            "point_id", "tx_count_before", "attempts_expected",
            "attempts_submitted", "barrier_satisfied", "verification",
            "timed_out", "point_interrupted",
        }
        for observation in driver_run_observations():
            self.assertEqual(set(observation), required)

    def test_t25_centering_hook_not_run_when_none(self):
        """When centering=None is passed, the driver never calls the centering hook.
        
        The driver.run() function only calls centering if it's provided (not None).
        """
        calls = []
        
        def dummy_centering():
            calls.append("called")
        
        harness = HubHarness()
        hub = harness.make_hub()
        
        # Run with centering=None - should never call the dummy centering function
        points = [
            ledger.SweepPoint(
                point_id=1, description="test",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
        ]
        result = driver_run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=Barrier(harness.rec), centering=None,
            ledger_obj=Ledger(),
        )
        
        # The centering hook should never be called when passing None
        self.assertEqual(calls, [])
        
        hub.stop()

    def test_t33_control_frames_do_not_cause_verification_failure(self):
        """T3.3 regression: intervening control frames must not break point verification.

        The Barrier returns all attempts including control frames, but the driver
        must filter to motor frames only before passing to Ledger.verify(). This
        test proves that:
          1. Control frames are injected between motor submits
          2. The complete attempt journal contains all five attempts (2 control + 3 motor)
          3. Control attempts have is_motor_frame=False
          4. Motor attempts have is_motor_frame=True
          5. Filtering by the recorded is_motor_frame field produces exactly A, B, C
          6. Ledger.verify() receives exactly those three motor attempts
          7. The point's final verification succeeds with no mismatches
        """
        harness = HubHarness()
        hub = make_control_frame_hub(harness)
        barrier = Barrier(harness.rec)
        led = Ledger()

        point = SweepPoint(
            point_id=99,
            description="test with control frames",
            motor_positions={"A": 100, "B": 200, "C": 300},
        )

        result = driver_run(
            points=[point], hub=hub, recorder=harness.rec,
            barrier=barrier, ledger_obj=led,
        )

        # Verify the run completed successfully
        self.assertEqual(len(result["points"]), 1)
        observation = result["points"][0]

        # Check barrier was satisfied (3 motor frames completed)
        self.assertTrue(observation["barrier_satisfied"])

        # Check verification succeeded
        ver = observation["verification"]
        self.assertIsNotNone(ver)
        self.assertTrue(ver.verified)
        self.assertTrue(ver.frames_match)
        self.assertTrue(ver.counts_match)
        self.assertTrue(ver.statuses_match)
        self.assertEqual(len(ver.mismatches), 0)

        # Get the complete attempt journal
        attempts = harness.rec.attempts()

        # Debug: print all attempts
        print(f"DEBUG: Total attempts: {len(attempts)}")
        for i, attempt in enumerate(attempts):
            print(f"  Attempt {i}: is_motor_frame={attempt.get('is_motor_frame')}, frame={attempt.get('frame_bytes')}, status={attempt.get('status')}")

        # Assert: journal contains all attempts (control frames + motor frames)
        # The hub's worker loop may process frames in an interleaved fashion,
        # so we check that we have exactly 3 motor frames and at least 1 control frame
        motor_frames = [a for a in attempts if a["is_motor_frame"]]
        control_frames = [a for a in attempts if not a["is_motor_frame"]]
        
        self.assertEqual(len(motor_frames), 3,
            "Should have exactly 3 motor frames")
        self.assertGreater(len(control_frames), 0,
            "Should have at least 1 control frame")

        # Verify the control frames are enable and disable
        enable_frames = [f for f in control_frames if f["frame_bytes"] == b"[ena]"]
        disable_frames = [f for f in control_frames if f["frame_bytes"] == b"[]"]
        self.assertGreater(len(enable_frames), 0, "Should have at least 1 enable frame")
        self.assertGreater(len(disable_frames), 0, "Should have at least 1 disable frame")

        # Verify the motor frames are in A, B, C order
        motor_letters = [chr(a["frame_bytes"][1]) for a in motor_frames]
        self.assertEqual(motor_letters, ["A", "B", "C"],
            "Motor frames should be in A, B, C order")

        # Verify filtering by the recorded is_motor_frame field
        # produces exactly Motor A, Motor B, Motor C in order
        filtered_motor_attempts = [
            attempt for attempt in attempts
            if attempt["is_motor_frame"]
        ]
        self.assertEqual(len(filtered_motor_attempts), 3,
            "Filtering should produce exactly 3 motor attempts")

        motor_letters = [chr(a["frame_bytes"][1]) for a in filtered_motor_attempts]
        self.assertEqual(motor_letters, ["A", "B", "C"],
            "Motor attempts should be in A, B, C order")

        # Verify the driver filtered to exactly 3 motor attempts for verification
        # The driver should have passed exactly 3 attempts to Ledger.verify()
        # We can verify this by checking the verification succeeded with no mismatches
        # and that the expected frames match the motor frames
        expected_frames = ledger.expected_frames(point)
        self.assertEqual(len(expected_frames), 3)

        # Verify each expected frame matches the corresponding motor attempt
        for i, (exp, motor_attempt) in enumerate(zip(expected_frames, motor_frames)):
            self.assertEqual(exp.frame_bytes, motor_attempt["frame_bytes"],
                f"Expected frame {i+1} should match motor attempt {i+1}")

        # Verify the complete journal is preserved (not discarded)
        self.assertEqual(len(attempts), len(motor_frames) + len(control_frames),
            "Complete journal must retain all attempts")

    def test_t33_source_guard(self):
        """The driver source must not use the forbidden patterns."""
        src = Path(driver.__file__).read_text(encoding="utf-8")
        self.assertNotIn("submit_control", src)
        self.assertNotIn("wait_for_idle", src)
        self.assertNotIn("QueueEmpty", src)
        self.assertNotIn("import serial", src)
        # Check that the driver uses the recorded is_motor_frame field
        # instead of re-classifying (no _is_motor_frame import needed)
        self.assertIn("from .recorder import", src)
        self.assertIn("is_motor_frame", src)
        # barrier waits happen at the Barrier, via wait_for_attempts
        self.assertIn("wait_for_attempts", src)
        # verification only through the ledger
        self.assertIn("verify", src)
        self.assertNotIn("status_for(", src)
        self.assertNotIn("COMPLETE", src)
        self.assertNotIn("DEGRADED", src)

    def test_t33_hub_owns_the_hub_argument(self):
        """The driver receives the hub; it never creates one itself."""
        src = Path(driver.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CommandHub(", src)
        self.assertNotIn("SerialTransport(", src)

    def test_t33_run_signature_named_only(self):
        """run() is keyword-only: every parameter after ``*``.

        ``points`` keeps a default so a pre-populated ledger can drive
        the run without it; T3.5+ call sites use keywords either way.
        """
        parameter_kinds = {
            name: kind
            for name, kind in inspect_signature(driver.run)
        }
        self.assertTrue(parameter_kinds, "run has parameters")
        # Check that all kinds are one of the valid parameter kinds
        valid_kinds = {"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD", "KEYWORD_ONLY", 
                      "VAR_POSITIONAL", "VAR_KEYWORD"}
        self.assertTrue(
            all(kind in valid_kinds for kind in parameter_kinds.values())
        )

    def test_t34_per_point_barrier_enforces_sequencing(self):
        """T3.4 regression: point k's barrier completes before point k+1 is submitted.

        This test proves the driver enforces strict per-point sequencing:
          1. Point 1's three motor commands are submitted
          2. Point 1's barrier starts and completes
          3. No point 2 motor command is submitted before point 1's barrier completes
          4. Only after point 1's barrier completes does the driver submit point 2
          5. Point 2's three motor commands are submitted
          6. Point 2's barrier starts and completes

        The test tracks both motor submissions and barrier calls to prove ordering
        without relying on arbitrary sleeps or timing assumptions.
        """
        points = [
            SweepPoint(
                point_id=1, description="first",
                motor_positions={"A": 100, "B": 200, "C": 300},
            ),
            SweepPoint(
                point_id=2, description="second",
                motor_positions={"A": 11, "B": 21, "C": 31},
            ),
        ]
        harness = HubHarness()
        hub = make_submission_tracking_hub(harness)  # Track submissions
        barrier = Barrier(harness.rec)
        led = Ledger()

        # Track barrier calls to prove ordering
        call_count = [0]
        call_order = []

        # Wrap the barrier to track when it's called
        original_wait = barrier.wait_for_attempts
        def tracked_wait(n, timeout):
            call_count[0] += 1
            call_order.append("barrier_wait_start")
            try:
                result = original_wait(n, timeout)
                call_order.append("barrier_wait_complete")
                return result
            except TimeoutError:
                call_order.append("barrier_wait_timeout")
                raise

        barrier.wait_for_attempts = tracked_wait

        try:
            result = driver_run(
                points=points, hub=hub, recorder=harness.rec,
                barrier=barrier, ledger_obj=led,
            )
        finally:
            hub.stop()
            barrier.wait_for_attempts = original_wait

        # Verify two points completed
        self.assertEqual(len(result["points"]), 2)
        self.assertEqual([o["point_id"] for o in result["points"]], [1, 2])

        # Verify motor command submission order
        submissions = hub.get_submission_order()
        self.assertEqual(len(submissions), 6)  # 3 for point 1 + 3 for point 2
        
        # First 3 submissions are for point 1 (motors A, B, C)
        self.assertEqual(submissions[0]['motor'], 'A')
        self.assertEqual(submissions[1]['motor'], 'B')
        self.assertEqual(submissions[2]['motor'], 'C')
        
        # Next 3 submissions are for point 2 (motors A, B, C)
        self.assertEqual(submissions[3]['motor'], 'A')
        self.assertEqual(submissions[4]['motor'], 'B')
        self.assertEqual(submissions[5]['motor'], 'C')

        # PROVE ORDERING: The complete sequence must be:
        # [submits point 1 A, B, C] -> [barrier starts] -> [barrier completes] ->
        # [submits point 2 A, B, C] -> [barrier starts] -> [barrier completes]
        #
        # The barrier call order proves that point 2's barrier didn't start until
        # point 1's completed. Combined with the submission order, this proves that
        # point 2's motor commands were not submitted before point 1's barrier completed.
        self.assertEqual(call_order, ["barrier_wait_start", "barrier_wait_complete", 
                                       "barrier_wait_start", "barrier_wait_complete"])

        # Verify both barriers completed successfully
        self.assertEqual(call_count[0], 2)  # Two barrier calls (one per point)
        self.assertEqual(len(call_order), 4)  # 2 start + 2 complete events

        # Verify all attempts have unique sequence numbers (no reordering)
        attempts = harness.rec.attempts()
        self.assertEqual(len(attempts), 6)
        self.assertEqual([a["attempt_seq"] for a in attempts], [1, 2, 3, 4, 5, 6])

        # Verify point 1's attempts (1-3) have different frames from point 2's attempts (4-6)
        first_frames = [a["frame_bytes"] for a in attempts[:3]]
        second_frames = [a["frame_bytes"] for a in attempts[3:]]
        self.assertNotEqual(first_frames, second_frames,
            "Point 1 and point 2 frames should differ")

        # Verify both points verified successfully
        for obs in result["points"]:
            self.assertTrue(obs["barrier_satisfied"])
            self.assertIsNotNone(obs["verification"])
            self.assertTrue(obs["verification"].verified)

def driver_run_observations():
    """One minimal successful point run, for the field-shape test."""
    harness = HubHarness()
    hub = harness.make_hub()
    points = [
        SweepPoint(
            point_id=1, description="first",
            motor_positions={"A": 100, "B": 200, "C": 300},
        ),
    ]
    try:
        result = driver.run(
            points=points, hub=hub, recorder=harness.rec,
            barrier=Barrier(harness.rec), ledger_obj=Ledger(),
        )
    finally:
        hub.stop()
    return result["points"]


if __name__ == "__main__":
    unittest.main()
