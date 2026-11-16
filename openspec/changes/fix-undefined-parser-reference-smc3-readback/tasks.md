# Tasks

## 1. Move validation into `parse_args()`

- [ ] 1.1 In `src/calibration/smc3_readback_diagnostic.py`, insert `--active-target-test` requires `--active-motor` validation after `parser.parse_args()` and before `return args` in `parse_args()`, then verify the check is present in the function
- [ ] 1.2 In `src/calibration/smc3_readback_diagnostic.py`, insert `--polling-rate` must be positive validation after `parser.parse_args()` and before `return args` in `parse_args()`, then verify the check is present in the function

## 2. Remove validation from `main()`

- [ ] 2.1 Remove the two validation blocks from `main()` (the `--active-target-test` requires `--active-motor` check and the `--polling-rate > 0` check), then verify they are no longer present in `main()`. Leave the empty-motor-list check unchanged.

## 3. Update existing test

- [ ] 3.1 In `src/calibration/test_readback_diagnostic.py`, update `test_active_samples_cli_argument` to include `--active-motor A` in the argument list that contains `--active-target-test`, then verify the test still passes

## 4. Add regression tests

- [ ] 4.1 In `src/calibration/test_readback_diagnostic.py`, add `test_active_target_test_requires_active_motor` that calls `main()` with `--active-target-test` but without `--active-motor`, asserts `SystemExit(2)`, captures stderr for the error message, and injects a serial factory that raises an assertion if called — then verify the test fails before the fix and passes after
- [ ] 4.2 In `src/calibration/test_readback_diagnostic.py`, add `test_polling_rate_must_be_positive` that calls `main()` with `--polling-rate 0`, asserts `SystemExit(2)`, captures stderr for the error message, and injects a serial factory that raises an assertion if called — then verify the test fails before the fix and passes after

## 5. Verification

- [ ] 5.1 Run both new regression tests (4.1 and 4.2) and verify they pass
- [ ] 5.2 Run the complete existing test suite (`python test_readback_diagnostic.py`) and verify all tests pass
- [ ] 5.3 Run Python syntax compilation on both modified files (`python -m py_compile smc3_readback_diagnostic.py` and `python -m py_compile test_readback_diagnostic.py`) and verify no syntax errors
- [ ] 5.4 Run the diagnostic script with `--help` and verify successful output (exit code 0)
- [ ] 5.5 Verify the Git diff shows changes only in the two authorized files
