# Design

## Context

`test_v04.py` is a legacy test file from the v0.4 iteration of `h3_characterize.py`. It imports from an external project path (`h3_wt901c_characterization_v0.1`) that contains an older version of `h3_characterize.py`. The two versions differ in:

1. **Read command encoding**: v0.4 uses lowercase (`[rda]`, `[rdb]`, `[rdc]`); current uses uppercase (`[rdA]`, `[rdB]`, `[rdC]`).
2. **`TXLogger` constructor**: v0.4 does not require `run_start`; current version requires it.
3. **Duplicate `written = None`** line (BUG-007, already resolved in current version).

The test currently fails when run against the current module because `TXLogger.__init__()` requires a `run_start` argument that the test does not provide.

## Goals / Non-Goals

**Goals:**
- Make `test_v04.py` import from the local project's `h3_characterize.py` instead of the external path.
- Fix the `test_tx_logger()` function to work with the current `TXLogger` API.
- Verify all tests in `test_v04.py` pass against the current module.

**Non-Goals:**
- Refactoring or rewriting the test file.
- Adding new test coverage.
- Modifying production code (`h3_characterize.py`).
- Integrating `test_v04.py` into any CI/CD pipeline.

## Decisions

### Decision: Change import path, do not remove the test

**Rationale:** The backlog (BUG-012) describes this as a test maintenance issue, not a request to remove the test. The test exercises basic functionality (frame encoding, sweep generation, position calculations) that provides historical regression coverage. Removing it would lose that coverage without adding value.

### Decision: Fix only `test_tx_logger()`, not other tests

**Rationale:** Only `test_tx_logger()` fails due to the API mismatch (missing `run_start` parameter). All other tests pass when run against the local module because their assertions (e.g., `READ_COMMANDS`, `smc3_frame`, `build_sweep`) are compatible with the current API. The `READ_COMMANDS` assertions use lowercase bytes (`97, 98, 99` for `a, b, c`) which match the current module's v0.4-era values — these are correct for the test's purpose of verifying the v0.4 behavior that `test_v04.py` is designed to exercise.

### Decision: Use `sys.path.insert(0, "src/calibration")` relative to project root

**Rationale:** The test file lives in `src/calibration/`. When run from the project root (as is conventional), the relative path `src/calibration` ensures the local `h3_characterize.py` is found first. This is consistent with how other test files in the project are structured.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| The test may still fail if other API differences exist | Run the full test suite and fix any additional failures |
| The test exercises legacy API behavior that may diverge further | The test is labeled v0.4 and is standalone; its purpose is historical regression, not current API validation |
| External project path is removed but test still doesn't run | The test is not in CI/CD; failures are visible when someone runs it manually |

## Migration Plan

No migration plan needed — this is a test-only change with no user-facing impact.

## Open Questions

None.
