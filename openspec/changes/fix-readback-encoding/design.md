# Design

## Context

The `h3_characterize.py` tool defines `READ_COMMANDS` with lowercase motor identifiers (`[rda]`, `[rdb]`, `[rdc]`). The November 14, 2026 H3 readback investigation confirmed the controller responds only to uppercase (`[rdA]`, `[rdB]`, `[rdC]`). The `smc3_readback_diagnostic.py` tool already uses the correct uppercase encoding.

## Goals / Non-Goals

**Goals:**
- Correct the three byte literals in `READ_COMMANDS` in `h3_characterize.py`.
- Add a regression test that directly asserts the correct encoding.
- Ensure the test fails with the original lowercase values and passes with the fix.

**Non-Goals:**
- Modifying response-reading or response-parsing logic.
- Modifying `smc3_readback_diagnostic.py` (already correct).
- Repairing unrelated problems in `test_v04.py` or legacy tests.
- Changing command framing, motor mapping, polling intervals, timeouts, CSV formats, or hardware behavior.

## Decisions

### Decision: Direct byte literal replacement

**Choice:** Replace the three integer byte lists in `READ_COMMANDS` with the correct uppercase values.

**Rationale:** The change is a one-to-one byte correction. No refactoring of the dictionary or its usage is needed — `poll_motor()` does a simple `READ_COMMANDS[motor]` lookup, and `classify_command()` does a reverse lookup via `.values()`. Both work with either casing; the fix only changes what bytes are transmitted.

**Alternatives considered:**
1. **Build bytes from `ord()` calls:** e.g., `bytes([91, ord("r"), ord("d"), ord("A"), 93])`. This adds indirection without benefit — the literal is simple, stable, and the current format is already clear.
2. **Use string encoding:** e.g., `b"[rdA]"` directly. This is actually cleaner and more readable than the current integer-list format. However, the existing codebase uses integer lists throughout, and switching to string literals would be a style change beyond the bug fix scope. Keeping the integer-list format minimizes diff noise.

### Decision: New test file for h3_characterize.py

**Choice:** Create `src/calibration/test_h3_characterize.py` as a standalone test file.

**Rationale:** No existing test file imports from `h3_characterize.py`. The existing `test_readback_diagnostic.py` tests only `smc3_readback_diagnostic.py`. A new file keeps the test isolated and focused.

**Alternatives considered:**
1. **Add to existing `test_fake_serial.py`:** This file tests the `FakeSerial` class used by `h3_characterize.py`, but adding `READ_COMMANDS` tests there would mix serial-mock tests with protocol-encoding tests.
2. **Add inline to `test_readback_diagnostic.py`:** This file already has `READ_COMMANDS` tests, but they import from `smc3_readback_diagnostic.py`. Adding `h3_characterize.py` tests here would mix two different modules.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Regression in `classify_command()` reverse lookup | The reverse lookup uses `READ_COMMANDS.values()`, which works with any casing. No change to lookup logic. |
| Test file not discovered by test runner | The test uses plain `assert` statements (no framework required). Can be run with `python -m pytest` or `python test_h3_characterize.py`. |
| Existing test fixtures use lowercase `[rda]` | Test fixtures in `test_readback_diagnostic.py` (e.g., `b"[rda]OK5D"`) are canned response strings, not assertions about the correct encoding. They are unaffected. |

## Migration Plan

No migration needed. This is a bug fix that corrects behavior to match the hardware-confirmed protocol. No API changes, no configuration updates.

## Open Questions

None. All technical decisions are resolved by the existing evidence (November 14, 2026 investigation) and the codebase analysis.
