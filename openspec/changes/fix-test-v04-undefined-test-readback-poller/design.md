# Design

## Context

`test_v04.py` is a standalone legacy test file for the v0.4 iteration of `h3_characterize.py`. It is not part of any CI/CD pipeline, pytest configuration, or test discovery mechanism. The file currently has 13 defined test functions, but `main()` calls 14 test functions — the 14th being `test_readback_poller()`, which was removed by a previous OpenSpec change but whose call was never removed.

## Goals / Non-Goals

**Goals:**
- Remove the dangling call to `test_readback_poller()` from `main()` so the file no longer raises `NameError` at runtime

**Non-Goals:**
- Do not modify any of the 13 existing test functions
- Do not add new tests
- Do not modify `test_tx_logger()` (which has a separate pre-existing failure due to a missing `run_start` argument — that is BUG-012's domain)
- Do not remove the entire file or reorganize its structure

## Decisions

**Decision:** Single-line removal — delete line 522 (`test_readback_poller()`) from `main()`.

**Rationale:**
- The function is never defined anywhere in the file or any other `.py` file in the project
- The five replacement tests already exist and are called by their correct names
- No other code references `test_readback_poller` (confirmed via grep across all `.py`, `.md`, `.yaml`, `.json`, `.sh` files)
- The file is not imported or referenced by any other module

**Alternatives considered:**
1. Rename `test_readback_poller()` to a placeholder function — rejected; adds dead code
2. Wrap the call in try/except — rejected; masks the underlying issue
3. Remove the entire `main()` function — rejected; unnecessary scope creep

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| None | This is a pure removal of a dead call; no behavioral change |
