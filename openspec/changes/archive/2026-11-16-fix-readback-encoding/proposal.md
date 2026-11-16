# Proposal

## Why

`h3_characterize.py` encodes SMC3 readback commands with lowercase motor identifiers (`[rda]`, `[rdb]`, `[rdc]`), but the November 14, 2026 H3 readback investigation confirmed the controller only responds to uppercase (`[rdA]`, `[rdB]`, `[rdC]`). This causes the characterization workflow to receive no valid readback data, breaking the primary diagnostic path.

## What Changes

- Correct the three values in `READ_COMMANDS` in `src/calibration/h3_characterize.py` from lowercase to uppercase motor identifiers.
- Add a regression test that asserts `READ_COMMANDS` produces exactly `b"[rdA]"`, `b"[rdB]"`, and `b"[rdC]"`.
- The regression test imports `READ_COMMANDS` directly from `h3_characterize.py`.

## Capabilities

### New Capabilities

- `smc3-readback-commands`: Defines the correct byte encoding for SMC3 readback request commands sent to the controller, establishing that uppercase motor identifiers (`[rdA]`, `[rdB]`, `[rdC]`) are required per the November 14, 2026 H3 readback investigation.

### Modified Capabilities

- _(none)_

## Impact

| Area | Details |
|------|---------|
| **Code** | `src/calibration/h3_characterize.py` — three byte literals in `READ_COMMANDS` (lines 45–47) |
| **Tests** | New test file `src/calibration/test_h3_characterize.py` — regression test for `READ_COMMANDS` encoding |
| **Behavior** | `h3_characterize.py --readback` will now receive valid controller responses instead of timeouts |
| **Risk** | Minimal — changes only the request bytes; no response parsing, framing, or hardware behavior is affected |
