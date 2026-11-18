# Design

## Context

The `smc3_readback_diagnostic.py` module uses two distinct patterns for selecting mode strings:

- **Correct pattern** (lines 1050, 1257): `"ACTIVE" if args.active_target_test else "PASSIVE"` — proper ternary.
- **Fragile pattern** (lines 1176, 1355): `args.active_target_test and "ACTIVE" or "PASSIVE"` — the `and`/`or` idiom.

The fragile idiom works only because `"ACTIVE"` is truthy. It would fail silently if a future mode name were falsy.

## Goals / Non-Goals

**Goals:**
- Replace both fragile `and`/`or` expressions with proper ternary conditionals.
- Achieve consistency with the correct pattern already used elsewhere in the file.

**Non-Goals:**
- No behavioral changes.
- No test modifications.
- No changes to `stats["mode"]` consumers (none exist).

## Decisions

1. **Use ternary, not a helper function.** The pattern is simple and appears only twice. A helper function would add indirection without benefit.
2. **Preserve the `"SIMULATION_"` prefix** on line 1176 by applying the ternary inside the concatenation: `"SIMULATION_" + ("ACTIVE" if args.active_target_test else "PASSIVE")`.
3. **No test changes.** No test asserts on `stats["mode"]` values. The existing test suite (`test_readback_diagnostic.py`, 73 tests) validates behavior independently of this string.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| None — the change is a 1:1 semantic replacement | Existing 73 tests pass without modification |

## Migration Plan

Single-file, two-line edit. No migration or rollback needed — the change is atomic and reversible.

## Open Questions

None.
