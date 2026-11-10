# Tasks

## 1. Add CLI flags

- [x] 1.1 Add `--simulate` flag (action store_true) and `--simulate-response` flag (append, metavar="HEX") to the argparse parser in `main()`
- [x] 1.2 Add `--simulate-count` flag (type=int, default=10, metavar="N") to the argparse parser
- [x] 1.3 Verify `python smc3_readback_diagnostic.py --help` shows the three new flags with correct descriptions

## 2. Implement simulate-mode routing in main()

- [x] 2.1 After argument validation, add a `simulate` branch that sets `serial_factory` to a factory producing `FakeSerial` with the provided parameters and canned responses
- [x] 2.2 Parse each `--simulate-response` hex string into bytes and store as the `responses` list for `FakeSerial`
- [x] 2.3 In simulate mode, track a request counter and stop the diagnostic when it reaches `--simulate-count`; this is independent of `--duration` (count is a request counter, not a time duration)
- [x] 2.4 Handle `--motor ALL` in simulate mode with round-robin distribution: cycle through motors A, B, C in order, distributing `--simulate-count` total requests evenly
- [x] 2.5 Verify: `python smc3_readback_diagnostic.py --simulate --simulate-response "5B 72 64 41 5D" --simulate-count 1 --motor A --port /dev/null` runs without error and exits 0

## 3. Skip hardware prompts and detection in simulate mode

- [x] 3.1 In simulate mode, skip the `--list-devices` block (no devices to list) and proceed directly to session creation
- [x] 3.2 In simulate mode with `--active-target-test`, skip the hardware confirmation prompt
- [x] 3.3 In simulate mode without `--port`, do not attempt serial device enumeration; use a dummy port string (e.g., `/dev/null`) for `FakeSerial` — `--port` is optional in simulate mode
- [x] 3.4 Define `--simulate-count 0` behavior: unlimited in passive mode (existing `--duration 0` behavior); full fixed sequence in active-target-test mode (no early termination)
- [x] 3.5 Verify: `python smc3_readback_diagnostic.py --simulate --simulate-count 1 --motor A` runs without asking for confirmation or listing devices

## 4. Skip file I/O in simulate mode

- [x] 4.1 In simulate mode, create a no-op `DiagnosticSession` by defining an inline subclass in `main()` that overrides `_setup_output_files()` and `write_summary()` as no-ops — so no CSV logs, raw logs, or summary files are created
- [x] 4.2 In simulate mode, skip `DiagnosticSession.write_summary()` — instead, print the summary dict to stdout
- [x] 4.3 Print a warning header "SIMULATION MODE — no hardware connected" before starting the simulation
- [x] 4.4 Verify: running in simulate mode does not create any diagnostic files in the configured `--output-dir`
- [x] 4.5 Verify that no other `DiagnosticSession` methods write CSV or raw records during simulation; if another file-writing method is discovered, report the finding and implement only a simulation-specific bypass consistent with the approved design (no silent broadening or modification of `DiagnosticSession`)

## 5. Add simulation summary output

- [x] 5.1 After simulation completes, print a summary to stdout showing: mode ("SIMULATION"), total requests, successful responses, timeouts, and errors (matching the format of `write_summary`)
- [x] 5.2 Include the motor(s) and simulate count in the summary
- [x] 5.3 Verify: the stdout summary contains the expected fields and matches the stats tracked by `ReadbackDiagnostic`

## 6. Add unit tests

- [x] 6.1 Add `test_simulate_flag_enabled()` that verifies `--simulate` sets the correct internal state (no real serial opened)
- [x] 6.2 Add `test_simulate_responses_fifo()` that provides multiple `--simulate-response` values and verifies FIFO delivery
- [x] 6.3 Add `test_simulate_count_limits_requests()` that verifies `--simulate-count 3` produces exactly 3 requests
- [x] 6.4 Add `test_simulate_no_output_files()` that verifies no files are created when `--simulate` is enabled
- [x] 6.5 Add `test_simulate_skips_confirmation()` that verifies the hardware confirmation prompt is skipped
- [x] 6.6 Add `test_simulate_all_motors_round_robin()` that verifies round-robin motor distribution and stdout summary output with `--motor ALL`
- [x] 6.7 Run the new tests and verify all pass (32 existing + 6 new = 38 total)

## 7. Regression verification

- [x] 7.1 Run the full existing test suite (`python test_readback_diagnostic.py`) and verify all 32 existing tests still pass (38 total with new tests)
- [x] 7.2 Run `python smc3_readback_diagnostic.py --help` and verify existing flags are unchanged
- [x] 7.3 Verify that running without `--simulate` behaves identically to pre-change behavior (uses `serial.Serial`)
