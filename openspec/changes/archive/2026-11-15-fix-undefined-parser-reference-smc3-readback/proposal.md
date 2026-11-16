# Proposal: Fix Undefined Parser Reference in SMC3 Readback Diagnostic

## Why

The `main()` function in `src/calibration/smc3_readback_diagnostic.py` references `parser.error()` in two validation checks, but the `parser` variable is local to `parse_args()` and not defined in `main()`'s scope. This causes a `NameError` when the two reachable validation paths are triggered, instead of producing the expected argparse error with exit code 2. This bug makes argument validation silently fail for users who supply invalid argument combinations.

## What Changes

- **Move validation into `parse_args()`**: Two validation checks currently in `main()` (requiring `--active-motor` when `--active-target-test` is used, and requiring `--polling-rate > 0`) will be moved into `parse_args()` where the `parser` instance is available.
- **Remove validation from `main()`**: The corresponding validation blocks will be removed from `main()`.
- **Preserve existing empty-motor-list check**: The `--motor must contain A, B, C, or ALL` check remains unchanged in `main()` (it uses a different pattern that works).
- **Update existing test**: `test_active_samples_cli_argument` will be updated to include `--active-motor A` in its argument list when testing `--active-target-test`, making the arguments valid under the new validation rules.
- **Add regression tests**: Two new tests will verify that invalid arguments are rejected before serial initialization.

## Capabilities

No spec-level behavior changes. This change fixes an implementation bug where the existing validation requirements (e.g., `--active-target-test requires --active-motor`) were not functioning due to a scope error. The existing specifications already define these constraints; the implementation is being corrected to match them.

## Impact

- **Files modified**: `src/calibration/smc3_readback_diagnostic.py`, `src/calibration/test_readback_diagnostic.py`
- **Behavior change**: Invalid argument combinations that previously raised `NameError` will now produce proper argparse error messages with exit code 2.
- **Risk**: Low. The change is narrowly scoped to two files. The validation logic itself is unchanged — only its location is moved.
