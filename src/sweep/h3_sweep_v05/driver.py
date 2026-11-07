"""H3 sweep driver — sweep execution, point sequencing, barriers,
interruption, centering, and run status.

This is the T3.3 per-point driver integration on top of the T3.1
barrier and the T3.2 ledger verification layer:

    for each registered point, in ledger order:
      1. snapshot the recorder attempt_seq and the hub tx_count,
      2. take the point's expected frames from the ledger (the
         archived encoder produced them at registration time),
      3. submit one MotorCommand per expected frame through the
         CommandHub motion path (hub.submit),
      4. wait at the barrier for the three closed attempts,
      5. verify the point against exactly the attempts this point
         produced (Ledger.verify), and only then advance to the
         next point.

The driver never classifies the overall run: T3.3 records per-point
facts (barrier satisfaction, submitted count, and the VerificationResult
the ledger returned). The run status vocabulary and its rules are task
T3.7; they are not implemented here. A barrier timeout is a software
TimeoutError raised by the T3.1 barrier — the driver attributes it to
the point being waited on and stops, recording the point as not
satisfied.

T2.x contract carried forward (tests/test_driver.py now runs the same
checks against the real barrier/ledger/recorder instead of stubs):
    T2.1 one point at a time; the next starts only after verify.
    T2.2 interruption: stop_callback stops between points/submissions.
    T2.3 point order exactly ledger.known_points() order.
    T2.4 centering hook: run() calls a centering callable only when
         given one; submitting the centering sequence is T3.4+.
    T2.5 per-point observation dicts, one per executed point.
    T2.6 barrier timeouts attributed to the point being waited on.
    T2.7 verification results come only from Ledger.verify.
    T2.8 point/attempt association: snapshot attempt_seq before the
         point and verify the batch returned by the barrier after
         the barrier completes.

The hub must be a started archived CommandHub (the caller starts it;
hub.submit raises CommandHubError when the worker is not alive). The
recorder must be the SerialRecorder the hub's SerialTransport writes
were installed onto, and the barrier watches that recorder.
"""
from __future__ import annotations

from .classifier import classify_point
from .ledger import Ledger, LedgerError, MotorCommand
from .recorder import Barrier, AttemptBatch

ATTEMPTS_PER_POINT = 3
DEFAULT_TIMEOUT = 5.0
DEFAULT_RATE_HZ = 20.0

__all__ = ["run", "ATTEMPTS_PER_POINT", "DEFAULT_TIMEOUT", "DEFAULT_RATE_HZ"]


def run(
    *,
    points=None,
    hub,
    recorder,
    barrier: Barrier,
    timeout: float = DEFAULT_TIMEOUT,
    rate_hz: float = DEFAULT_RATE_HZ,
    centering=None,
    stop_callback=None,
    ledger_obj=None,
):
    """Execute the points one at a time (T2.1, T3.3).

    Args:
        points: sequence of SweepPoint; registered with a fresh Ledger
            when ledger_obj is None (invalid configs raise LedgerError).
        hub: started archived CommandHub; submissions go through its
            motion path via hub.submit(MotorCommand(motor, position)).
        recorder: the SerialRecorder the hub writes are recorded into
            (attempt counts snapshot the point association, T2.8).
        barrier: Barrier watching that recorder (T3.1).
        timeout: per-point barrier timeout in seconds.
        rate_hz: reserved for T3.9 pacing; not applied yet.
        centering: optional callable run once before the first point
            (T2.4); submitting the centering sequence is T3.4+.
        stop_callback: optional callable checked between points and
            between submissions (T2.2).
        ledger_obj: pre-populated Ledger; its known_points() order then
            drives the run and points is ignored.

    Returns a dict of run-level facts (no run-status classification —
    that vocabulary is T3.7):
        points: one observation dict per executed point (T2.5) with
            point_id, tx_count_before, attempts_expected,
            attempts_submitted, barrier_satisfied, verification (the
            VerificationResult or None), timed_out and
            point_interrupted.
        interrupted / stopped: interruption and timeout facts (T2.2).
        attempts_recorded_total: closed attempts this run recorded.
    """
    if ledger_obj is None:
        ledger_obj = Ledger()
    # Always register points into the ledger, whether it's pre-created
    # or new. This ensures known_points() returns the correct points.
    for point in points or ():
        ledger_obj.register_point(point)
    # ``Ledger.known_points()`` hands back the registered SweepPoint
    # objects in point-id order; the driver visits their ids (rule 1 of
    # the acceptance: registered order, one point at a time).
    known = [point.point_id for point in ledger_obj.known_points()]

    if centering is not None:
        centering()

    results = []
    interrupted = False
    # T3.3 step 1: snapshot the recorder's last attempt_seq before
    # the first point, so per-point associations use the delta from
    # that snapshot.
    run_start_seq = recorder.attempts()[-1]["attempt_seq"] if recorder.attempts() else 0

    for point_id in known:
        if stop_callback is not None and stop_callback():
            interrupted = True
            break

        # T3.3 step 1: snapshot attempt_seq and tx_count before this
        # point's submissions. The barrier will wait for exactly three
        # new attempts after this snapshot.
        seq_before = recorder.attempts()[-1]["attempt_seq"] if recorder.attempts() else 0
        tx_before = hub.tx_count
        expected = ledger_obj.frames_for(point_id)

        submitted = 0
        for exp in expected:
            hub.submit(MotorCommand(exp.motor, exp.position))
            submitted += 1
            if stop_callback is not None and stop_callback():
                interrupted = True
                break

        barrier_satisfied = False
        if not interrupted:
            try:
                # T3.3 step 4: wait for the barrier to return the batch
                # of closed attempts. The barrier returns the AttemptBatch
                # directly, so we retain it for verification.
                batch = barrier.wait_for_attempts(ATTEMPTS_PER_POINT, timeout)
                barrier_satisfied = True
            except TimeoutError:
                pass

        # T3.3 step 5: filter to motor frames only (control frames are
        # recorded in the journal but must not count toward verification),
        # then verify against the point's expected frames.
        verification = None
        classification = None
        if barrier_satisfied:
            # Filter the batch to only motor-position frames using the
            # recorder's classification (is_motor_frame field).
            # Do not re-classify; the recorder already set this field.
            motor_batch = [
                attempt for attempt in batch
                if attempt["is_motor_frame"]
            ]
            verification = ledger_obj.verify(point_id, motor_batch)
            # Classify the point based on verification and attempt data
            classification = classify_point(
                verification_result=verification,
                tx_count_before=tx_before,
                barrier_timed_out=False,
                attempts=batch,
            )
            # Call classify() to set the status before accessing properties
            if classification:
                classification.classify()

        # T3.7: add classification info to results
        results.append(
            {
                "point_id": point_id,
                "tx_count_before": tx_before,
                "attempts_expected": len(expected),
                "attempts_submitted": submitted,
                "barrier_satisfied": barrier_satisfied,
                "verification": verification,
                "classification": classification.status if classification else None,
                "classification_reason": classification.reason if classification else None,
                "timed_out": not barrier_satisfied and not interrupted,
                "point_interrupted": interrupted,
            }
        )

        if interrupted or not barrier_satisfied:
            break

    stopped = interrupted or any(r["timed_out"] for r in results)
    return {
        "points": results,
        "interrupted": interrupted,
        "stopped": stopped,
        "attempts_recorded_total": len(recorder.attempts()) - run_start_seq,
    }
