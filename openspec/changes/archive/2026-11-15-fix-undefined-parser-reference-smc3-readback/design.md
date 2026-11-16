# Design: Fix Undefined Parser Reference

## Context

The `parse_args()` function in `smc3_readback_diagnostic.py` creates an `argparse.ArgumentParser` as a local variable and returns the parsed namespace. The `main()` function contains two validation checks that call `parser.error()`, but `parser` is not defined in `main()`'s scope.

Current state:
- `parse_args()` has local `parser` variable, returns `args`
- `main()` has two unreachable validation blocks that reference `parser.error()` (lines ~1242 and ~1254)
- The third validation (`--motor must contain A, B, C, or ALL`) uses `parser.error()` but works because it's in the same code path where `parser` would need to be defined — but it also fails with `NameError` unless I'm wrong. Let me re-check.

Actually, looking at the code more carefully:
- Line 1242: `parser.error("--active-target-test requires --active-motor")` — in `main()`, `parser` is NOT defined → `NameError`
- Line 1250: `parser.error("--motor must contain A, B, C, or ALL")` — in `main()`, `parser` is NOT defined → `NameError`
- Line 1254: `parser.error("--polling-rate must be > 0")` — in `main()`, `parser` is NOT defined → `NameError`

Wait, the user's task description says to leave the empty-motor-list check unchanged. Let me re-read the code...

The user says: "Leave the existing empty-motor-list check unchanged: `if not motors: parser.error("--motor must contain A, B, C, or ALL")`"

This is confusing — that check also uses `parser.error()` and would also raise `NameError`. But the user explicitly says to leave it unchanged. Perhaps this check is never reached in practice because `parse_motor_arg()` is called with a valid motor string, or perhaps the user is aware of this but considers it out of scope.

For this change, I'll follow the user's explicit instructions: move only the two specified checks into `parse_args()` and leave the empty-motor-list check as-is.

## Goals / Non-Goals

**Goals:**
- Move the `--active-target-test` requires `--active-motor` validation into `parse_args()`
- Move the `--polling-rate > 0` validation into `parse_args()`
- Remove the corresponding checks from `main()`
- Add regression tests that verify invalid arguments are rejected before serial initialization
- Update `test_active_samples_cli_argument` to include `--active-motor A`

**Non-Goals:**
- Fix the empty-motor-list check (out of scope per user request)
- Add new CLI arguments
- Change any other validation logic
- Modify any files outside the two authorized files

## Decisions

### Decision 1: Move validation into `parse_args()` instead of passing `parser` to `main()`

**Choice**: Insert validation checks after `parser.parse_args()` and before returning `args` in `parse_args()`.

**Rationale**:
- Keeps the parser local to `parse_args()`, following the existing pattern
- `parser.error()` raises `SystemExit(2)` which is the standard argparse behavior
- Tests can call `main()` with invalid arguments and expect `SystemExit(2)` — argparse handles this automatically
- No need to change the function signature of `main()`

**Alternatives considered**:
1. Pass `parser` to `main()` — breaks encapsulation, makes the function signature more complex
2. Use `sys.exit()` instead of `parser.error()` — loses the standard argparse error formatting
3. Make `parser` module-level — not recommended by argparse docs, causes issues with multiple calls

### Decision 2: Use `parser.error()` in `parse_args()` validation

**Choice**: Use `parser.error()` which raises `SystemExit(2)` with a formatted error message on stderr.

**Rationale**:
- Standard argparse behavior — exit code 2, formatted error message
- Existing tests already assert `SystemExit(2)` for invalid arguments
- Error message format is consistent with other argparse errors (e.g., `--help`, unknown arguments)

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Moving validation changes the exit path (from `main()` to `parse_args()`) | `parser.error()` raises `SystemExit(2)` in both cases; behavior is identical from caller's perspective |
| Tests that previously relied on `NameError` will fail | No existing tests rely on `NameError`; the bug was undiscovered |
| The empty-motor-list check still has the same `NameError` bug | Out of scope per user request; will be addressed in a separate change |

## Migration Plan

No migration needed. This is a bug fix that corrects broken validation. No data changes, no API changes, no configuration changes.

## Open Questions

None. The approach is straightforward and the user's instructions are explicit.
