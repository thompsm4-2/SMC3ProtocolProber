# Bug Backlog — DOF Reality H3 Linux Driver Project

> **Audit date:** November 15, 2026
> **Scope:** Read-only inspection of production code, diagnostic scripts, CLI handling, tests, configuration, and documentation.
> **Rules applied:** No hardware interaction. No code fixes. No claims of exhaustiveness.
>
> Priority legend: **P0** = data loss / hardware risk / silent failure &nbsp;|&nbsp; **P1** = incorrect behavior under valid use &nbsp;|&nbsp; **P2** = degraded behavior / code quality &nbsp;|&nbsp; **P3** = minor / cosmetic
>
> Status legend: **Open** = confirmed defect &nbsp;|&nbsp; **Needs Investigation** = suspected but unverified &nbsp;|&nbsp; **Rejected** = false positive &nbsp;|&nbsp; **Resolved** = already fixed in the current repository

---

## Executive Summary (After Re-Verification)

| Status | Count | Notes |
|--------|-------|-------|
| Open (confirmed bugs) | 1 | BUG-005 (P2) |
| Rejected (false positives) | 7 | BUG-002, BUG-003, BUG-004, BUG-006, BUG-008, BUG-015, BUG-016 |
| Code quality / test maintenance | 4 | BUG-010, BUG-012, BUG-013, BUG-014 |
| **Total retained** | **16** | All original IDs preserved |

| Priority | Count |
|----------|-------|
| P1 – High | 0 |
| P2 | 1 |
| P3 | 6 |
| **Total** | **7** (functional + code quality) |

---

## Open — Confirmed Functional Defects

### BUG-001: READ_COMMANDS encoding mismatch between h3_characterize.py and smc3_readback_diagnostic.py

| Field        | Value |
|--------------|-------|
| **Status**   | Resolved |
| **File(s)**  | `src/calibration/h3_characterize.py` line 52; `src/calibration/smc3_readback_diagnostic.py` line 48 |
| **Impact**   | `h3_characterize.py` sends SMC3 readback commands with lowercase motor bytes, whereas the November 14, 2026 H3 investigation confirmed the controller responds to uppercase `[rdA]`, `[rdB]`, `[rdC]`. The practical impact is unreliable or unavailable readback data in the `h3_characterize.py` characterization workflow. No hardware damage, safety risk, or data loss has been demonstrated. |
| **Description** | `h3_characterize.py` encodes read requests with **lowercase** motor bytes: `bytes([91, 114, 100, 97, 93])` → `[rda]` (0x5B 0x72 0x64 0x61 0x5D). `smc3_readback_diagnostic.py` encodes with **uppercase** motor bytes: `bytes([91, 114, 100, 65, 93])` → `[rdA]` (0x5B 0x72 0x64 0x41 0x5D). The third motor byte differs by 32 (0x61 vs 0x41). |
| **Evidence** | ```python # h3_characterize.py line 52-54 "A": bytes([91, 114, 100, 97, 93]),  # [rda]  # 0x61 = 'a' # smc3_readback_diagnostic.py line 48-50 "A": bytes([91, 114, 100, 65, 93]),  # [rdA]  # 0x41 = 'A' # ChatGPT-archive reference smc3.py line 48-52: encode_read_feedback('A') produces b'[rdA]' (0x41) # November 14, 2026 investigation: H3 demonstrated responses to [rdA], [rdB], [rdC] (uppercase) ``` |
| **Reproduction** | Run `h3_characterize.py --readback` and observe that no valid readback responses are logged. Cross-reference with `smc3_readback_diagnostic.py --motor A --duration 5 --simulate --simulate-response "5B 41 00 00"` which uses the correct uppercase encoding. |
| **Priority** | P1 – High |
| **Confidence** | High |
| **Notes** | The ChatGPT-archive `smc3.py` (line 48) uses `encode_read_feedback` which produces `bytes((0x5B, ord("r"), ord("d"), ord(motor), 0x5D))` with motor uppercased — this is upstream reference implementation evidence. The November 14, 2026 H3 readback investigation demonstrated that the actual H3 controller responds to uppercase `[rdA]`, `[rdB]`, `[rdC]` commands. This measured evidence establishes that `smc3_readback_diagnostic.py` encodes correctly and `h3_characterize.py` encodes incorrectly. The lowercase `[rda]` implementation in `h3_characterize.py` is a legacy error — it may have worked with an older controller firmware version or was simply a typo that propagated. No hardware damage, safety risk, or data loss has been demonstrated; the practical impact is unreliable or unavailable readback data in the `h3_characterize.py` characterization workflow. |
| **Resolution** | Fixed in `openspec/changes/fix-readback-encoding/`: byte literals corrected to uppercase (Motor A: 97→65, B: 98→66, C: 99→67). Regression test added in `src/calibration/test_h3_characterize.py`. All 73 existing tests in `test_readback_diagnostic.py` pass. |

---

### BUG-005: `--read-timeout` does not control `poll_motor()` response collection timeout

| Field        | Value |
|--------------|-------|
| **Status**   | Open |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 61, 720, 783, 954–957, 1099, 1160, 1178, 1312, 1347 |
| **Impact**   | The `--read-timeout` CLI option does not control the response collection timeout used by `poll_motor()`. Users who set `--read-timeout` to a value other than 0.10 s will not observe any change in response collection behavior. The option is misleading — users expect it to control how long the tool waits for a readback response, but it does not. |
| **Description** | Three distinct timeout values are involved in the polling path, and only one is controlled by `--read-timeout`:<br><br>1. **Serial port timeout** — set via `timeout=args.read_timeout` at line 1312 (real hardware) and line 1099 (simulate mode). This controls how long `serial.read(1)` blocks on a single call before returning empty data.<br>2. **Response collection deadline** — set inside `poll_motor()` at line 533 as `deadline = start + timeout`, where `timeout` is the first parameter to `poll_motor()`. This controls the total wall-clock time spent waiting for a response.<br>3. **Hardcoded `DEFAULT_TIMEOUT`** — all call sites pass `DEFAULT_TIMEOUT` (0.10 s) as the first argument to `poll_motor()` (lines 720, 783, 1160, 1178, 1347).<br><br>Because the response collection deadline is always `start + 0.10`, changing `--read-timeout` has no effect on how long the tool waits for a readback response. The serial port timeout (item 1) is set to `args.read_timeout`, but `poll_motor()` reads byte-by-byte inside a while loop that checks `time.monotonic() < deadline` (line 532). If `args.read_timeout` exceeds 0.10 s, a single `serial.read(1)` call could block the thread for longer than the deadline, which is a secondary concern but does not extend the effective response collection window.<br><br>The `run_active()` method does not accept a `timeout` parameter at all; it hardcodes `DEFAULT_TIMEOUT` in its `poll_motor()` call at line 783. |
| **Evidence** | ```python # Line 61: DEFAULT_TIMEOUT = 0.10 # Line 720 (run_passive): self.poll_motor(DEFAULT_TIMEOUT, interval, delay) # Line 783 (run_active): success = self.poll_motor(DEFAULT_TIMEOUT, 0.05) # Line 954-957: --read-timeout arg, default=DEFAULT_TIMEOUT # Line 1099 (simulate): timeout=args.read_timeout → FakeSerial # Line 1160 (simulate ALL): diag_motor.poll_motor(DEFAULT_TIMEOUT, interval, args.delay) # Line 1178 (simulate single): diagnostic.poll_motor(DEFAULT_TIMEOUT, interval, args.delay) # Line 1312 (real hardware): timeout=args.read_timeout → serial.Serial # Line 1347 (real-hardware ALL): diag_motor.poll_motor(DEFAULT_TIMEOUT, interval, args.delay) # Line 533 (inside poll_motor): deadline = start + timeout  # uses parameter, not self.ser.timeout ``` |
| **Reproduction** | `python smc3_readback_diagnostic.py --port /dev/ttyACM0 --motor A --read-timeout 2.0 --duration 5` — the response collection timeout remains 0.10 s regardless of the `--read-timeout` value. |
| **Priority** | P2 |
| **Confidence** | High |
| **Notes** | The `run_active()` method signature does not accept a `timeout` parameter; it hardcodes `DEFAULT_TIMEOUT` in its `poll_motor()` calls. Fix: pass `args.read_timeout` to all `poll_motor()` call sites, and add a `timeout` parameter to `run_active()`. |

---

### BUG-002: `poll_motor()` in smc3_readback_diagnostic.py writes the request twice

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 448–457 (send_request), 485–560 (poll_motor) |
| **Impact**   | N/A — not a bug |
| **Description** | The original report claimed `send_request()` was called before the write inside `poll_motor()`, producing a double write. Verification shows `send_request()` is **dead code** — it is defined at line 448 but never called anywhere in the codebase. `poll_motor()` writes the request exactly once at line 509. |
| **Evidence** | ```bash $ grep -n "send_request" src/calibration/smc3_readback_diagnostic.py 448:    def send_request(self) -> Tuple[bytes, int]: # Only the definition; no callers found ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | `send_request()` should be removed as dead code. Its return value `(b"", written)` is also misleading (returns empty bytes as a placeholder response). |

### BUG-003: ALL-motor stats merging discards previous motor data

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 1156, 1344 |
| **Impact**   | N/A — not a bug |
| **Description** | The original report claimed `diag_motor.stats.update(diagnostic.stats)` fails to accumulate stats because `diag_motor` starts with fresh zeros. Verification shows the update correctly copies values from `diagnostic.stats` (previous iteration) into `diag_motor.stats` (new iteration), then `diagnostic = diag_motor` replaces the reference. For mutable values (sets, lists), `dict.update()` replaces the reference with the source's reference, so subsequent `poll_motor()` modifications in-place persist across iterations. |
| **Evidence** | Python trace confirmed: after 3 motors, `total_requests = 3`, `successful = 3`, `response_lengths` accumulates correctly. |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | The stats accumulation works correctly for all stat types (integers, sets, lists). |

### BUG-004: Active test creates diagnostic with `args.motor` instead of `args.active_motor`

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` line 1322 |
| **Impact**   | N/A — not a bug |
| **Description** | The original report claimed that `--motor ALL --active-target-test --active-motor A` would cause a `KeyError: 'ALL'` because the diagnostic is created with `args.motor` ("ALL"). However, `run_active()` at line 739 sets `self.motor = motor` (the parameter), which overrides the constructor argument. So `self.motor` is set to `args.active_motor` ("A"), not `args.motor` ("ALL"). |
| **Evidence** | ```python # Line 1322: diagnostic = ReadbackDiagnostic(session, ser, args.motor, verbose=args.verbose) # Line 1323: diagnostic.run_active(args.active_motor, active_targets, ...) # Line 739 (inside run_active): self.motor = motor  # overwrites self.motor with args.active_motor ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | The constructor argument `args.motor` is effectively ignored in active-test mode. This is confusing but not broken. |

### BUG-006: `ser.flush()` discards input data in h3_characterize.py

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/h3_characterize.py` lines 205, 223 |
| **Impact**   | N/A — not a bug |
| **Description** | The original report claimed `serial.Serial.flush()` discards input data. In pyserial 3.5, `flush()` only waits until all output data is written. It does **not** discard input data (that is `flushInput()`). The behavior is correct for the intended use case (ensure the command is fully transmitted before reading the response). |
| **Evidence** | ```python # pyserial 3.5 documentation: # flush(): "Flush of file like objects. In this case, wait until all data is written." # flushInput(): "Discards everything in the input buffer." # flushOutput(): "Discards everything in the output buffer." ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | `flush()` is the correct method here. No change needed. |

### BUG-008: CSV headers duplicated on repeated runs

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 181–195 |
| **Impact**   | N/A — not a bug in normal operation |
| **Description** | The original report claimed CSV headers are duplicated on repeated runs because files are opened in append mode. However, each run creates a **timestamped subdirectory** (`run_dir_name = run_now.strftime("%Y-%m-%d_%H-%M-%S")`). Files are written to this unique subdirectory, so repeated runs get separate directories and no header duplication occurs. |
| **Evidence** | ```python # Line 185: run_dir_name = run_now.strftime("%Y-%m-%d_%H-%M-%S") # Line 188: self.output_dir = self.output_dir / run_dir_name # Each run gets a unique subdirectory (to the second) ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | Header duplication is only theoretically possible if two runs start within the same second. The `active_file` has explicit overwrite handling (line 196), while other files use append mode — this inconsistency is harmless in practice but could be cleaned up. |

### BUG-016: FakeSerial TX/RX buffer separation concern (rejected)

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 67–171 (FakeSerial class) |
| **Impact**   | N/A — not a bug |
| **Description** | The original concern questioned whether FakeSerial's serial read and write behavior could allow transmitted command bytes to be returned as simulated controller responses, due to a suspected shared buffer between TX and RX. Verification shows the TX and RX paths are properly separated:

1. **TX path** (`write()`, lines 94–119): Written data is stored in `_write_history` (line 101) for test observation only. The transmitted command bytes are never placed into any read buffer.
2. **RX path** (`read()`, lines 120–142): Reads exclusively from `_response_list` (lines 128–141). Empty responses (timeouts) are skipped (line 131–132). Returns `b""` if no responses available.
3. **Response generation**: When a read command (`[rdA]`, `[rdB]`, `[rdC]`) is written, a canned response from `self.responses` is appended to `_response_list` (line 115). This is a **pre-configured separate byte sequence**, not the transmitted command bytes.
4. **Dead buffers**: `_input_buffer` and `_output_buffer` (lines 85–86) are created in `__init__` but never used for data flow. `reset_input_buffer()` (line 148) and `close()` (lines 157–160) reference them, but they are dead code.

The canned responses are distinct from the transmitted command. For example, `write(b'[rdA]')` appends `self.responses[n]` (e.g., `b'[rdA]OK5D'`) to `_response_list` — the transmitted bytes `0x5B 0x72 0x64 0x41 0x5D` never enter the read path.

The concern likely arose from observing `_input_buffer` and `_output_buffer` created in `__init__` (lines 85–86), which are dead code, creating the impression of a naive shared-buffer design.

**Existing test coverage** that validates this separation:
- `test_fake_serial_responses` — verifies FIFO response delivery and correct response matching
- `test_normal_passive_cli_execution` — full integration: confirms writes are read commands, reads contain valid response bytes, no position commands sent
- `test_single_motor_cli_execution` — confirms only the correct motor command is sent
- `test_response_request_association` — each request has associated response

No test explicitly asserts "transmitted command bytes do not appear in reads," but the implementation design makes this impossible. |
| **Evidence** | ```python # FakeSerial.__init__ (lines 85-86) - DEAD BUFFERS self._input_buffer = io.BytesIO()  # Never used for data flow self._output_buffer = io.BytesIO()  # Never used for data flow # FakeSerial.write() (lines 94-119) - TX path self._write_history.append(data)  # TX data tracked for observation only # Response generated from canned data, NOT from write argument if self.responses and is_read_command:     self._response_list.append(self.responses[self._response_counter])  # Separate canned data # FakeSerial.read() (lines 120-142) - RX path only if not self._response_list:     return b""  # Empty if no canned responses available response = self._response_list[0]  # Reads ONLY from _response_list ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | The FakeSerial implementation in `smc3_readback_diagnostic.py` is correctly designed. A separate FakeSerial class exists in `test_fake_serial.py` (used by `h3_characterize.py`) with a different implementation using `_output_buffer` — that class also does not have a TX/RX separation issue (responses are written to `_output_buffer` only from canned data, not from write arguments). |

### BUG-015: `build_sweep()` can produce duplicate positions

| Field        | Value |
|--------------|-------|
| **Status**   | Rejected |
| **File(s)**  | `src/calibration/h3_characterize.py` lines 372–389 |
| **Impact**   | N/A — not a bug |
| **Description** | The original report claimed duplicate positions are a bug. However, the sweep is **intentionally** designed to visit the same positions from different approach directions (down-and-back, then up-and-back). The docstring at lines 372–380 explicitly documents this behavior: "measurements at the same motor position can be compared by approach direction." The "duplicates" are by design. |
| **Evidence** | ```python # Docstring lines 372-380: # "The path intentionally does not snap to center between the negative and # positive sweeps. Instead it reverses direction through center so that # measurements at the same motor position can be compared by approach direction." # Example (step=20, limit=100): # -20, -40, -60, -80, -100, # -80, -60, -40, -20, 0, # +20, +40, +60, +80, +100, # +80, +60, +40, +20, 0 ``` |
| **Priority** | N/A |
| **Confidence** | High |
| **Notes** | The sweep intentionally revisits positions from different directions for hysteresis comparison. |

---

## Code Quality Observations (Not Functional Bugs)

These are retained for awareness but are not functional defects. They represent dead code, fragile patterns, or test maintenance issues.

### BUG-007: Duplicate `written = None` assignment in `send_command()`

| Field        | Value |
|--------------|-------|
| **Status**   | Resolved |
| **File(s)**  | `src/calibration/h3_characterize.py` line 221 |
| **Impact**   | None. Dead code. |
| **Description** | The statement `written = None` appeared twice on consecutive lines. |
| **Evidence** | ```python # Lines 220-221 (before fix) written = None written = None ``` |
| **Priority** | P3 |
| **Confidence** | High |
| **Resolution** | Fixed in `openspec/changes/fix-duplicate-written-assignment/`: duplicate line 221 removed. File passes `py_compile`. All 2 existing tests in `test_h3_characterize.py` pass. |

### BUG-009: `send_request()` is dead code with misleading return value

| Field        | Value |
|--------------|-------|
| **Status**   | Resolved |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 448–457 |
| **Impact**   | None. Dead code. |
| **Description** | `send_request()` is defined but never called. Its return value `(b"", written)` returns empty bytes as a placeholder "response," which would be misleading if the method were ever used. |
| **Evidence** | `grep -n "send_request" smc3_readback_diagnostic.py` returns only the definition at line 448. |
| **Priority** | P3 |
| **Confidence** | High |
| **Resolution** | Fixed in `openspec/changes/remove-dead-send-request-method/`: `send_request()` method definition removed (lines 448–457). File passes `py_compile`. All 73 existing tests in `test_readback_diagnostic.py` pass.

### BUG-010: Fragile `and`/`or` idiom for mode string

| Field        | Value |
|--------------|-------|
| **Status**   | Open (code quality) |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` lines 1189, 1368 |
| **Impact**   | None currently. Fragile pattern. |
| **Description** | ```python stats["mode"] = args.active_target_test and "ACTIVE" or "PASSIVE" ``` This idiom works because `"ACTIVE"` is truthy, but would fail if a future mode name were falsy (e.g., empty string). Use a proper ternary: `"ACTIVE" if args.active_target_test else "PASSIVE"`. |
| **Evidence** | ```python # Line 1189: stats["mode"] = "SIMULATION_" + (args.active_target_test and "ACTIVE" or "PASSIVE") # Line 1368: stats["mode"] = args.active_target_test and "ACTIVE" or "PASSIVE" ``` |
| **Priority** | P3 |
| **Confidence** | High |

### BUG-011: `FakeSerial.baudrate` attribute is stored but never read

| Field        | Value |
|--------------|-------|
| **Status**   | Resolved |
| **File(s)**  | `src/calibration/smc3_readback_diagnostic.py` line 80; `src/calibration/test_readback_diagnostic.py` lines 704, 834, 1160 |
| **Impact**   | None. Dead attribute. |
| **Description** | `FakeSerial.__init__` stored `self.baudrate = baudrate` but this attribute was never referenced anywhere in the class. |
| **Priority** | P3 |
| **Confidence** | High |
| **Resolution** | Fixed in `openspec/changes/remove-fake-serial-baudrate-attribute/`: `self.baudrate = baudrate` removed from `FakeSerial.__init__` (line 80). `baudrate` parameter preserved in signature for API compatibility with `serial.Serial`. Three test assertions removed from `test_readback_diagnostic.py` (lines 704, 834, 1160). All 73 tests pass. |

### BUG-012: `test_v04.py` imports from external project path

| Field        | Value |
|--------------|-------|
| **Status**   | Open (test maintenance) |
| **File(s)**  | `src/calibration/test_v04.py` line 9 |
| **Impact**   | Test is inapplicable to the current project. |
| **Description** | `sys.path.insert(0, "/home/mathomp/Documents/Development/MotionSimProjects/h3_wt901c_characterization_v0.1")` imports from an external project. The test is a copy of v0.4 code from an earlier project iteration. |
| **Priority** | P3 |
| **Confidence** | High |

### BUG-013: `test_v04.py` calls undefined `test_readback_poller()`

| Field        | Value |
|--------------|-------|
| **Status**   | Open (test maintenance) |
| **File(s)**  | `src/calibration/test_v04.py` line 522 |
| **Impact**   | Running `python test_v04.py` raises `NameError: name 'test_readback_poller' is not defined`. |
| **Description** | The `main()` function calls `test_readback_poller()` at line 522, but this function is never defined in the file. This is a standalone test entry point, not part of any CI/CD pipeline. |
| **Priority** | P3 |
| **Confidence** | High |

### BUG-014: `analyze_h3_characterization.py` assumes UTF-8 with optional BOM

| Field        | Value |
|--------------|-------|
| **Status**   | Open (code quality) |
| **File(s)**  | `analysis/analyze_h3_characterization.py` line 23 |
| **Impact**   | None in practice. Input is validated. |
| **Description** | Uses `encoding="utf-8-sig"` which silently strips BOM. The tool validates required columns (lines 224–229), which catches most encoding mismatches with a clear error. |
| **Priority** | P3 |
| **Confidence** | Low |

---

### BUG-016: TX/RX buffer separation analysis
1. **Buffer tracing**: Inspected all FakeSerial methods (`__init__`, `write`, `read`, `reset_input_buffer`, `flush`, `close`) confirming `_input_buffer` and `_output_buffer` are never read from in `write()` or `read()`. The actual data flow uses `_response_list` (RX) and `_write_history` (TX observation).
2. **Response generation tracing**: Confirmed `write()` appends `self.responses[self._response_counter]` (canned response from constructor argument) to `_response_list`, not the write argument itself.
3. **Read path isolation**: Confirmed `read()` only reads from `_response_list` and returns `b""` when empty. No code path allows write data to enter `_response_list`.
4. **Test coverage review**: Verified existing tests (`test_fake_serial_responses`, `test_normal_passive_cli_execution`, `test_single_motor_cli_execution`, `test_response_request_association`) exercise the TX/RX flow and would detect any TX→RX data leakage.

## Appendix: Re-Verification Methodology

1. **Protocol verification (BUG-001):** Compared READ_COMMANDS byte values between `h3_characterize.py` and `smc3_readback_diagnostic.py` against the ChatGPT-archive reference implementation (`smc3.py` line 48) and the November 14, 2026 H3 readback investigation (which confirmed uppercase `[rdA]`, `[rdB]`, `[rdC]` work).

2. **Call graph tracing (BUG-002, BUG-004):** Verified `send_request()` is never called (grep returns only definition). Verified `run_active()` overwrites `self.motor` with its parameter at line 739.

3. **Stats accumulation trace (BUG-003):** Executed Python simulation of the `dict.update()` pattern confirming stats accumulate correctly across motor iterations.

4. **pyserial behavior (BUG-006):** Verified pyserial 3.5 `flush()` documentation — it only waits for output completion, does not discard input.

5. **Directory structure verification (BUG-008):** Confirmed timestamped subdirectories (`%Y-%m-%d_%H-%M-%S`) are created per run, preventing file collision.

6. **Sweep output calculation (BUG-015):** Computed sweep output for multiple step/limit combinations confirming duplicates match the documented expected behavior.

7. **Timeout path tracing (BUG-005):** Traced all `poll_motor()` call sites confirming `DEFAULT_TIMEOUT` (0.10) is hardcoded instead of `args.read_timeout`.

## Appendix: Files Inspected

| File | Lines | Notes |
|------|-------|-------|
| `src/calibration/h3_characterize.py` | ~540 | Main characterization tool |
| `src/calibration/smc3_readback_diagnostic.py` | ~1420 | Readback diagnostic utility |
| `src/calibration/test_readback_diagnostic.py` | ~3177 | Diagnostic test suite (68 test functions) |
| `src/calibration/test_fake_serial.py` | ~200 | Fake serial tests |
| `src/calibration/test_v04.py` | ~320 | v0.4 legacy tests |
| `analysis/analyze_h3_characterization.py` | ~145 | Analysis tool |
| `ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/smc3.py` | ~200 | Reference implementation |
| `reports/SMC3_READBACK_INVESTIGATION_2026-11-14.md` | ~350 | November 14, 2026 investigation |

## Changes from Original Audit

| Change | Details |
|--------|---------|
| **Rejected** | BUG-002 (double write), BUG-003 (stats loss), BUG-004 (KeyError), BUG-006 (flush discards input), BUG-008 (CSV duplication), BUG-015 (sweep duplicates), BUG-016 (FakeSerial TX/RX concern) |
| **Downgraded** | BUG-007: P2 → P3 (dead code, not functional) |
| **Reclassified** | BUG-009, BUG-010, BUG-011, BUG-014: confirmed as code-quality observations |
| **Reclassified** | BUG-012, BUG-013: confirmed as test-maintenance issues |
| **Retained** | BUG-001: P0 confirmed (protocol mismatch) |
| **Retained** | BUG-005: P2 confirmed (timeout ignored) |
| **Resolved** | BUG-011: P3 resolved — removed dead `FakeSerial.baudrate` attribute and test assertions |
| **Totals updated** | Confirmed: 2, Rejected: 6, Code quality/test maintenance: 4, Resolved: 2 |
