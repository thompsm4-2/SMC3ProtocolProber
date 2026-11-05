# DOF Reality H3 Linux Driver - Project Instructions

## Project Purpose

This project develops a Linux-based Python driver
for the DOF Reality H3 motion platform.

The eventual goal is to port the working Python
implementation to Rust.

## Reading Requirements

Always read QWEN_INSTRUCTIONS.md.

Read the other documents only when the task requires them:

- docs/SOFTWARE_ARCHITECTURE.md — changing control code
- docs/TESTING_AND_CALIBRATION.md — testing or calibration work
- docs/VERSION_HISTORY.md — version or provenance questions
- README.md — package-structure questions
- docs/ANALYSIS_METHODOLOGY.md and reports/ — log-analysis work

Inspect the existing source tree before proposing
architectural changes.

## Important Project Rules

- Preserve the existing directory structure.
- Do not reorganize protocol-analyzer.
- Do not remove original calibration source.
- Preserve original raw capture files.
- Do not overwrite original experimental data.
- Maintain compatibility with the existing SMC3
  communication protocol.
- Do not introduce unnecessary dependencies.
- Check Python syntax and imports before delivering
  modified code.

## Hardware Safety

Do not assume hardware is connected.

Perform static checks and software-only tests first.

Do not request hardware testing to identify basic
programming errors that can be caught beforehand.

## Development Workflow

Before making changes:

1. Explain the proposed changes.
2. Identify affected files.
3. Identify potential regressions.

After making changes:

1. Run appropriate syntax checks.
2. Run available software-only tests.
3. Check imports and dependencies.
4. Update relevant documentation.
5. Report exactly what changed and what was tested.

Never claim a hardware test was successful unless
the hardware test was actually performed.

Before beginning a task, identify and read the relevant project documentation and QWEN_INSTRUCTIONS.md. Treat QWEN_INSTRUCTIONS.md as supplemental engineering requirements, not as a replacement for AGENTS.md.
