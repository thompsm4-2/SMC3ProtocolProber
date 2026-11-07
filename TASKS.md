# v0.5 Implementation Tasks — DOF Reality H3 Sweep Driver & Reliable Serial Recording

Broken down from `Implementation.md`. Status corrected 2026-11-05: v0.3.5.1 CommandHub baseline restored and hash-verified (see `reports/SOURCE_LOG_PROVENANCE.md`); Phase 0 preflight complete; Phases 1–10 not implemented (no `src/sweep/h3_sweep_v05/` package exists).

## Phase 0 — Preflight / Baseline Inspection

- [x] **T0.1** Follow `AGENTS.md` reading requirements; for v0.5 driver/recorder work that means `QWEN_INSTRUCTIONS.md`, `docs/SOFTWARE_ARCHITECTURE.md`, `docs/TESTING_AND_CALIBRATION.md`, `docs/HARDWARE_REFERENCE.md`. Read `reports/` only when inspecting historical v0.4.1 evidence.
- [x] **T0.2** Inspect actual repository structure; confirm all baseline paths exist (archived v0.3.5.1 CommandHub, historical v0.4.1 source, raw captures, `analysis/analyze_h3_characterization.py`, archived test harness `ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/tests/serial.py`).
- [x] **T0.3** Confirm archived CommandHub API: `CommandHub(transport, rate_hz=30.0, debug=False, event=None)`, `MotorCommand(motor, position)`, `SMC3Transport`.
- [x] **T0.4** Confirm archived `smc3.py` source hash / known behaviors (worker thread owns writes, latest-value coalescing, `wait_for_idle()` unreliable, `tx_count` increments after `write()` returns, transport discards byte count, worker catches exceptions, `stop()` joins 1 s then closes).
- [x] **T0.5** If any required baseline file is missing — report it, do not recreate or approximate. (Condition not met: all required baseline paths confirmed present and hash-verified by T0.2 / `reports/SOURCE_LOG_PROVENANCE.md`.)

## Phase 1 — Package Skeleton

- [x] **T1.1** Create `src/sweep/h3_sweep_v05/` with modules: `__init__.py`, `driver.py`, `recorder.py`, `ledger.py`, `eventslog.py`, `csvlog.py`.
- [x] **T1.2** Assign responsibilities: `driver.py` (sweep execution, sequencing, barriers, interruption, centering, run status); `recorder.py` (serial proxy, write-attempt records, synchronization, write status); `ledger.py` (expected frames, point association, exact verification); `eventslog.py` (JSONL events); `csvlog.py` (v0.4.1-compatible CSVs).
- [x] **T1.3** Ensure modules are independently testable, no circular imports, no unnecessary dependencies.
- [x] **T1.4** Add tests following the project's existing test organization/conventions.
- [x] **T1.5** New package must not modify archived CommandHub.

## Phase 2 — Serial Write Recorder

- [x] **T2.1** Implement serial-module injection shim at `smc3.serial` (module attribute), installed before CommandHub starts; shim's `Serial` class delegates to real pyserial while recording every write attempt.
- [x] **T2.2** Shim preserves: serial construction, port opening, baud config, read/write timeouts, two-second Arduino reset delay, writes, closing.
- [x] **T2.3** Prohibitions: no modification of private `SerialTransport._serial`, no second serial connection, no bypassing the archived transport's write lock/lifecycle.
- [x] **T2.4** Scope recorder to one run; restore original `smc3.serial` reference during cleanup only after the worker can no longer use the recorded serial. Document the module-level injection limitation (not thread-safe for concurrent runs).
- [x] **T2.5** Attempt record fields: `attempt_seq`, `timestamp`, `monotonic_timestamp`, `frame_bytes`, `returned_count`, `expected_count`, `status`, `exception`. Monotonic sequence numbers; monotonic time for ordering. Recorder must be thread-safe.
- [x] **T2.6** Status classification: `OK` (exact expected bytes), `SHORT` (fewer), `ERROR` (exception). Expected SMC3 frame length = 5 bytes.
- [x] **T2.7** On exception: record `ERROR`, preserve exception info, re-raise original exception so archived CommandHub sees the same failure. Never convert exceptions to successful returns.
- [x] **T2.8** Record `SHORT` even though CommandHub may still increment `tx_count`. Never silently discard partial writes.

## Phase 3 — Ledger and Write-Attempt Barrier

- [x] **T3.1** Barrier interface: `Barrier.wait_for_attempts(expected: int, timeout: float) -> AttemptBatch`. Waits until N attempts reach terminal state (`OK`/`SHORT`/`ERROR`). Bounded timeout, no indefinite hang. Must not use `wait_for_idle()` or rely on `tx_count` alone.
- [x] **T3.2** Driver-owned expected-frame ledger: generate expected frames via archived `MotorCommand`/`encode_command`; preserve exact motor order and encoded bytes.
- [x] **T3.3** Per-point sequencing: generate 3 expected frames (A, B, C) → snapshot attempt_seq and tx_count → submit 3 `MotorCommand` objects via CommandHub motion path → wait for 3 new closed attempt records → compare recorded vs. expected ledger → verify byte counts → verify statuses → record point result → only then submit next point.
- [x] **T3.4** Enforce: point k's three-attempt barrier completes before point k+1 is submitted (protects against latest-value-per-motor coalescing).
- [x] **T3.5** Associate attempts to points via monotonically increasing sequence numbers + point expectation ledger (not approximate timestamps).
- [x] **T3.6** Control frames classified separately; never count toward a point's three motor-position frames. Frame mismatch = software error → point FAILED.
- [x] **T3.7** Point classification: 3 matching all-OK frames + tx_count Δ3 → `COMPLETE`; any short write → `DEGRADED`; any write exception → `FAILED`; barrier timeout → `FAILED`; frame mismatch → `FAILED`; unexpected motor/missing frame → `FAILED`. A short write fails the point even with Δ3.
- [ ] **T3.8** Use `MotorCommand` via motion queue for all ordinary motor-position commands; never `submit_control()` for those. Control queue reserved for real SMC3 control frames.
- [ ] **T3.9** Classification implemented in new package from documented protocol; do not import/execute historical v0.4.1 source.

## Phase 4 — Shutdown and Worker-Lingering Handling

- [ ] **T4.1** Shutdown procedure: mark run shutting-down → arm recorder shutdown/close-window tracking → call archived hub shutdown → check worker liveness → emit `WORKER_LINGERING` if alive → record current `tx_count` → classify attempts during/after shutdown separately → no additional motor commands → no return-to-center through possibly-closing transport → preserve recorder/event data until no worker can access them → restore `smc3.serial` only when it cannot interfere with an active run.
- [ ] **T4.2** Post-close attempt handling: every attempt classifiable as sweep-point-associated, control/center, or post-close/shutdown-overlap. Shutdown-overlap attempts never credited to a sweep point. If worker lingering after `stop()`, do not claim normal cleanup; do not conceal via exception suppression.
- [ ] **T4.3** Do not modify archived `stop()` implementation.

## Phase 5 — Interruption & Return-to-Center State Machine

- [ ] **T5.1** `CENTER = 512`. Distinguish centering request from confirmed transmission.
- [ ] **T5.2** Center states: `CENTER_REQUESTED`, `CENTER_TX_CONFIRMED`, `CENTER_DEGRADED`, `CENTER_FAILED`, `CENTER_NOT_ATTEMPTED`.
- [ ] **T5.3** Centering safety rules: only while transport healthy/hub usable; never after shutdown begun; never if worker lingering or transport closed; never after unrecoverable transport failure; same three-attempt barrier as sweep points; log center commands as normal position transmissions with distinct phase or documented `point_index = -1` sentinel; never claim physical centering from transmission records alone.
- [ ] **T5.4** Run statuses: `COMPLETE`, `INCOMPLETE`, `INTERRUPTED`, `TRANSPORT_FAILURE`. Final report displays run status and center status separately.
- [ ] **T5.5** On `KeyboardInterrupt`: bounded, safe centering attempt only if transport remains usable; do not hang during interruption handling.

## Phase 6 — CSV and JSONL Logging

- [ ] **T6.1** Inspect actual historical v0.4.1 source and analyzer before implementing writers.
- [ ] **T6.2** TX CSV: preserve original 10 columns in order (`timestamp`, `elapsed_ms`, `command_type`, `motor`, `position`, `bytes_hex`, `bytes_written`, `expected`, `status`, `error`); preserve `OK`/`SHORT`/`ERROR` vocabulary; `bytes_written` from serial-proxy return value; `expected` from frame length. Append v0.5 fields after: `run_id`, `point_index`, `attempt_seq`, `post_close`. Document center/control classification (`point_index = -1` sentinel; document how control frames are distinguished). Do not change the original ten columns.
- [ ] **T6.3** Sensor CSV: preserve v0.4.1 schema exactly (`CSV_FIELDS` order/names). No WT901C decoder changes, no invented sensor values. If sensor collection not part of a run, report "not collected"; never fabricate placeholders.
- [ ] **T6.4** JSONL events file: record at minimum run start/end, recorder install/restore, transport open success/failure, point submissions, write attempt completions, barrier completions/timeouts, frame verification results, short writes/exceptions, center state transitions, shutdown start/end, worker lingering, post-close attempts, final run status. Independent of archived CommandHub debug setting. Structured JSON, one per line. Do not rely on archived `pop_events()` as authoritative log.
- [ ] **T6.5** Analyzer `analysis/analyze_h3_characterization.py` must remain unchanged. Verify (via actual end-to-end test, not assumption) it reads: existing v0.4.1 CSVs, synthetic v0.5 TX CSVs (10 + appended fields), compatible sensor CSVs. Confirm `csv.DictReader`/`.get()` compatibility.

## Phase 7 — Software-Only Tests (fake serial from archived harness)

- [ ] **T7.1** T1 — Normal ledger and barrier: fake serial returns 5 bytes; one point; 3 completed attempts; all `OK`; tx_count Δ3; exact frame-byte equality vs. ledger; classification `COMPLETE`.
- [ ] **T7.2** T2 — Coalescing protection: demonstrate archived queue coalescing when points submitted too fast; verify v0.5 driver prevents it via per-point barrier; every intended point → exactly 3 recorded motor attempts.
- [ ] **T7.3** T3 — Short-write detection: fake serial returns 3 bytes for one frame; recorder marks `SHORT`; CommandHub may still increment `tx_count`; barrier rejects point despite Δ3; point classified `DEGRADED` or documented equivalent.
- [ ] **T7.4** T4 — Exception and shutdown handling: inject write exception; recorder records `ERROR`; exception re-raised to archived CommandHub; hub `last_error` observable; driver does not claim successful transmission; no commands submitted after shutdown begins.
- [ ] **T7.5** T5 — Center-state machine: exercise all five center states; verify associated TX records, events, final run-status reporting.
- [ ] **T7.6** T6 — CSV compatibility: generate synthetic v0.5 TX and sensor CSVs; run unchanged existing analysis script; verify parsing, `all_full_writes` correctness, sensor group keys and available analysis outputs; verify analyzer still accepts historical v0.4.1 files.
- [ ] **T7.7** T7 — Worker lingering during shutdown (dedicated deterministic test): fake serial with controllable blocking write; start CommandHub → submit motor command → block fake write after it begins → initiate `stop()` → let 1 s join timeout expire → verify worker still alive when `stop()` returns → release blocked write → allow worker to terminate → verify recorder captures the attempt and final status → verify attempt not credited to a sweep point after shutdown began → verify `WORKER_LINGERING` recorded → verify no additional sweep commands submitted → verify run does not claim successful centering. Must use real archived CommandHub with fake serial (not a replacement hub). Deterministic, hardware-free; use synchronization events instead of arbitrary sleep timing where needed.
- [ ] **T7.8** Archived regression tests: run archived software-only tests without modifying archived source/tests. Report the known `test_manual_cli.py` ±10-vs-±20 historical failure accurately; do not alter archived code to make it pass. Report any pre-existing historical v0.4.1 test/API mismatch separately.
- [ ] **T7.9** Tests must never open `/dev/ttyACM0` or `/dev/ttyUSB0`, and must not fall back to a real serial device on failure.

## Phase 8 — Verification Sequence

- [ ] **T8.1** Run Python syntax compilation on every new Python file.
- [ ] **T8.2** Run new v0.5 unit tests, then T1–T7.
- [ ] **T8.3** Run archived software-only regression tests.
- [ ] **T8.4** Run analyzer compatibility test.
- [ ] **T8.5** Check imports and package entry points.
- [ ] **T8.6** Check cleanup paths: normal completion, exceptions, interruption.
- [ ] **T8.7** Check recorder restoration of `smc3.serial`.
- [ ] **T8.8** Confirm no historical source or raw capture changed.
- [ ] **T8.9** Inspect final Git diff.

## Phase 9 — Documentation Updates

- [ ] **T9.1** `README.md`: add v0.5 to overview, new package to directory tree, separation of historical calibration source vs. new sweep implementation, how to run software-only tests, note that hardware testing not yet performed.
- [ ] **T9.2** `docs/SOFTWARE_ARCHITECTURE.md`: recorder/ledger/barrier/driver/logging responsibilities, module-attribute serial injection, CommandHub limitations v0.5 works around, shutdown race and v0.5 handling policy.
- [ ] **T9.3** `docs/TESTING_AND_CALIBRATION.md`: document T1–T7, required software-only verification sequence, transmitted-center vs. physical-centering distinction, physical validation still outstanding.
- [ ] **T9.4** `docs/VERSION_HISTORY.md`: v0.5 entry, new files, tests performed, known limitations, no hardware-validation claims.
- [ ] **T9.5** `QWEN_INSTRUCTIONS.md`: v0.5 architecture and preservation rules, write-attempt barrier and recorder, `tx_count` not proof of complete transmission, center-state terminology, preserve existing historical-source rules.
- [ ] **T9.6** Update `MANIFEST.sha256` only after all intended doc/source changes complete; verify with `sha256sum -c MANIFEST.sha256`. Do not regenerate prematurely.

## Phase 10 — Final Report

- [ ] **T10.1** Section A: Implementation summary (modules and interactions).
- [ ] **T10.2** Section B: Files created (all new files).
- [ ] **T10.3** Section C: Files modified + reason each.
- [ ] **T10.4** Section D: Files preserved — explicit confirmation archived v0.3.5.1 source, historical v0.4.1 source, raw captures unchanged.
- [ ] **T10.5** Section E: Test results table (Syntax compilation, T1–T7, Archived regression tests, Analyzer compatibility, Manifest verification) with `PASS`/`FAIL`/`NOT RUN`/`BLOCKED` only.
- [ ] **T10.6** Section F: Known issues — distinguish pre-existing from new v0.5 issues.
- [ ] **T10.7** Section G: Hardware readiness — no physical H3 test performed, no hardware movement, software-only tests not proof of physical operation, first hardware test still requires controlled validation.
- [ ] **T10.8** Section H: Git status — branch, changed files, working-tree cleanliness. Do not commit unless explicitly instructed.

---

## Global Preservation Constraints (apply to every task)

- Do not modify, rename, or delete archived v0.3.5.1 source or historical v0.4.1 calibration source.
- Do not modify/delete existing raw capture data or overwrite historical analysis results.
- Do not modify SMC3 firmware or the archived CommandHub (including `stop()`).
- Do not reorganize unrelated project directories; keep `protocol-analyzer` flat.
- Do not change existing CSV column names/meanings.
- No hardware-dependent tests in the software-only suite; never claim hardware testing.
- No new unnecessary dependencies.
- Check Python syntax and imports before delivering modified code.

## Out of Scope for v0.5 (do not implement)

WT901C decoder changes, sensor-based physical centering confirmation, SMC3 readback protocol, X-Plane UDP/SRS/dataref mapping, motion cueing, pitch/roll/yaw mixing, acceleration/vibration effects, Rust port, SMC3 firmware changes, archived CommandHub changes.

## Task Ordering / Dependencies

Phases must proceed in order 0 → 10 per Implementation.md §17: inspect baseline → package skeleton → recorder + fake-serial tests → ledger + barrier → driver + run/center state machine → JSONL/CSV logging → T1–T7 → run all software-only verification → documentation + manifest → final diff review and report. Do not stop at a plan; if genuinely blocked by missing source or unresolved interface, stop at that specific blocker and report exact evidence.

**Primary engineering priority: preserve known-working CommandHub behavior while making every v0.5 motor transmission observable, attributable, and verifiable.**
