# Tasks

## 1. Remove Dangling Call

- [ ] 1.1 Delete line 522 (`test_readback_poller()`) from `src/calibration/test_v04.py` `main()` function and verify the file compiles with `python3 -m py_compile src/calibration/test_v04.py`

## 2. Verify

- [ ] 2.1 Run `python3 src/calibration/test_v04.py` and confirm it no longer raises `NameError: name 'test_readback_poller' is not defined` (note: `test_tx_logger()` will still fail with a `TypeError` due to a separate pre-existing issue — BUG-012 — which is out of scope for this change)
- [ ] 2.2 Confirm no other `.py` file in the project references `test_readback_poller` by running `grep -rn "test_readback_poller" --include="*.py" src/` and verifying only the removed line remains (should return no results)

## Workflow follow-up

- Archive the change after review
- Update BUG-013 in `reports/BUG_BACKLOG.md` to Resolved status
