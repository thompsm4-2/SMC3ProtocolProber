# Source Log Provenance

The following files were extracted byte-for-byte from the user-uploaded `h3_motor_c_logs.zip`.

- `h3_motor_c_readback_v0.4.1.csv` — SHA-256: `031d6ff1accf9e6f2894736a5cf191dead958903f4d63482549c7f251c3ce723`
- `h3_motor_c_tx_v0.4.1.csv` — SHA-256: `325aea37a2230673cedf0cbc0a5a4ae2f80f87d538a4d6252135444677c8cb85`

## v0.3.5.1 CommandHub baseline

Recovered and preserved on 2026-11-04.

- Original source path: `/home/mathomp/Downloads/H3_v0.3.5.3_calibration_diagnostic_no_observe/H3_v0.3.5.1_commandhub_diagnostic/`
- Matching ZIP archive: `/home/mathomp/Downloads/H3_v0.3.5.1_calibration_diagnostic_no_observe.zip`
- Preserved destination: `ChatGPT-Archive/H3_v0.3.5.1_commandhub_diagnostic/`

The extracted directory was verified byte-for-byte against the matching ZIP archive
and then copied unchanged (structure and filenames preserved; no edits, no cache
files, no collisions with an existing destination).

All nine files, with sizes and SHA-256 hashes (identical in source, ZIP listing,
and preserved copy):

| File | Size (bytes) | SHA-256 |
| --- | --- | --- |
| `smc3.py` | 10033 | `22bf719c50f63e7fde5fc6104c07db18a3ea0bef8640be04bcbd78334d1a3a24` |
| `README.md` | 894 | `bb13f4dae2c22b8edaa38e171ea28c925a803344b8e7c521eda3f5eb9cab67b9` |
| `examples/manual_h3.py` | 2677 | `4e668af5a473bb9b1dfc3d998f591578bede1216b90bf37490d17c60399e6808` |
| `examples/h3_calibrate.py` | 7698 | `75fb70fd3cd4c654593c9ab35171763c893febbded4b4e16ef4406edc2910be6` |
| `tests/serial.py` | 825 | `24d51b10dbd23ffe75dec597b39b4983e0a7a2baf90cd85ad0f33f08e82cbe78` |
| `tests/test_command_hub.py` | 679 | `948ff1be647c016454631687b461aada63d1a4477ca8610e3c2ca5e5ee4479d2` |
| `tests/test_manual_cli.py` | 1193 | `d0b9eb4b5895e0db5ce9612a8482b4e648dc9d75fa88ddc5651d04768601da62` |
| `tests/test_smc3.py` | 1955 | `6d7ac32246c700ec60bc3e0b5cf59c0219af178b5c1d4895a49611f24d9db8c7` |
| `tests/test_h3_calibrate.py` | 3888 | `c6e15b3ec775931db5d7ca39dc4076099e9ee6e07f83e57de27f840a297a616a` |

Limitation: no independent historical hash for this baseline was recorded
previously, so the original version identity (v0.3.5.1) is corroborated by
extracted-tree-versus-ZIP byte-for-byte agreement and archive naming, not by an
older independent hash.
