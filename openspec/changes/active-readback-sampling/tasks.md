# Tasks

## 1. Add CLI argument and parameter wiring

- [ ] 1.1 Add `--active-samples` CLI argument to `parse_args()` with default 5 and verify the argument appears in `--help` output
- [ ] 1.2 Add `sample_count` parameter to `run_active()` signature with default 5 and verify the parameter is threaded through from CLI args

## 2. Implement multi-sample collection loop in run_active()

- [ ] 2.1 Replace the single `poll_motor()` call (line 729) with a loop that collects `sample_count` samples at evenly-spaced intervals (`settling_delay / sample_count`) and verify the loop runs the correct number of times with `sample_count=3`
- [ ] 2.2 Each loop iteration calls `poll_motor(DEFAULT_TIMEOUT, 0.05)` and logs the result via `session.log_active_test()` with `sample_index` and `sample_timestamp` fields, and verify that 3 distinct rows are written for 3 samples

## 3. Update log_active_test() and CSV schema

- [ ] 3.1 Add `sample_index` and `sample_timestamp` parameters to `DiagnosticSession.log_active_test()` and verify new parameter values are accepted
- [ ] 3.2 Add `sample_index` and `sample_timestamp` to the active test CSV header (after `readback_sample` or at the end) and verify the new columns appear in the CSV output
- [ ] 3.3 Write sample rows including the new columns and verify column order and values are correct

## 4. Handle per-sample readback failures

- [ ] 4.1 When `poll_motor()` returns False for a sample, log a row with `decode_status="ERROR"`, null decoded fields, and the current `sample_index`/`sample_timestamp`, and verify the row is written to the CSV
- [ ] 4.2 After logging an ERROR sample, continue the sampling loop for remaining samples and verify subsequent samples are still collected
- [ ] 4.3 When all samples for a step fail, verify all N ERROR rows are written and the step completes (no crash)

## 5. Update existing tests

- [ ] 5.1 Update active test transmission tests to provide `sample_count × target_count` canned responses for simulation mode and verify the updated tests pass
- [ ] 5.2 Add test for default sample count (5) in simulation mode and verify 5 samples are collected per step
- [ ] 5.3 Add test for configurable sample count (`--active-samples 3`) and verify exactly 3 samples are collected per step
- [ ] 5.4 Add test for evenly-spaced sampling timing and verify sample intervals are approximately `settling_delay / sample_count`
- [ ] 5.5 Add test for sample_index values (0 through N-1) and verify correct zero-based indexing
- [ ] 5.6 Add test for sample_timestamp recording and verify ISO 8601 format timestamps
- [ ] 5.7 Add test for readback failure producing ERROR sample with null decoded fields and verify the ERROR row is written
- [ ] 5.8 Add test for readback failure not breaking the sampling loop and verify remaining samples continue after a failure
- [ ] 5.9 Verify existing active test tests (target sequence, position clamping, transmitted_hex) still pass unchanged

## 6. Verify and document

- [ ] 6.1 Run the full test suite (`python test_readback_diagnostic.py`) and verify all tests pass
- [ ] 6.2 Run Python syntax check on modified `smc3_readback_diagnostic.py` and verify no import or syntax errors
