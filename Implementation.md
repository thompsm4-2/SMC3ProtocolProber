# QWEN IMPLEMENTATION PROMPT
# DOF Reality H3 — v0.5 Sweep Driver and Reliable Serial Recording

## 1. Objective

Implement **v0.5 of the Linux DOF Reality H3 calibration/sweep system** in the existing `Linux_DOF_Reality_H3_Engineering_Handoff_v1.1` repository.

The purpose of v0.5 is to establish a reliable, auditable motor-command transmission system using the previously working v0.3.5.1 CommandHub architecture.

The implementation must provide:

- Reliable transmission of all three motor commands for every sweep point.
- Recording of every serial write attempt, including short writes and exceptions.
- A completion barrier that verifies actual write attempts rather than relying on queue state or `tx_count`.
- Exact association between transmitted frames and their intended sweep points.
- Safe, explicitly reported shutdown and interruption behavior.
- A distinction between requested centering and confirmed center-command transmission.
- CSV compatibility with the existing v0.4.1 analysis workflow.
- Structured JSONL event logging.
- Comprehensive software-only testing before any hardware is connected.

This is an implementation task, not another architecture research exercise. Read the existing project instructions and source files, implement the agreed design, and report any genuine blockers.

---

## 2. Mandatory project rules

Before making changes, read:

1. `AGENTS.md`
2. `QWEN_INSTRUCTIONS.md`
3. `README.md`
4. `docs/SOFTWARE_ARCHITECTURE.md`
5. `docs/VERSION_HISTORY.md`
6. `docs/TESTING_AND_CALIBRATION.md`
7. `docs/HARDWARE_REFERENCE.md`
8. `reports/SOURCE_LOG_PROVENANCE.md`
9. `reports/V0.4.1_MOTOR_C_ANALYSIS.md`

Inspect the actual repository structure before creating files. Do not assume that paths in this prompt exactly match the current checkout if the repository has changed.

### Preservation requirements

- Do not modify, rename, or delete the archived v0.3.5.1 source.
- Do not modify, rename, or delete the historical v0.4.1 calibration source.
- Do not modify or delete existing raw capture data.
- Do not overwrite historical analysis results.
- Do not modify SMC3 firmware.
- Do not reorganize unrelated project directories.
- Keep `protocol-analyzer` flat if it is referenced or used.
- Do not silently change existing CSV column names or meanings.
- Do not introduce hardware-dependent tests into the software-only test suite.
- Do not claim that physical hardware has been tested.

The existing v0.3.5.1 CommandHub is the baseline. Use it as-is. Any new behavior must be implemented in the new v0.5 package.

If a required baseline file is missing, report that fact instead of recreating or approximating it.

---

## 3. New package structure

Create the new implementation under:

```text
src/
└── sweep/
    └── h3_sweep_v05/
        ├── __init__.py
        ├── driver.py
        ├── recorder.py
        ├── ledger.py
        ├── eventslog.py
        └── csvlog.py
```

Add tests in the project's existing test organization, following its conventions.

Responsibilities:

| Module | Responsibility |
|---|---|
| `driver.py` | Sweep execution, point sequencing, barriers, interruption, centering, run status |
| `recorder.py` | Serial proxy, write-attempt records, attempt synchronization, write status |
| `ledger.py` | Expected motor frames, point association, exact frame verification |
| `eventslog.py` | Structured timestamped JSONL events |
| `csvlog.py` | v0.4.1-compatible TX CSV and compatible sensor CSV handling |

Keep the modules independently testable. Avoid circular imports and unnecessary dependencies.

The new package must not modify the archived CommandHub implementation.

---

## 4. CommandHub integration

Use the archived v0.3.5.1 implementation of `smc3.py`.

Relevant existing interfaces include:

```python
CommandHub(transport, rate_hz=30.0, debug=False, event=None)
MotorCommand(motor, position)
SMC3Transport(...)
```

The existing CommandHub has these important characteristics:

- One worker thread owns serial writes.
- The motion queue keeps the latest value per motor.
- Commands for the same motor can be coalesced.
- The normal rate is 30 Hz.
- `wait_for_idle()` is not a reliable write-completion barrier.
- `tx_count` increments after `transport.write()` returns.
- The existing serial transport discards the byte count returned by `serial.write()`.
- The worker catches write exceptions and continues.
- `stop()` joins for one second and then closes the transport, even if the worker remains alive.

Do not change these behaviors in the archived source.

### Ordinary motor commands

All ordinary motor-position commands must use:

```python
MotorCommand(motor, position)
```

and the CommandHub motion submission path.

Do not use `submit_control()` for ordinary motor-position commands.

Reserve the control queue for actual SMC3 control frames.

Do not submit the next sweep point until the current point has passed its write-attempt barrier.

This is essential because the motion queue uses latest-value-per-motor coalescing.

---

## 5. Serial write recorder

Implement the recorder using a serial-module injection mechanism.

### Required injection approach

The archived `smc3.py` calls:

```python
serial.Serial(...)
```

through its imported module attribute.

Use this established injection point:

```python
smc3.serial
```

Install a shim module before the CommandHub starts. Its `Serial` class must delegate to the real pyserial implementation while recording every write attempt.

Do not modify private `SerialTransport._serial` attributes.

Do not open a second serial connection.

Do not bypass the archived transport's write lock or lifecycle.

The shim must preserve the existing behavior of:

- Serial construction.
- Port opening.
- Baud-rate configuration.
- Read and write timeouts.
- The existing two-second Arduino reset delay.
- Serial writes.
- Serial closing.

The recorder must be scoped to one run. Restore the original `smc3.serial` module reference during cleanup, after the worker can no longer use the recorded serial object.

Document the module-level injection limitation. Do not claim it is thread-safe for concurrent independent runs.

### Required attempt record

Every write attempt must produce a record containing:

```text
attempt_seq
timestamp
monotonic_timestamp
frame_bytes
returned_count
expected_count
status
exception
```

Use a monotonically increasing sequence number.

Use monotonic time for ordering and elapsed-time measurements.

The recorder must be thread-safe.

### Attempt status

Classify every attempt as:

| Status | Meaning |
|---|---|
| `OK` | Write returned exactly the expected number of bytes |
| `SHORT` | Write returned fewer bytes than expected |
| `ERROR` | Write raised an exception |

For SMC3 frames, the expected length is five bytes.

If the underlying write raises an exception:

1. Record the attempt as `ERROR`.
2. Preserve the exception information.
3. Re-raise the original exception so the archived CommandHub sees the same failure it would have seen without the recorder.

Do not convert exceptions into successful returns.

If a write returns a short count, record `SHORT` even though the archived CommandHub may increment `tx_count`.

The recorder must not silently discard partial writes.

---

## 6. Write-attempt completion barrier

Implement a reliable barrier.

Suggested interface:

```python
Barrier.wait_for_attempts(
    expected: int,
    timeout: float
) -> AttemptBatch
```

The barrier must wait until the requested number of write attempts have reached terminal states (`OK`, `SHORT`, or `ERROR`).

It must not use `wait_for_idle()` as proof of transmission.

It must not rely on `tx_count` alone.

### Per-point execution

Each sweep point contains exactly three expected motor-position frames:

- Motor A
- Motor B
- Motor C

For each point:

1. Generate the expected frames using the archived command encoding.
2. Record the current attempt sequence and `tx_count`.
3. Submit the three `MotorCommand` objects through the CommandHub.
4. Wait for three new closed attempt records.
5. Compare the recorded frames against the expected ledger.
6. Verify the returned byte counts.
7. Verify all statuses.
8. Record the point result.
9. Only then proceed to the next point.

A point must not be considered successful merely because `tx_count` increased by three.

### Point classification

| Condition | Result |
|---|---|
| Three matching frames, all `OK`, tx_count delta = 3 | `COMPLETE` |
| Any short write | `DEGRADED` |
| Any write exception | `FAILED` |
| Barrier timeout | `FAILED` |
| Frame mismatch | `FAILED` |
| Unexpected motor or missing frame | `FAILED` |

A short write is a failure of the point even if `tx_count` increased by three.

The barrier must use a bounded timeout and must not hang indefinitely.

Include tests proving that the barrier correctly distinguishes a short write from a complete write.

---

## 7. Frame ledger and point attribution

Implement a driver-owned expected-frame ledger.

The ledger must:

- Generate expected frames using the archived `MotorCommand` or `encode_command` implementation.
- Preserve the exact motor order.
- Preserve the exact encoded bytes.
- Associate every attempt with the appropriate sweep point.
- Verify that actual recorded bytes match expected bytes.

The archived CommandHub has one serial-writing worker, so attempts are sequential.

The driver must enforce this sequencing:

**Point k must complete its three-attempt barrier before point k+1 is submitted.**

Do not infer point association from approximate timestamps alone.

Use the recorder's monotonically increasing sequence numbers and the driver's point expectation ledger.

Control frames must be classified separately and must not count toward a point's three motor-position frames.

A frame mismatch is a software error and must fail the point.

Do not import or execute the historical v0.4.1 source to perform classification. Implement the necessary classification in the new package using the documented protocol.

---

## 8. Shutdown and worker-lingering behavior

The archived CommandHub has a known shutdown limitation:

- `stop()` sets its stop event.
- It joins the worker with a one-second timeout.
- It closes the transport even if the worker remains alive.

This can create a close-during-write race.

The new implementation must explicitly detect and report this condition.

### Required shutdown procedure

1. Mark the run as shutting down.
2. Arm the recorder's shutdown/close-window tracking.
3. Call the archived hub shutdown method.
4. Check whether the worker remains alive.
5. If it remains alive, emit `WORKER_LINGERING`.
6. Record the current `tx_count`.
7. Classify any attempts occurring during or after shutdown separately from sweep-point attempts.
8. Do not submit additional motor commands.
9. Do not attempt return-to-center through a transport that may already be closing or closed.
10. Preserve the recorder and event data until no worker can access them.
11. Restore the original `smc3.serial` reference only when doing so cannot interfere with an active run.

Do not modify the archived `stop()` implementation.

### Post-close attempt handling

Every attempt must be classifiable as either:

- Associated with an active sweep point.
- A control/center attempt.
- A post-close or shutdown-overlap attempt.

A shutdown-overlap attempt must never be credited to a sweep point.

If the worker remains alive after `stop()`, do not claim that cleanup completed normally.

Do not conceal the condition by suppressing exceptions.

---

## 9. Additional mandatory shutdown test

In addition to the original T1–T6 tests, implement a dedicated test for the one-second shutdown race.

### T7 — Worker lingering during shutdown

Use a fake serial implementation with a controllable blocking write.

Test procedure:

1. Start the CommandHub.
2. Submit a motor command.
3. Block the fake serial write after it begins.
4. Initiate `stop()`.
5. Allow the one-second join timeout to expire.
6. Verify that the worker is still alive when `stop()` returns.
7. Release the blocked write.
8. Allow the worker to terminate.
9. Verify that the recorder captures the write attempt and its final status.
10. Verify that the attempt is not credited to a sweep point after shutdown began.
11. Verify that `WORKER_LINGERING` is recorded.
12. Verify that no additional sweep commands are submitted.
13. Verify that the run does not claim successful centering.

This test must exercise the real archived CommandHub with a fake serial implementation, not a replacement CommandHub.

The test must be deterministic and must not require physical hardware.

If a reliable test requires a controlled synchronization event rather than arbitrary sleep timing, use synchronization events.

---

## 10. Interruption and return-to-center policy

Center position is:

```python
CENTER = 512
```

The v0.5 driver must distinguish a centering request from successful transmission.

Use these states:

| State | Meaning |
|---|---|
| `CENTER_REQUESTED` | Three center commands were submitted |
| `CENTER_TX_CONFIRMED` | Three complete matching center frames were recorded |
| `CENTER_DEGRADED` | Center attempts completed, but at least one was short or failed |
| `CENTER_FAILED` | Center barrier timed out or could not complete |
| `CENTER_NOT_ATTEMPTED` | Centering could not safely be requested |

**Important:** `CENTER_TX_CONFIRMED` means that the three center frames were successfully transmitted. It does not prove that the physical platform reached center.

Physical centering requires sensor feedback and is outside the scope of v0.5.

### Centering safety rules

- Centering may be requested only while the transport is healthy and the hub is usable.
- Do not submit centering commands after shutdown has begun.
- Do not submit centering commands if the worker is lingering or the transport is closed.
- Do not attempt centering after an unrecoverable transport failure.
- Centering must use the same three-attempt barrier as ordinary sweep points.
- Center commands must be logged as normal position transmissions, with a distinct center phase or a documented `point_index = -1` sentinel.
- Do not claim physical centering based solely on transmission records.

### Run status

Use these run statuses:

| Status | Meaning |
|---|---|
| `COMPLETE` | All sweep points completed and center transmission confirmed |
| `INCOMPLETE` | A point or ledger verification failed |
| `INTERRUPTED` | User interrupted the run, with center status reported separately |
| `TRANSPORT_FAILURE` | Transport opening failed or the hub/transport failed early |

The final report must display run status and center status separately.

On `KeyboardInterrupt`, perform only a bounded, safe centering attempt if the transport remains usable. Do not hang indefinitely during interruption handling.

---

## 11. CSV and analysis compatibility

The existing v0.4.1 analysis workflow must continue to work.

Inspect the actual historical source and analyzer before implementing the writers.

### TX CSV

Preserve the original ten columns in their existing order:

```text
timestamp
elapsed_ms
command_type
motor
position
bytes_hex
bytes_written
expected
status
error
```

Preserve the existing meanings and status vocabulary:

```text
OK
SHORT
ERROR
```

Populate `bytes_written` using the actual return value recorded by the serial proxy.

Populate `expected` using the expected frame length.

Append these v0.5 fields after the original ten columns:

```text
run_id
point_index
attempt_seq
post_close
```

Use a documented center/control classification. If using `point_index = -1` for center/control rows, document how control frames are distinguished.

Do not change the original ten columns.

### Sensor CSV

Preserve the v0.4.1 sensor CSV schema exactly, including the existing `CSV_FIELDS` order and field names.

Do not modify the WT901C decoder or invent new sensor values.

If sensor collection is not part of a particular v0.5 run, report that it was not collected. Never populate sensor CSV fields with fabricated or placeholder measurements that could be mistaken for actual measurements.

### JSONL events file

Create a third artifact containing timestamped structured events.

At minimum, record:

- Run start and end.
- Serial recorder installation and restoration.
- Transport open success/failure.
- Sweep point submission.
- Write attempt completion.
- Point barrier completion/timeout.
- Frame verification result.
- Short writes and exceptions.
- Center state transitions.
- Shutdown start/end.
- Worker lingering.
- Post-close attempts.
- Final run status.

Events must be recorded independently of the archived CommandHub debug setting.

Use structured JSON objects, one per line.

Do not rely on the archived human-readable `pop_events()` output as the authoritative log.

### Analyzer compatibility test

The existing analyzer:

```text
analysis/analyze_h3_characterization.py
```

must remain unchanged.

Verify that it can read:

1. Existing v0.4.1 CSV files.
2. Synthetic v0.5 TX CSV files containing the original ten columns plus the appended fields.
3. Compatible sensor CSV files.

The existing analyzer uses `csv.DictReader` and accesses fields using `.get()`. Confirm this behavior with an actual end-to-end test rather than assuming compatibility.

---

## 12. Required software-only tests

Implement the following tests using a fake serial module based on the archived test harness:

```text
ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/tests/serial.py
```

Do not use a physical serial port.

### T1 — Normal ledger and barrier

- Fake serial returns five bytes for every write.
- Submit one sweep point.
- Verify three completed attempts.
- Verify all statuses are `OK`.
- Verify `tx_count` delta is three.
- Verify exact frame-byte equality with the ledger.
- Verify point classification is `COMPLETE`.

### T2 — Coalescing protection

- Demonstrate that the archived motion queue can coalesce commands when points are submitted too quickly.
- Verify that the v0.5 driver prevents this by waiting for each point's barrier before submitting the next point.
- Verify that every intended point produces exactly three recorded motor attempts.

### T3 — Short-write detection

- Configure fake serial to return three bytes for one motor frame.
- Verify that the recorder marks the attempt `SHORT`.
- Verify that the CommandHub may still increment `tx_count`.
- Verify that the barrier rejects the point despite a `tx_count` delta of three.
- Verify that the point is classified `DEGRADED` or the documented equivalent.

### T4 — Exception and shutdown handling

- Inject a serial write exception.
- Verify that the recorder records `ERROR`.
- Verify that the exception is re-raised to the archived CommandHub.
- Verify that the hub's `last_error` is observable.
- Verify that the driver does not claim successful transmission.
- Verify that no commands are submitted after shutdown begins.

### T5 — Center-state machine

Exercise all five center states:

- `CENTER_REQUESTED`
- `CENTER_TX_CONFIRMED`
- `CENTER_DEGRADED`
- `CENTER_FAILED`
- `CENTER_NOT_ATTEMPTED`

Verify associated TX records, events, and final run-status reporting.

### T6 — CSV compatibility

- Generate synthetic v0.5 TX and sensor CSV files.
- Run the unchanged existing analysis script against them.
- Verify that it parses the files.
- Verify that `all_full_writes` is correct.
- Verify that sensor group keys and available analysis outputs are present.
- Verify that the analyzer still accepts historical v0.4.1 files.

### T7 — Worker lingering during shutdown

Implement the deterministic blocking-write test described in Section 9.

### Archived regression tests

Run the archived software-only tests without modifying the archived source or tests.

The previously observed `test_manual_cli.py` ±10-versus-±20 mismatch is a known historical failure. Report it accurately; do not silently change the archived test or implementation to make it pass.

Also report any pre-existing historical v0.4.1 test/API mismatch separately.

---

## 13. Code quality and verification requirements

Before reporting implementation complete:

1. Run Python syntax compilation on every new Python file.
2. Run the new v0.5 unit tests.
3. Run T1–T7.
4. Run the archived software-only regression tests.
5. Run the existing analyzer compatibility test.
6. Check imports and package entry points.
7. Check cleanup paths for normal completion, exceptions, and interruption.
8. Check that the recorder is restored correctly.
9. Check that no historical source or raw capture was changed.
10. Inspect the final Git diff.

Use software-only tests. Do not connect to, power, or move the H3.

Do not create a test that silently opens `/dev/ttyACM0` or `/dev/ttyUSB0`.

Do not use a real serial device as a fallback if a fake serial test fails.

Do not claim a test passed unless it was actually executed and its result was inspected.

---

## 14. Documentation updates

Update the relevant project documentation to describe v0.5.

At minimum:

### README.md

- Add v0.5 to the project overview.
- Add the new package to the directory tree.
- Explain the separation between historical calibration source and the new sweep implementation.
- Explain how to run software-only tests.
- Explain that hardware testing has not yet been performed.

### docs/SOFTWARE_ARCHITECTURE.md

- Document the recorder, ledger, barrier, driver, and logging responsibilities.
- Explain the module-attribute serial injection.
- Explain the CommandHub limitations that v0.5 works around.
- Document the shutdown race and the v0.5 handling policy.

### docs/TESTING_AND_CALIBRATION.md

- Document T1–T7.
- Document the required software-only verification sequence.
- Explain the distinction between transmitted center commands and physical centering.
- State that physical validation remains outstanding.

### docs/VERSION_HISTORY.md

- Add a v0.5 entry.
- Identify the new files.
- Identify the tests performed.
- Identify known limitations.
- Do not claim hardware validation.

### QWEN_INSTRUCTIONS.md

- Add the v0.5 architecture and preservation rules.
- Explain the write-attempt barrier and recorder.
- Explain that `tx_count` is not proof of complete transmission.
- Explain the center-state terminology.
- Preserve the existing historical-source rules.

Update `MANIFEST.sha256` only after all intended documentation and source changes are complete. Verify the resulting manifest with `sha256sum -c MANIFEST.sha256`.

Do not regenerate the manifest prematurely.

---

## 15. Out of scope for v0.5

Do not implement the following in this version:

- WT901C sensor decoder changes.
- Sensor-based physical centering confirmation.
- SMC3 readback protocol.
- X-Plane UDP integration.
- SRS protocol emulation.
- X-Plane dataref mapping.
- Motion cueing algorithms.
- Pitch/roll/yaw mixing changes.
- Acceleration or engine vibration effects.
- Rust port.
- Changes to SMC3 firmware.
- Changes to the archived CommandHub.

These are future development stages.

The v0.5 goal is reliable, verifiable motor-command transmission and calibration logging.

---

## 16. Required final implementation report

When implementation is complete, provide a report with these sections:

### A. Implementation summary
Describe what was implemented and how the modules interact.

### B. Files created
List every new file.

### C. Files modified
List every modified file and explain the reason for each modification.

### D. Files preserved
Explicitly confirm that the archived v0.3.5.1 source, historical v0.4.1 source, and raw captures remain unchanged.

### E. Test results
Provide a table containing:

| Test | Result | Evidence/notes |
|---|---|---|
| Syntax compilation | | |
| T1 | | |
| T2 | | |
| T3 | | |
| T4 | | |
| T5 | | |
| T6 | | |
| T7 | | |
| Archived regression tests | | |
| Analyzer compatibility | | |
| Manifest verification | | |

Use `PASS`, `FAIL`, `NOT RUN`, or `BLOCKED`. Do not use ambiguous wording.

### F. Known issues
List unresolved problems and distinguish pre-existing issues from new v0.5 issues.

### G. Hardware readiness
State clearly:

- No physical H3 test was performed.
- No hardware movement was attempted.
- Software-only tests are not proof of physical operation.
- The first hardware test still requires controlled validation.

### H. Git status
Report the branch, changed files, and whether the working tree is clean. Do not commit unless explicitly instructed.

---

## 17. Implementation instructions

Proceed in this order:

1. Inspect the current repository and confirm all baseline paths.
2. Confirm the archived CommandHub API and source hash.
3. Implement the serial recorder and its fake-serial tests.
4. Implement the ledger and barrier.
5. Implement the driver and run/center state machine.
6. Implement JSONL and CSV logging.
7. Implement T1–T7.
8. Run all software-only verification.
9. Update documentation and manifest.
10. Review the complete diff and produce the final implementation report.

Do not stop after producing another plan or design document.

If an implementation detail is genuinely blocked by missing source or an unresolved interface, stop at that specific blocker and report the exact evidence. Do not invent an API or silently change the baseline.

**Primary engineering priority: preserve the known working CommandHub behavior while making every v0.5 motor transmission observable, attributable, and verifiable.**
