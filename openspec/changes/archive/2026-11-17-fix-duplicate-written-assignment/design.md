# Design

## Context

`send_command()` in `src/calibration/h3_characterize.py` has two consecutive `written = None` assignments at lines 220–221. The second assignment is redundant — it overwrites the first with the same value before `written` is reassigned by `ser.write(command)` on the following line.

## Goals / Non-Goals

**Goals:**
- Remove the duplicate `written = None` assignment (line 221).
- Preserve all existing behavior.

**Non-Goals:**
- No refactoring of `send_command()` beyond the duplicate removal.
- No test changes — the existing behavior is unchanged.

## Decisions

1. **Delete line 221, keep line 220.** The first `written = None` is the canonical initialization. There is no code path between the two assignments that would justify a re-initialization.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Accidentally removing the wrong line | Both lines are identical; either removal is correct. |
| Off-by-one line number after edit | Verified with `read` — only two consecutive identical lines exist. |

No migration plan or open questions.
