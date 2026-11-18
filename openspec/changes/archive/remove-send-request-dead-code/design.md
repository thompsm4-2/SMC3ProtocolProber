# Design

## Context

The `send_request()` method (line 447 in `smc3_readback_diagnostic.py`) is a method on the `ReadbackDiagnostic` class that:
1. Constructs a readback request from `READ_COMMANDS[self.motor]`
2. Writes it to the serial port via `self.serial.write()`
3. Flushes the serial port
4. Returns `(b"", written)` — an empty bytes response with the byte count

It was likely created as part of the original diagnostic tool design but was never wired into the actual polling flow. The real implementation uses inline write logic inside `poll_motor()` (line 509).

## Goals / Non-Goals

**Goals:**
- Remove the dead `send_request()` method cleanly.

**Non-Goals:**
- Refactoring `poll_motor()` or its write logic.
- Adding tests for the removed method.
- Investigating whether `send_request()` was intended to be used (it was not; `poll_motor()` handles all write logic inline).

## Decisions

**Decision:** Remove the method entirely (lines 447–457).

**Alternatives considered:**
1. **Keep and suppress with `# noqa`** — Rejected. Adds noise without value.
2. **Rename to `_deprecated_send_request`** — Rejected. Still dead code, just with a different name.
3. **Remove and add a test asserting it doesn't exist** — Rejected. Over-engineering for 10 lines of dead code.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Accidentally removing a method that IS called | Exhaustive grep confirmed zero callers across the entire codebase (all `.py`, `.yaml`, `.yml`, `.json`, `.txt` files) |
| Test file references | Confirmed zero references in any `test_*.py` file |
