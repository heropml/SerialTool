# Architecture and maintenance baseline

CommTool is a desktop, event-driven communications workbench. `main_window.py` is
still the composition root for the existing UI, but new behavior should live in the
domain package that owns it and remain Qt-free whenever practical.

| Area | Package | Boundary |
|---|---|---|
| transports | `transport/` | serial, SEGGER J-Link RTT, TCP/UDP, BLE, Virtual; emits bytes/events |
| protocol | `protocol/` | framing, parsing, checksums, reusable frame templates |
| automation | `automation/` | replies, triggers, sequences, scripts, action safety |
| record | `record/` | `.ctrec`, replay, PCAP export, local session catalog |
| project | `project/` | `.ctproj`, presets, operator-panel and device resources |
| sessions | `sessions/` | per-tab connection, buffers, engines, ownership |
| UI | `ui/` | Qt widgets/dialogs and presentation adapters only |

## Rules for new work

1. Put normalization, validation, indexing, serialization, and policy in a Qt-free
   module with direct unit tests.
2. Keep payload ownership in its session. Window-level state is only for resources
   deliberately shared by a workspace/project.
3. External actions are deny-by-default and must have bounded concurrency, timeout,
   import gates, and explicit unsafe overrides.
4. Persist project resources explicitly; retain their old QSettings mapping until a
   format migration has shipped and been exercised.
5. Do not add another large feature directly to `main_window.py`; add a thin adapter
   or mixin after the domain API is stable.

## Runtime and CI baseline

- Supported and tested source runtime: Python 3.11–3.13.
- Compatibility CI: Python 3.11 and 3.13; primary Windows tests: Python 3.12.
- Runtime dependencies are bounded in `requirements.txt` and reproduced in CI/release
  builds through `constraints-runtime.txt`.
- RTT uses `pylink-square`; the Python package is bundled, while the vendor J-Link
  driver remains an explicit host prerequisite. DLL access is process-serialized.
- Ruff, compileall, pure-logic tests, platform smoke suites, full Windows tests, and
  nightly soak/disconnect churn form the delivery gate.

## Qt migration boundary

The current release line uses PyQt5/Qt5. New domain modules intentionally avoid Qt,
which limits a future Qt6 migration to UI, signals, packaging, and compatibility
tests. The migration should be a separate release track: introduce one `qt_compat`
surface, move imports package-by-package, validate high-DPI/tray/network behavior on
all three platforms, then switch packaging. Mixing that migration into protocol or
transport feature work would make regression attribution unreliable.
