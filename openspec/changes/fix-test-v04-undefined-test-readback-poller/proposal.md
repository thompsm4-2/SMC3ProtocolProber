# Proposal

## Why

The `main()` function in `src/calibration/test_v04.py` calls `test_readback_poller()` at line 522, but this function is never defined in the file. An archived OpenSpec change (`2026-11-08-replace-failing-readback-poller-test`) replaced the original `test_readback_poller()` test with five new replacement tests, but never removed the dangling call from `main()`. This causes a `NameError` when running `python test_v04.py`, masking the file as broken even though all 13 replacement tests are valid and complete.

## What Changes

- **Remove** the call to `test_readback_poller()` from the `main()` function in `src/calibration/test_v04.py` (line 522)
- No other code changes — the five replacement tests (`test_context_manager_entry_exit`, `test_successful_poll_motor`, `test_poll_motor_timeout`, `test_poll_due_interval`, `test_poll_now_immediate`) already exist and are called by their correct names

## Capabilities

No spec-level behavior changes. This is a pure test maintenance fix.

## Impact

- **Affected file:** `src/calibration/test_v04.py` (line 522 only)
- **Not affected:** No other test files, no production code, no CI/CD pipeline (test_v04.py is standalone)
- **Risk:** Zero — the call is to a non-existent function; removing it eliminates a guaranteed runtime error
