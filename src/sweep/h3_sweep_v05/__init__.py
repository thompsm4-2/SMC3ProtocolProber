"""v0.5 sweep driver and reliable serial recorder for the DOF Reality H3.

This package layers on top of the archived v0.3.5.1 CommandHub
implementation (ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/smc3.py)
without modifying it. Every v0.5 motor transmission is made observable,
attributable, and verifiable through:

- driver.py    -- sweep execution, point sequencing, write-attempt
                  barriers, interruption handling, centering state
                  machine, run status
- recorder.py  -- serial-proxy recorder installed at the smc3.serial
                  module attribute, write-attempt records, attempt
                  synchronization, write status classification
- ledger.py    -- expected motor-frame ledger, sweep-point association,
                  exact frame-byte verification
- eventslog.py -- structured timestamped JSONL event log
- csvlog.py    -- v0.4.1-compatible TX CSV and sensor CSV handling

No module re-exports are provided at the package level: modules are
imported directly and must remain independently testable with no
circular imports and no unnecessary dependencies.
"""
