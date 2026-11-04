# Version and Evidence Register

| Component | Version | Status | Evidence |
|---|---|---|---|
| H3 CommandHub transport | v0.3.5.1 | User-reported physically working | User's prior hardware test |
| Characterization | Qwen v0.4 | Failed physical run | Motor C moved initially; crash; no TX log |
| Characterization | ChatGPT v0.4.1 | User-reported completed physical run | Uploaded TX and WT901C CSV logs |
| Calibration source | v0.4.1 | Original source preserved | Added to `src/calibration/` for historical reference and reproducibility |
| WT901C capture/decoder | Prior prototype | Historical | Prior project captures; verify current parser |

## Original source preservation

The original v0.4.1 calibration source is stored in `src/calibration/`.

This source is preserved as a historical implementation reference. Its presence does not imply that the implementation is the current recommended architecture or that every feature has been independently validated.

## Version-control rules

- Preserve exact known-good source snapshots.
- Do not label experimental code as known-good.
- Record source hashes, test commands, test outputs, and hardware conditions.
- Promote a version only when the relevant test has actually passed.
- A successful one-time run does not validate all edge cases.
