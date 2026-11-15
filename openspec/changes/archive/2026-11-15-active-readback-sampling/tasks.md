# Tasks

## 1. Add CLI argument and parameter wiring

- [x] 1.1 Add `--active-samples` CLI argument to `parse_args()` with default 5 and verify the argument appears in `--help` output
- [x] 1.2 Add `sample_count` parameter to `run_active()` signature with default 5 and verify the parameter is threaded through from CLI args

## 2. Implement multi-sample collection loop in run_active()

- [x] 2.1 Replace the single `poll_motor()` call (line 729) with a loop that collects `sample_count` samples at evenly-spaced intervals (`settling_delay / sample_count`) and verify the loop runs the correct number of times with `sample_count=3`
- [x] 2.2 Each loop iteration calls `poll_motor(DEFAULT_TIMEOUT, 0.05)` and logs the result via `session.log_active_test()` with `sample_index` and `sample_timestamp` fields, and verify that 3 distinct rows are written for 3 samples

## 3. Update log_active_test() and CSV schema

- [x] 3.1 Add `sample_index` and `sample_timestamp` parameters to `DiagnosticSession.log_active_test()` and verify new parameter values are accepted
- [x] 3.2 Add `sample_index` and `sample_timestamp` to the active test CSV header (after `readback_sample` or at the end) and verify the new columns appear in the CSV output
- [x] 3.3 Write sample rows including the new columns and verify column order and values are correct

## 4. Handle per-sample readback failures

- [x] 4.1 When `poll_motor()` returns False for a sample, log a row with `decode_status="ERROR"`, null decoded fields, and the current `sample_index`/`sample_timestamp`, and verify the row is written to the CSV
- [x] 4.2 After logging an ERROR sample, continue the sampling loop for remaining samples and verify subsequent samples are still collected
- [x] 4.3 When all samples for a step fail, verify all N ERROR rows are written and the step completes (no crash)

## 5. Update existing tests

- [x] 5.1 Update active test transmission tests to provide `sample_count × target_count` canned responses for simulation mode and verify the updated tests pass
- [x] 5.2 Add test for default sample count (5) in simulation mode and verify 5 samples are collected per step
- [x] 5.3 Add test for configurable sample count (`--active-samples 3`) and verify exactly 3 samples are collected per step
- [x] 5.4 Add test for evenly-spaced sampling timing and verify sample intervals are approximately `settling_delay / sample_count`
- [x] 5.5 Add test for sample_index values (0 through N-1) and verify correct zero-based indexing
- [x] 5.6 Add test for sample_timestamp recording and verify ISO 8601 format timestamps
- [x] 5.7 Add test for readback failure producing ERROR sample with null decoded fields and verify the ERROR row is written
- [x] 5.8 Add test for readback failure not breaking the sampling loop and verify remaining samples continue after a failure
- [x] 5.9 Verify existing active test tests (target sequence, position clamping, transmitted_hex) still pass unchanged

## 7. Add missing tests

- [x] 7.1 Add test for `sample_count=1` (single-sample mode) and verify exactly one sample per step
- [x] 7.2 Add test for default sample count when `sample_count` parameter is omitted and verify 5 samples per step
- [x] 7.3 Add test for malformed response (wrong framing/motor byte) producing ERROR sample with null decoded fields
- [x] 7.4 Add timing test using `mock.patch("time.sleep")` to verify sleep calls match `settling_delay / sample_count` interval
- [x] 7.5 Add test for `--active-samples` CLI argument parsing with custom and default values
- [x] 7.6 Fix `test_readback_failure_continues_sampling_loop` to supply mixed success/failure responses and verify both OK and ERROR rows

## 8. Implementation corrections

- [x] 8.1 Remove undocumented inter-step `time.sleep(settling_delay)` at line 812 that doubles per-step settling time
- [x] 8.2 Pass `error` parameter to `log_active_test()` — `None` for successful polls, `"timeout"` for failed polls
