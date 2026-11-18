# Design

## Context

`poll_motor(timeout, interval, delay)` accepts a `timeout` parameter that sets the response collection deadline (`deadline = start + timeout`). However, every call site passes `DEFAULT_TIMEOUT` (0.10 s) instead of `args.read_timeout`. The `--read-timeout` CLI argument is only used to configure the serial port's `timeout` attribute, not the response collection deadline.

The relevant code paths are:
1. `run_passive()` — the passive polling loop (single motor and ALL motors)
2. `run_active()` — the active target-resolution test
3. `main()` — the CLI entry point, which branches into simulate and real-hardware modes

## Goals / Non-Goals

**Goals:**
- Make `--read-timeout` actually control the response collection timeout in `poll_motor()`.
- Preserve backward compatibility: default behavior (0.10 s) is unchanged.
- Cover all code paths: simulate mode, real-hardware mode, single motor, ALL motors, passive, and active.

**Non-Goals:**
- Changing `DEFAULT_TIMEOUT`'s value.
- Adding new CLI arguments.
- Fixing other pre-existing bugs (e.g., `test_all_motor_cli_execution` timing issue).
- Modifying `poll_motor()`'s signature or internal logic.

## Decisions

### Decision 1: Add `timeout` parameter to `run_passive()` and `run_active()`

**Choice**: Add an optional `timeout` parameter with default `DEFAULT_TIMEOUT` to both methods.

**Rationale**:
- Minimal change: existing callers (including tests) that don't pass `timeout` inherit the current behavior.
- `run_passive()` already accepts `duration`, `polling_rate`, and `delay` as parameters. Adding `timeout` fits the existing pattern.
- `run_active()` already accepts `motor`, `targets`, `settling_delay`, and `sample_count`. Adding `timeout` is consistent.

**Alternatives considered**:
- *Modify `poll_motor()` to read `self.ser.timeout`*: Would require setting `self.ser.timeout` before calling `poll_motor()`, but `self.ser` is injected (could be `FakeSerial` or `serial.Serial`). Also, `FakeSerial.timeout` is the serial port timeout, not the response collection deadline — they are separate concerns.
- *Add a `set_timeout()` method on `ReadbackDiagnostic`*: More indirection, no benefit over a direct parameter.
- *Change `DEFAULT_TIMEOUT` globally*: Would be a breaking change for all users; not a targeted fix.

### Decision 2: Pass `args.read_timeout` from `main()` to both methods

**Choice**: In `main()`, pass `args.read_timeout` as the `timeout` argument to both `run_passive()` and `run_active()`.

**Rationale**:
- `args.read_timeout` is already parsed with `default=DEFAULT_TIMEOUT`, so the default value is correct.
- Both simulate and real-hardware branches in `main()` need the same fix.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Existing tests that call `run_passive()` or `run_active()` without a `timeout` argument may behave differently if `DEFAULT_TIMEOUT` changes | `DEFAULT_TIMEOUT` value is unchanged; default parameter preserves current behavior. Tests pass `timeout=0.1` or `timeout=0.05` directly to `poll_motor()`, not through `run_passive()`/`run_active()`. |
| Users with slow serial links may need to increase `--read-timeout` beyond 0.10 s | This is the intended behavior — the fix exposes the tuning capability that was already advertised but not functional. |
| `FakeSerial` in simulate mode uses `timeout` for both serial port timeout and response collection deadline | `FakeSerial.read()` returns canned responses immediately (no actual I/O blocking), so the serial port timeout has no practical effect in simulate mode. The response collection deadline is the only effective timeout. This is correct behavior. |

## Migration Plan

No migration needed. The change is a bug fix that makes existing CLI behavior match user expectations. Default behavior (0.10 s) is unchanged.

## Open Questions

None. All implementation details are resolved by the codebase inspection.
