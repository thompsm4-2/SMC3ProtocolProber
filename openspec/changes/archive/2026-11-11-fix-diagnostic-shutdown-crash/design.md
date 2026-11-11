# Design

## Context

`DiagnosticSession._cleanup()` (lines 211–224 of `smc3_readback_diagnostic.py`) checks `self.serial._closed` to determine whether to call `self.serial.close()`. The `FakeSerial` test stub defines `_closed` as its attribute, but real pySerial `serial.Serial` objects expose `closed` (public API). This mismatch causes an `AttributeError` when the diagnostic runs with real hardware and attempts cleanup on shutdown.

## Goals / Non-Goals

**Goals:**
- Fix the `AttributeError` in `_cleanup()` so it works with both real pySerial and `FakeSerial`.
- Preserve existing test behavior (tests assert on `ser._closed`).
- Ensure cleanup is safe when serial is `None` or already closed.

**Non-Goals:**
- No changes to the diagnostic's main polling or active-test logic.
- No changes to `FakeSerial`'s public API or test contract.
- No changes to output file cleanup or other session state.

## Decisions

### Decision: Use `hasattr` to check for `closed` attribute

**Choice**: Replace `self.serial._closed` with `getattr(self.serial, 'closed', getattr(self.serial, '_closed', True))`.

**Rationale**: The `FakeSerial` stub uses `_closed` while pySerial uses `closed`. Using `getattr` with a fallback checks the public API first, then falls back to the private attribute. This preserves compatibility with both implementations without requiring changes to `FakeSerial`.

**Alternatives considered**:
1. **Change `FakeSerial` to use `closed`**: Would align with pySerial's API but requires updating all test assertions that reference `ser._closed`. Higher risk of test breakage.
2. **Always call `close()` without checking**: pySerial's `close()` is idempotent and safe to call multiple times. However, this is less explicit about intent and doesn't match the existing code's pattern of checking before closing.
3. **Try/except AttributeError**: Catch the error and fall back. Less clear intent than explicit attribute checking.

### Decision: Keep existing exception handling

The existing `try/except Exception: pass` around `self.serial.close()` is retained. No changes to error handling strategy.

### Decision: No changes to FakeSerial

`FakeSerial` continues to use `_closed` internally. The fix in `_cleanup()` accommodates both attribute names, so `FakeSerial` remains unchanged.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Tests assert on `ser._closed` directly (e.g., `assert ser._closed, ...`) | These assertions are on the `FakeSerial` object itself, not on `_cleanup()`. Since `FakeSerial` is unchanged, these assertions remain valid. |
| `getattr` fallback adds minor complexity | The fallback is a single line and well-documented. The alternative (changing `FakeSerial`) would require more widespread test changes. |
| `FakeSerial._closed` and pySerial `closed` have different semantics | Both are boolean flags indicating open/closed state. The behavior is equivalent for the purpose of this check. |

## Migration Plan

This is a bug fix with no migration steps. The change is:
1. Edit `DiagnosticSession._cleanup()` in `smc3_readback_diagnostic.py`.
2. Run existing tests to verify no regressions.

## Open Questions

None.
