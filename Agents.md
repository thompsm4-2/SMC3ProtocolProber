# DOF Reality H3 Linux Driver - Project Instructions

## Project Purpose

This project develops a Linux-based Python driver
for the DOF Reality H3 motion platform.

The eventual goal is to port the working Python
implementation to Rust.

## Initial Reading Requirements

Before modifying anything, read:

1. README.md
2. QWEN_INSTRUCTIONS.md
3. docs/SOFTWARE_ARCHITECTURE.md
4. docs/VERSION_HISTORY.md
5. docs/TESTING_AND_CALIBRATION.md

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
