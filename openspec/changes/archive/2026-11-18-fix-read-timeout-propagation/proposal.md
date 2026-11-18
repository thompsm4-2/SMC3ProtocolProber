# Proposal

## Why

The `--read-timeout` CLI option on the SMC3 readback diagnostic utility does not control the response collection timeout used by `poll_motor()`. All call sites pass the hardcoded `DEFAULT_TIMEOUT` (0.10 s) instead of `args.read_timeout`. Users who set `--read-timeout` to a different value observe no change in response collection behavior, making the option misleading. This bug prevents users from tuning the polling timeout for noisy or slow serial links.

## What Changes

- Add a `timeout` parameter to `ReadbackDiagnostic.run_passive()` (default `DEFAULT_TIMEOUT`).
- Add a `timeout` parameter to `ReadbackDiagnostic.run_active()` (default `DEFAULT_TIMEOUT`).
- Replace all hardcoded `DEFAULT_TIMEOUT` calls to `poll_motor()` with the method's `timeout` parameter.
- In `main()`, pass `args.read_timeout` to `run_passive()` and `run_active()` for both real-hardware and simulate-mode code paths.
- Update the passive-mode print statement in `run_passive()` to display the actual timeout value instead of `DEFAULT_TIMEOUT`.

No breaking changes to the public API — all new parameters have sensible defaults matching the current behavior.

## Capabilities

### Modified Capabilities

- **diagnostic-simulation**: The requirement "Simulate mode preserves serial parameters" already asserts that `--read-timeout` is passed to `FakeSerial`. This change extends that requirement to also cover how `--read-timeout` controls the response collection deadline in `poll_motor()` during simulation.

## Impact

- **Files**: `src/calibration/smc3_readback_diagnostic.py` (methods `run_passive`, `run_active`, and `main()` in both simulate and real-hardware branches).
- **Tests**: Existing tests in `test_readback_diagnostic.py` call `run_passive()` and `run_active()` without a `timeout` parameter, so they inherit the default `DEFAULT_TIMEOUT` and continue to pass. No test changes required.
- **Behavior**: Users who set `--read-timeout` to a value other than 0.10 s will now observe the expected change in response collection timeout. Users who rely on the default 0.10 s behavior see no change.
