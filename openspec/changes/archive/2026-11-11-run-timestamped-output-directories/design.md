# Design

## Context

The diagnostic utility (`smc3_readback_diagnostic.py`) writes all output files into a flat `smc3_diagnostic_output/` directory. Files are differentiated by embedded timestamps in their names (e.g., `requests_20261111_143000.csv`). When multiple runs occur in the same day, files from different runs are intermingled, making it hard to identify which files belong to which run.

The `DiagnosticSession` class (line 153) accepts an `output_dir: Path` parameter and creates files directly within it. The `_setup_output_files` method (line 163) generates timestamps in `%Y%m%d_%H%M%S` format and creates all output files. The main function (line 1166) resolves the output directory from `--output-dir` or defaults to `Path("smc3_diagnostic_output")`.

## Goals / Non-Goals

**Goals:**
- Group all files from a single run into a timestamped subdirectory.
- Preserve existing file naming conventions and append behavior.
- Minimize changes to the `DiagnosticSession` interface.
- Keep simulation mode behavior unchanged (no files, no directories).

**Non-Goals:**
- Changing the file-level timestamp format (`%Y%m%d_%H%M%S`).
- Adding run metadata files (e.g., `run_manifest.json`).
- Changing the CLI flag interface (no new flags).
- Implementing automatic cleanup of old run directories.

## Decisions

### Decision: Subdirectory creation in `DiagnosticSession.__init__`

The timestamped subdirectory will be created inside `DiagnosticSession.__init__`, after resolving the parent `output_dir`. The `output_dir` attribute will point to the subdirectory (not the parent), so all downstream file operations remain unchanged.

**Rationale:** This keeps the change localized to one method and avoids threading a separate "parent_dir" parameter. The `DiagnosticSession` interface (`output_dir: Path`) stays the same.

### Decision: Two timestamp formats from one source time

The subdirectory name uses `YYYY-MM-DD_HH-MM-SS` (readable, filesystem-safe). File-level timestamps keep `%Y%m%d_%H%M%S` (existing convention). Both derive from the same `datetime.now()` call at run start.

**Rationale:** Preserves existing file naming conventions exactly. The subdirectory format is more human-readable and sortable. Using a single source time ensures consistency.

### Decision: `--output-dir` now means parent directory

The `--output-dir` flag is reinterpreted: it sets the parent directory (default `smc3_diagnostic_output`). The timestamped subdirectory is always created automatically inside it.

**Rationale:** Users who already use `--output-dir` to set a custom parent directory expect that behavior. The subdirectory is always created, so the flag's meaning shifts from "exact output path" to "parent directory." This is a semantic change but not a breaking one — the default behavior is the same, and custom paths still work.

### Decision: No change to `_SimulateSession`

Simulation mode continues to pass a hardcoded `Path("smc3_diagnostic_output")` to `_SimulateSession` (a subclass of `DiagnosticSession`), but `_SimulateSession` overrides `_setup_output_files` to do nothing, so no directories or files are created.

**Rationale:** The simulate-mode behavior is already correct — it skips file creation entirely. No changes needed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Tests asserting file paths in `smc3_diagnostic_output/` directly will break | Update test assertions to account for the subdirectory layer. The test file already uses `tempfile.TemporaryDirectory` for isolation, so path assertions need one extra level. |
| Existing runs in `smc3_diagnostic_output/` are now orphaned | This is a one-time migration issue. Old runs remain in the parent directory; new runs go into subdirectories. Users can manually consolidate if needed. |
| Two runs at the exact same second share a subdirectory and append | This is the existing behavior and is preserved intentionally. The spec explicitly documents this. |
| `iterdir()` at end of run (line 1282) only lists the subdirectory, not files | Fix: list files inside the subdirectory, not the parent. Update the print loop. |

## Migration Plan

No migration needed. The change is additive:
1. Old runs remain in the parent directory (untouched).
2. New runs automatically use subdirectories.
3. Tests update to account for the new structure.

## Open Questions

None. All technical decisions are resolved in this design.
