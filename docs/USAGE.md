# CommTool Usage Guide

**Serial debugger + network debugging tool** in one app — UART serial terminal and TCP/UDP share the same UI, for embedded development, device bring-up, Modbus / custom protocols, and communication log analysis.

![UI preview](./icon_preview.png)

---

## Contents

- [Quick Start](#quick-start)
- [What's New in v1.5.3](#whats-new-in-v153)
- [What's New in v1.5.2](#whats-new-in-v152)
- [What's New in v1.5.1](#whats-new-in-v151)
- [What's New in v1.5.0](#whats-new-in-v150)
- [Features](#features)
  - [Connection](#connection)
  - [Receiving Data](#receiving-data)
  - [Sending Data](#sending-data)
  - [Keyword Highlighting](#keyword-highlighting)
  - [Multi-Send](#multi-send)
  - [Interface](#interface)
  - [Multilingual UI](#multilingual-ui)
  - [Themes](#themes)
  - [Hover Tooltips](#hover-tooltips)
  - [System Tray](#system-tray)
  - [Online Update](#online-update)
  - [Auto-saved Configuration](#auto-saved-configuration)
- [Tips](#tips)
- [Status Bar](#status-bar)
- [FAQ](#faq)
- [System Requirements](#system-requirements)

---

## Quick Start

1. Double-click the **CommTool** icon on your desktop
2. In the left **Connection** panel, pick a **Type** (serial / network / Virtual), fill in the parameters, then click **Open Serial** / **Open** / **Connect** / **Listen** / **Start Virtual** (depending on type)
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below
4. Use **New Session** for multi-tab concurrent connections (serial / TCP / UDP / Virtual)

---

## What's New in v1.5.3

UX polish and engineering gates on the v1.5.2 baseline:

- **Combo anti-misclick** — mouse wheel over main-window combo boxes is ignored while the popup is closed (baud / type / etc.).
- **Selection convert** — Data-area context menu: **Convert to Text** / **Convert to HEX**; result shown in a dialog and copied to the clipboard (64 KiB cap).
- **Phase A/B** — contract tests, silent-`except` budget, macOS CI smoke, ruff, coverage upload, multi-session boundary notes in README.
- **Tests** — 1464 passed / 11 skipped / 295 subtests.

---

## What's New in v1.5.2

Visualization, export, and replay hardening on the v1.5.1 baseline:

- **Plot & dashboard** — waveform / XY / histogram views, dual-Y + cursor stats; dashboard widgets Number / Gauge / LED / Progress; register-fed alert levels no longer blink off on text `feed`.
- **Excel / PCAP** — sequence + structured-record `.xlsx` export; PCAP/pcapng for TCP Client/Server (single peer), UDP and multicast (serial stays `.ctrec`).
- **Drive real TX replay** — optional `drive_tx` mode with confirmations, consecutive-fail pause, partial-write failure; default remains Virtual RX inject.
- **Sessions / examples** — switching tabs auto-stops multi-send cycles; more example projects; UI tips for window-owned tools.
- **Audit polish** — High/Medium/Low fixes (replay filter sync, serial reconfig race, stale RX drop, HEX search alignment, `open_conn` replace guard, …).
- **Tests** — 1433 passed / 11 skipped / 295 subtests.

---

## What's New in v1.5.1

Follow-ups on the v1.5.0 multi-session baseline:

- **Search lazy pagination** — `find_spans(limit, start)` stops scanning early on large logs; ▲/▼ crosses pages with global wrap; last-page jump is one pass; zero-width regex advances safely; a trailing `+` means more matches exist beyond the current page.
- **Reversible I/O Graph** — status-bar right-click or Workspace → I/O Graph opens the time-axis + four rate channels without wiping your series; closing / changing axis / clearing the parser restores the previous channel snapshot.
- **Example projects** — `examples/*.ctproj` for Modbus RTU, AT modem, and dual-session presets (stable `preset_id`); the Windows installer ships `{app}/examples`, and the macOS DMG shows an `Examples` folder.
- **Mac publish gate** — `url_mac` stays empty until the DMG is verified on GitHub; the updater prefers GitHub Mac candidates and explains when the asset is not ready yet.
- **macOS startup hotfix** — guards the app-level Qt event filter before the receive view exists, preventing `None.viewport()` from becoming a PyQt `qFatal` / `SIGABRT`; maps `Segoe UI Symbol` to `Apple Symbols`.
- **Display-options matrix** — the active tab follows live UI toggles; background tabs keep their own `display_opts` (timestamp / HEX / dump / ANSI / split / encoding / freeze / log). Freeze prefers `display_context["freeze_view"]`.
- **Hardening** — Modbus slave CRC resync performance, master TCP transaction-id checks, truncated virtual-inject logs, search state reset on session switch.
- **Tests** — 1359 passed / 11 skipped / 295 subtests.

---

## What's New in v1.5.0

**Multi-session tabs** — one window can keep several independent connections open at once (serial / TCP / UDP / Virtual), similar to Xshell-style tabs:

- **Per-session isolation** — connection, RX/TX view, display options that affect that pane, live log path, auto-reconnect, and **periodic send** belong to the tab. Background tabs keep receiving, logging, and period-sending.
- **Window-owned tools** — auto-reply / Modbus-slave configuration and RX processing belong to the window and apply to the active tab. Script Console, Sequence, file transfer, Modbus master, recording/replay, send DSL, device scan, and multi-send **cycle** share one occupancy table. Starting another exclusive task shows which task is already running; leaving the active tab is blocked while a hard exclusive task (script / sequence / transfer / Modbus / …) owns the link.
- **Multi-send cycle** — the cycle timer is window-owned; switching tabs **auto-stops the cycle** with a toast (it does not migrate). Per-session periodic send keeps running after a switch.
- **Tab cues** — green = connected, yellow = reconnect wait, gray = disconnected. Hover the tab for connection / periodic-send / live-log status. Double-click a tab to set an optional custom name (tooltip still shows the real port/address).
- **Keyword highlight** — each rule can match as plain text, regex (ReDoS-safe), or HEX bytes (same engine as Find).
- **Draft autosave** — connection/send edits debounce to disk after ~1.5s; period-send ticks do not write the config.
- **Profiles / new window** — Help → New Window (or another profile) is still a separate workbench; multi-session is in-window concurrency, not a replacement for multi-window profiles.
- **Limits** — no session tree, drag-to-split, or tear-off tabs in this release. Two sessions cannot share the same expanded live-log path.

---

## What's New in v1.4.2

Official wrap-up on the v1.4.1 maintainability baseline; v1.4 mainline is feature-frozen:

- **S-2 R43–R55** -- runtime orchestration (reconnect / Modbus poll / sequence / AR gate / RX-TX / Modbus feed) plus display/settings/conn helpers (`config_io` / `view_format` / `connection_presets` / `term_vt`); Qt/QSS/i18n shells stay in `CommTool`.
- **S-3** -- `VirtualConn.simulate_link_drop` baselines; optional `COMMTOOL_SOAK_DISCONNECT` / `COMMTOOL_SOAK_SERIAL` / `COMMTOOL_SOAK_NIGHTLY` gates.
- **Usability** -- send-history dialog can delete entries (button / Delete / Backspace); history and file-transfer buttons match MultiSend ghost/primary styles.
- **Boundary** -- P2 (CLI / REST / plugin dissector) remains deferred.
- **Tests** -- 1186 passed / 6 skipped / 291 subtests.

---

## What's New in v1.4.1

Official maintainability release on top of v1.4.0 capabilities:

- **S-2 architecture** -- extract Qt-free service modules (R1–R33) and GUI `build_*` factories (R34–R42); `CommTool` stays a thin assembler.
- **S-1 / S-3 / S-4 / S-5** -- quieter exception logging, soak/reconnect burst harness, size-based log roll, actionable connection/send toasts, send-history search, Modbus master one-shot R/W.
- **Fixes** -- empty `[]`/`{}` JSON parse no longer becomes `None`; empty send still resets history nav; dead imports cleaned; single-block RX overflow trim without newlines.
- **Tests** -- 1148 passed / 4 skipped / 291 subtests.

---

## What's New in v1.4.0

Official stability release:

- **Register extensions** -- 64-bit types, bitfields, 0/1 address base, warn/alarm levels.
- **Modbus Master multi-view** -- edit polls by view; shared half-duplex engine.
- **FC22 / FC43/14** -- mask write and device identification.
- **Trigger actions** -- Webhook / external command / hit thresholds; process-group cleanup; delete confirms.
- **Modbus TCP↔RTU gateway** -- multi-client directed replies; 0x0B on timeout; recovery window; same-batch resync keeps valid frames.
- **Hardening** -- shell-escape for run_cmd placeholders; no fake disconnect while connecting; literal private webhook URLs blocked.
- **Tests** -- 1023 passed / 3 skipped / 291 subtests.

---

## What's New in v1.3.9

This release finishes the remaining P1 polish:

- **Multi-slave row table** -- the Modbus slave dialog replaces the JSON textarea with Addr / Server ID / Extra JSON rows (add/remove). Duplicate addresses are rejected with a toast; hand-edited project JSON still keeps the first address at runtime.
- **Jump to session time** -- click the status-bar RX/TX stats to jump to the latest sample wall time; double-click a session-compare row to jump via `.ctrec` `wall_t0` (older recordings without the anchor show a toast). New recordings store `wall_t0`.
- **Data-area bookmarks** -- `Ctrl+F2` toggles a bookmark on the current line; `F2` / `Shift+F2` move next/prev (wrapping). Clearing the data area or an ANSI full clear (`ESC[2J`) drops bookmarks.
- **Docs** -- P1 roadmap items are complete; stale "still TODO" notes cleaned up. Next focus is stability / multi-session polish and cross-platform CI (P2 CLI / API / plugins remain deferred). PCAP export supports TCP Client/Server (single peer), UDP, UDP Multicast as `.pcap` / `.pcapng`.
- **v1.4 stability follow-up** -- register definitions now cover 64-bit values, bitfields and warning/alarm levels; Modbus Master adds grouped views, FC22 mask writes and FC43/14 device identification; trigger actions add Webhook / external commands with hit thresholds; and the Bridge page includes a real multi-client Modbus TCP↔RTU gateway. External command processes are reaped on shutdown, including POSIX child process groups.

---

## What's New in v1.3.8

This release wraps up the post-1.3.7 polish items:

- **Wrapping tooltips** — long tips are routed through `ui_tips.set_tooltip` so Qt wraps them as rich text instead of one ultra-wide line. The system-tray icon tip stays plain text (Windows shows HTML literally in the tray).
- **Modbus advanced UI** — the auto-reply slave dialog now configures exception injection (mode / n / funcs / addrs), dynamic registers (table), and `server_id`. Multi-slave remains a JSON box. On the master page, FC08 qty accepts `sub:data` (e.g. `0:1`); switching function codes reshapes the cell and refreshes its tooltip. Read quantities clamp to at least 1; dynamics `max=0` saves correctly.
- **Plot → session jump** — double-click a plot point to jump the structured record to that sample's wall time via `jump_to_session_time`. Rate series (`rx_Bps` / `tx_Bps` / `rx_pps` / `tx_pps`) are not jump targets.
- **Fixes** — auto-reply `closeEvent` now both commits pending edits and syncs settings (split sizes persist); help text no longer claims exception/dynamics have no UI.

---

## What's New in v1.3.7

This release closes the loop from reusable connections to CI-ready test artifacts, and deepens Modbus simulation and record playback:

- **Named connection presets** — save every serial or network parameter, plus notes and the auto-reconnect policy, as a named preset. The connection bar gains a preset dropdown with Save / Manage; presets support most-recently-used ordering, duplicate, delete, JSON import/export and travel inside `.ctproj`. Applying a preset while connected is refused (the dropdown falls back to its placeholder), so live parameters are never swapped underneath you.
- **Sequence variables and context** — sequence **Send** / **Expect** fields accept `${name}` templates, and each step can extract variables from its reply by text, HEX, regex group or Modbus field for later steps to use; scope is per round and `$${` escapes a literal `${`. An undefined variable now fails the step immediately instead of silently degrading to a plain send, so aging loops cannot report false passes.
- **CSV data-driven sequences** — bind a CSV dataset to run one round per row, with the header row seeding `${var}` and the loop count taken from the row count; reports carry the CSV row number and a device label (taken from a `device_id` / `sn` / `name` column). Decoding falls back utf-8 → GBK (Excel "Save as CSV") → latin-1.
- **Test report export now includes JUnit XML** — **Export Report** offers HTML / CSV / **JUnit XML**, the last of which drops straight into Jenkins or GitLab CI. All three formats now record the app version, start and end time, run parameters (loops, step count, stop-on-fail) and the CSV path, plus per step the elapsed time, failure reason and key frames (TX / RX hex). **Behaviour change: a mid-run stop or disconnect now still produces a summary and can be exported** (flagged as stopped) instead of being discarded, and multi-round runs expand every step of every round.
- **I/O statistics and diagnostics** — the status bar adds packet rate (pkt/s, where a "packet" is a transport-level read/write chunk, not a protocol frame); tooltips add peak packet rate, packet size min/avg/max, a size histogram, timeout counters split by sequence / Modbus master / connection, and the average rate over the last minute. The plot dialog can subscribe to `rx_Bps`, `tx_Bps`, `rx_pps` and `tx_pps`; right-click the status bar or open Workspace -> I/O Graph for a one-click time-axis preset. Resetting statistics leaves recordings and the data area untouched. No new dependencies.
- **Example projects** — starter `.ctproj` packs cover Modbus RTU, AT modem and dual-session presets. Source builds use `examples/`; the Windows installer creates `{app}/examples`, and the macOS DMG contains a visible `Examples` folder. Open a pack with **Project → Open**. Dual-session tabs are runtime-only: after opening, use **New Session** and apply the Session B connection preset.
- **Multi-slave simulation** — the Modbus auto-reply slave can emulate several slaves on one bus: the **multi-slave row table** (Addr / Server ID / Extra JSON) takes one row per slave, each with its own register maps and server ID, and anything left out is inherited from the single-slave configuration above. **Filling the table overrides the single-address table.** Under TCP Server every client still keeps its own partial-frame buffer, so frames never bleed between clients. Broadcast address 0 accepts write function codes only; reads and FC08 / FC11 / FC17 / FC23 are refused with "Broadcast address only allows write functions" in the result column.
- **Exception injection and dynamic registers** — the slave can return exception codes on a policy, so you can exercise the master's error paths, and register values can move on their own by increment, decrement, random, sine or ramp to mimic a live device; a value written by the master overrides the dynamic one until the session is reset. The dialog exposes only the exception code and the **Inject exception** switch — **the injection mode, the function-code and address filters, and the dynamic register rules have no UI yet and must be written into the project file**: `{"exception": {"enabled": true, "code": 4, "mode": "n", "n": 3, "funcs": [3, 6], "addrs": [10, 11]}, "dynamics": [{"space": "holding", "addr": 0, "mode": "sine", "min": 0, "max": 100, "period_ms": 2000}]}`. The exception `mode` is `always` / `once` / `n` (every Nth request), and empty `funcs` / `addrs` mean "any". For dynamics, `space` is `holding` / `input` / `coils` / `discrete` and `mode` is `inc` / `dec` / `random` / `sine` / `ramp` (with optional `step` / `phase` / `seed`); `min` equal to `max` degenerates to a constant. Give `random` a `seed` to make the sequence reproducible; resetting the session returns it to the start.
- **More function codes** — the function dropdown adds **08 Diagnostics (echo)**, **11 Get Comm Event Count**, **17 Report Server ID** and **23 Read/Write Multiple Regs**, implemented on both the master and the slave side. For FC23 the quantity column takes `read_qty @ write_addr : write_values` (values space-separated, e.g. `2 @ 100 : 10 20`); FC08's diagnostic data goes in the same column and the result shows both decimal and hex so you can check the echo against what you sent, but **the sub-function has no UI yet** and must be set as `diag_sub` in the project file's poll rule (default 0 = loopback). FC17's server ID has no standardized length, so its response is variable: RTU sizes the frame from its byte-count field, Modbus-TCP from the MBAP length field and ASCII from the frame terminator, and all three variants receive it in full.
- **Persistent plots and structured playback** — plot and dashboard data sources, units and layout are saved inside `.ctproj` and restored when the project is reopened. A structured recording can be replayed on its original timeline to drive the same plots, with pause, single step, speed and seek; byte-level `.ctrec` playback also supports pause, single step and seek by seconds, and stepping pauses first so each click advances exactly one event.
- **Session diff filtering and export** — comparison results can be filtered by direction (RX / TX) and by absolute time delta, and the summary counters follow the current filter; the filtered rows export to CSV or JSONL, and the export button disables itself when the filter hides every row rather than writing a header-only file.

---

## What's New in v1.3.6

This release turns CommTool into a project-oriented debugging workspace:

- **Workspace and projects** — Terminal, Protocol, Simulation, Automation, Data and Bridge now have dedicated pages. The project menu supports New, Open, Save, Save As, recent projects and optional startup restore.
- **Device Center and Modbus Scan** — define register tags with type, byte order, scale, offset and units; import or export them as CSV. Scan slave IDs or 03/04 register ranges over an open serial or TCP Client link, then add successful results to the register map. A scan temporarily takes over the Modbus scheduler, protects in-flight RTU replies, locks conflicting Modbus edits and restores the previous configuration afterwards. Each batch is limited to 512 targets.
- **Structured records** — record named Modbus values and protocol fields, filter them by source or keyword, save/load CSV and replay on the original time axis.
- **Portable project resources** — `.ctproj` v2 explicitly packs register maps, snippets, multi-send groups, sequences, scripts and dashboard settings while remaining compatible with v1 projects. A v1 project that has no register-map or snippet resources initializes those two resources as empty; export current shared content first if it must be retained.

---

## What's New in v1.3.5

This release makes device logs feel more like a terminal, alerts you when unattended equipment misbehaves, and keeps frequently used commands one click away:

- **ANSI color display** — Text view and terminal mode now render the device's own SGR colors, including standard/bright colors, 256-color and true-color output, bold, underline, and reverse video. Color state and incomplete escapes continue correctly across chunks; TCP Server clients keep independent state. Cursor movement, title-setting, and other non-display escapes are removed instead of appearing as `^[[0;32m` noise.
- **Trigger alerts** — Function → Trigger Alerts matches text or HEX using Contains / Equals / Prefix / Regex rules, scoped to RX, TX, or both. A hit can beep, show a tray notification, and mark the data area. Cooldown suppresses repeated actions without losing hit counts or the last-hit time. Serial/TCP rules can match keywords split across chunks, while UDP preserves datagram boundaries.
- **Send snippet library** — Open it from the Multi-Send window to store frequently used text or HEX commands. Search, add/delete, import/export JSON, double-click to fill the send box, or fill and send immediately. It reuses the normal send path, so newline, checksum, and target settings behave exactly like manual sending.
- **Unified view selector** — Text, HEX, HEX Dump, and Numeric rendering are now one mutually exclusive dropdown. Mode-specific controls appear alongside it: ANSI for Text, row width for Dump, and type/byte order for Numeric. No new dependencies.

---

## What's New in v1.3.4

This release is about seeing more clearly, changing faster, and telling recordings apart:

- **Numeric view** — a new toggle in display settings: read the incoming byte stream as numbers in u8 / i8 / u16 / i16 / u32 / i32 / f32 x big / little endian (12 combinations), so ADC samples and raw sensor values need no manual conversion. Trailing bytes that don't fill a whole value carry over to the next packet, so values split across packets stay aligned; column widths are fixed per type so successive packets line up in columns. Mutually exclusive with the HEX dump (both take over the data area).
- **Selection checksums** — select a run of bytes in the data area and the status bar shows their checksums right there, no more copying into the toolbox. The status bar shows Modbus / XOR / SUM inline, and hovering pops a themed card with all 9 (sum / neg-sum / XOR / CRC8 / Modbus-CRC16 / CCITT-CRC16 / CRC32 / ADD16 / MOBUS). Byte recovery skips timestamps, direction arrows, the dump's offset column and ASCII column; text / numeric / terminal views cannot losslessly recover the original bytes, so it declines rather than show a plausible-looking wrong value.
- **Live serial params** — change baud / data bits / parity / stop bits / flow control while the port is open, without disconnecting or losing the receive buffer, so trying unknown baud rates one by one is far faster than reconnecting each time. Parameters apply atomically and roll back on mid-way failure. Changing port / protocol still requires reconnecting.
- **Logging upgrades** — the live-log filename supports variables: `%date` (20260724) / `%time` / `%datetime` / `%port` (COM3 etc.) / `%n` (segment index), e.g. `log_%date_%port.txt`. When the name contains a date variable, it rolls over to a new file across a calendar day (per-day archival, segment index reset), handy for unattended and long-running captures. Works alongside the existing size-based segmentation.
- **Session compare** — Function → Session compare: pick two `.ctrec` recordings and align them event by event into same / changed / only-in-A / only-in-B, with timing offsets for paired events. Record the old and new firmware once each to answer "what changed in this build". Alignment uses the longest common subsequence (memory-lean linear-space implementation): a single missing frame is reported once and the rest stays aligned instead of cascading; timing is not part of the equality test, and the full result can be exported as CSV. No new dependencies.

---

## What's New in v1.3.3

This release is about getting work done without hardware on the desk:

- **Virtual connection** — a new `Virtual` entry in the Type dropdown: bring up a connection with no hardware attached, and auto-reply / test sequences / the script console / plot / dashboard / protocol highlighting all keep working as usual. Turn on **Loopback** and whatever you send comes back as if received, so you can write and verify rules and scripts on the road.
- **Record / replay** — Function → Record / Replay: capture the raw traffic on the link together with its timing into a `.ctrec` file (plain text, readable and diffable), then re-inject it at the original pace with a 0.5x–max speed control and optional looping. Capture once on site and reproduce it later, or send the scene to a colleague. Division of labour with macro recording: the macro records *what you sent* and produces a script, this records *the raw bytes on the wire* and produces data. Replay targets the virtual connection (injecting "received data" into a real serial port isn't physically meaningful). Later releases add **Export PCAP** in the same dialog: TCP Client/Server (single client), UDP (fixed remote), and UDP Multicast can export synthetic `.pcap` / `.pcapng` (not NIC capture); serial etc. still use `.ctrec`.
- **Command DSL** — write timing directly in the send box: `AT\r\n\!(Delay500)AT+VER\r\n` sends AT, waits 500 ms, then sends the next one; `\!(Repeat3)PING\!(Delay200)` repeats the whole thing three times; also `\!(Wait)` / `\!(Hex)` / `\!(Text)`. Without any directive the text is sent exactly as before, so it's handy for a quick bit of automation without opening the script console.
- **Task exclusion extended** — recording / replay / DSL now join the shared task table alongside the script console, sequences, file transfer, timed send and the Modbus master, so two of them can never fight over the link. No new dependencies.

---

## What's New in v1.3.2

This release moves automation from GUI forms to real code:

- **Script console** — Function → Script Console: drive real traffic on the current connection with a Python script — self-tests, burn-in, bulk provisioning, protocol bring-up: anything a GUI form can't express. The API is `send / recv / expect / sleep / log / check / hexs`: `expect("OK", timeout=1000)` blocks until the reply arrives (or returns `None` on timeout) and `check(cond, "label")` records pass/fail per step and prints a summary at the end. Keep several named scripts and switch with the dropdown; they persist with the session config and can be exported as JSON to share (imports ask for confirmation first — scripts run with this app's privileges).
- **Macro recording** — click "● Record" in the script console, go work in the main window as usual, then click "■ Stop Recording": your actions are translated into a script and saved to the library, ready to replay with "Run". Each send becomes `send(...)`, the replies that follow are merged into `expect(...)` + `check(...)` (timeout gets 3× headroom over the measured latency), and gaps ≥50ms become `sleep(ms)` so the original pacing is preserved. You don't have to write code to turn a debugging session into a repeatable test case.
- **RX/TX task mutual exclusion** — script / test sequence / file transfer / macro recording / timed send / multi-send loop / Modbus master now exclude each other: starting one while another owns the link gives a clear message instead of silently interleaving frames. While a script runs, auto-reply and the Modbus master are paused and any response still in flight from before the takeover is isolated, then everything is restored.
- **Grouped Function menu** — the Function menu is now split into four themed groups (frame tools / visualization / automation / communication) with separators, so it stays scannable as it grows. Also fixes dialog combo boxes briefly showing the system accent color when opening. No new dependencies.

---

## What's New in v1.3.1

Several practical additions this release:

- **Numeric dashboard** — Function → Numeric Dashboard: parses the RX stream into named numeric channels (delimiter / regex / HEX-field modes) and shows each as a large-value tile; fill the thresholds line with `name:lo~hi:unit` (comma-separated, e.g. `Temp:10~40:℃, Volt:3.0~3.6:V`; leave lo or hi empty for one-sided) and out-of-range tiles blink red. Great for live sensor / power readings; its parse config is independent from the plot.
- **Protocol highlighting** — tick "Protocol Highlight" in the Frame Parse dialog and, in HEX view, each field of incoming frames is colored per your frame-parse rules (slave address / function code / CRC each in its own color), with a hover tooltip showing "rule · field=value". Turns the data area from a raw byte stream into structured information, reusing your existing frame-parse rules.
- **Serial auto-reconnect** — when a serial link drops at runtime (unplug / power loss / cable glitch), it reconnects with a backoff that grows linearly from 0.5s to 5s, but only back to the exact device and parameters it had (full signature saved — never drifts to another port in the dropdown), and only once the original port re-enumerates; waiting and actual retries share a single budget of up to 10 tries (~27.5s), after which it gives up silently and stays disconnected. A single prompt on disconnect, then the retries stay silent — no toast spam.
- **USB chip identification** — the serial port dropdown now appends the USB-UART bridge chip model (CH340 / CP2102 / FT232, etc., matched by VID/PID) after the system description, so you can tell several USB-serial adapters apart at a glance. No new dependencies.

---

## What's New in v1.3.0

**Bridge forwarding** (**Function → Bridge**) connects any two endpoints — serial / TCP client / TCP server / UDP — and passes bytes through in both directions, for protocol relaying, putting a serial device on the network, or tapping a stream:

- **Any two endpoints** — Side A and Side B each pick serial / TCP client / TCP server / UDP independently; once both are up, bytes flow both ways (serial↔serial, serial↔network, network↔network).
- **Robust forwarding** — a disconnect / error on either side auto-stops the bridge, with live A→B / B→A byte counts and rates. The TCP server broadcasts to all clients with write-buffer backpressure, UDP splits large streams into valid ≤65507-byte datagrams, and send failures are logged (never silently dropped).
- **Pre-start check** — before starting, each side is checked for a reachable send target (TCP must be connected, UDP must have a peer); if not ready, it tells you which side.
- **Forward log** — an optional log at the bottom: text / HEX, clearable, adjustable line cap; incremental UTF-8 decoding (multi-byte characters split across packets don't garble) and a per-entry byte cap. No new dependencies.

---

## What's New in v1.2.9

This release brings several practical enhancements at once:

- **Toolbox** — Function → Toolbox: base / encoding conversion (a byte sequence converts live between HEX ⇄ text ⇄ decimal ⇄ binary, interpreted as ascii/u16/i16/u32/i32/f32, plus single-value bases and a bit mask) and checksum calculation (lists every built-in algorithm at once so you can spot which one a device uses, plus a custom Rocksoft CRC).
- **Function menu reorg** — the waveform plot, frame parser and Modbus master move from the data-area toolbar into the title-bar **Function** menu, numbered alongside the others; the toolbar is trimmed to highlight / font-size only.
- **Serial control lines** — once a port is open, a **Control lines** section appears under the Open button: DTR / RTS output switches, Reset (pulses DTR low ~120ms to trigger the Arduino / ESP auto-reset), Break (holds TX low ~250ms), and CTS / DSR / DCD / RI status LEDs polled ~5Hz. The serial settings gain a **Flow control** dropdown (none / RTS-CTS hardware / XON-XOFF software).
- **File transfer** — Function → File Transfer: XMODEM (128 B, checksum / CRC), XMODEM-1K and YMODEM (with filename / size) in both directions (often used to upload firmware to a bootloader), plus a raw-byte mode that dumps a file directly with a configurable chunk size and inter-chunk gap. Progress + log + cancel; the data view, auto-reply, sequence and Modbus master pause during transfer.
- **HEX dump view** — a **HEX dump** toggle in the data-area options renders RX / TX in hex-editor style: offset (8 hex) + HEX (8 / 16 / 32 / 64 bytes per row, split at the midpoint) + |ASCII|, integrated with the highlight-only filter. No new dependencies.

---

## What's New in v1.2.8

The **Frame Builder** (**Function → Frame Builder**) assembles a binary frame field by field, auto-computes length and checksum, and gives you the complete sendable HEX in real time:

- **Field-based assembly** — endian-aware u8/i8/u16/u32/f32 integers and floats, ASCII, and raw HEX; one field per row, with the full HEX and byte count shown live and invalid input blocked from fill / send.
- **Automatic length & checksum** — the length field counts the bytes after it; the checksum field covers everything before it (ADD8 / XOR8 / CRC8 / Modbus CRC16 / CCITT / CRC32, etc.).
- **Built-in protocol templates** — Modbus read, Modbus write-single, and AT-command templates provide editable starting points; field definitions are auto-saved and refresh correctly across config import / switch.
- **Drag to reorder & resizable columns** — drag a row's left handle to reorder fields (order = byte order); the Name / Type / Value columns are drag-resizable.
- **Fill or send directly** — copy the result into the main send box or send it directly; Direct Send transmits the bytes unchanged, while filling the send box still respects the main window's visible newline / checksum settings. This release also fixes the receive view jumping away from a scrolled-up position when a selection exists and new data arrives. No new dependencies.

---

## What's New in v1.2.7

This release makes the **Automated Test Sequence** production-ready — loop/aging runs, per-step retries, exportable reports, and reusable test cases:

- **Test report export (HTML / CSV)** — after a run, **Export Report** → HTML (pass/fail row shading, verdict summary, test time — archive or email it) or CSV (opens in Excel, formula-injection safe); loop runs produce a per-round table, single runs a per-step table; export is only available once a run finishes with a summary (partial results from a stop / disconnect aren't exported).
- **Loop / aging runs** — a **Loops** count + **Stop on fail** in the top bar let a device self-check N rounds for aging / reliability; while running it shows round R/N · step i/n, and the summary gives "passed rounds R/N + cumulative steps" (flagging "of M planned" on an early stop); a mid-run stop / disconnect still summarizes the rounds done, and the result can be exported.
- **Per-step retry** — each step can set a **Retry** count (0 = none): on failure (timeout / send error) it waits out the step's delay plus a short line-silence window, then resends; any passing attempt counts as pass, marked "(try N)"; a late reply from the previous attempt won't taint the next.
- **Step import / export (JSON)** — the **Steps ▾** menu exports / imports the whole sequence as JSON for sharing and version-controlling test cases; import is strictly validated (step count, field types & ranges, file size) with a confirm before replacing current steps. No new dependencies.

---

## What's New in v1.2.6

**Automated Test Sequence** — a new **Function menu → Automated Sequence** that runs a list of "send → wait for a matching reply" steps in order, judging each **Pass / Fail** and giving a summary at the end. Great for factory tests, device self-checks, batch acceptance, and protocol bring-up — anything repetitive:

- **Per-step config** — Name, Send content (text / HEX), Checksum (CRC / sum, etc. auto-appended, same as the main window), Expected reply (**leave blank = send only, don't wait for a reply**), Match mode (contains / equals / prefix), Timeout ms, Timeout action (**Stop** = a failed step ends the whole run / **Continue** = mark it failed but keep going), Inter-step delay ms, and an Enable checkbox.
- **Ordered run + step-by-step verdict** — each step is sent in order, then the tool waits for a reply and judges it by the match mode; the Result column updates live: Pending → Waiting… → **✓ Pass / ✗ Timeout**, with a Pass / Fail summary once the run finishes.
- **Pauses auto-reply / Modbus master while running** — the sequence is the active driver (it shares the receive stream with auto-reply and the Modbus master), so both are **paused** for the duration and **restored** when it ends; a disconnect **aborts the sequence and keeps the results so far**.
- **Card-style UI** — one card per step; only the **Send** and **Expected reply** fields are draggable (other columns fixed), matching the auto-reply dialog; a **?** help window (with AT-command / Modbus read-register / send-only examples); while running the **Run** button turns green and add/remove-row is locked, and steps are saved automatically.
- No new dependencies.

---

## What's New in v1.2.5

**Multiple windows** — you can now run several independent CommTool windows at once, each debugging its own device without interfering, and manage multiple config sets:

- **New Window** — "Help → Open Config → New Window (auto)" opens another independent window (or just launch the program again); the title carries a `(2)` / `(3)` suffix (taskbar and tray too).
- **Configs no longer clobber each other** — each window uses its own settings file (main = `settings.ini`, others = `settings-2.ini` / `settings-3.ini`…); a file lock auto-assigns a free slot, so even double-launching the exe auto-isolates (fixes the old "two windows overwrite each other's config" problem).
- **Fully independent** — each window has its own connection, send/receive, auto-reply, Modbus master, terminal, etc. (note: a serial COM port can still only be opened by one window; opening the same port in a second window reports "busy" — that's expected, data never mixes).
- **Open Config (switch)** — "Help → Open Config" lists saved configs (Main / Config 2 / Config 3…); clicking one switches the **current window** to it (title changes to `(N)`, saves go to that config afterward). The one in use by another window, and the current window's own, are shown disabled. Solves "closed everything, now want a previous config back but there's no entry."
- **Delete Config** — "Help → Delete Config" removes config files you no longer need (with confirmation, Cancel focused by default to avoid mis-deletes); the main config and in-use configs can't be deleted.
- **Multi-monitor safeguard / window cap** — if a window ends up off-screen (a disconnected/closed monitor), it's pulled back onto the primary screen on first show; up to 8 windows can be open at once (a message appears when full).

**Fixes in this release**: ① Can't connect to a local / LAN TCP server or client while a system proxy is on — debug connections now always go **direct, bypassing the proxy** (TCP / UDP both fixed); ② the bottom status-bar toast no longer overlaps the RX / TX stats text; ③ fixed the second / new-config window sometimes hanging with no visible window, and close-window freezes.

---

## What's New in v1.2.4

**Terminal mode** — a "Terminal mode" toggle in the **Send** settings turns the send box into a lightweight serial terminal, handy for logging into a Linux serial console and typing commands:

- **Type-to-send, key by key** — type in the send box and each keystroke goes straight to the device: **Enter / Backspace / Tab / Ctrl+C / arrow keys (↑↓ shell history, ←→ move) / ESC / Home / End / Delete** are all passed through.
- **Terminal-semantic rendering** — the data area renders the device's echo like a terminal: proper **backspace erase**, `\r` carriage return, cursor moves, and the common line-editing ANSI sequences (`ESC[J` / `ESC[K` erase, `ESC[C` / `ESC[D` cursor); **color codes `ESC[..m` are ignored** (colored `ls` output shows clean, no more `^[[31m` garbage).
- **Local echo / Enter mapping** — a "Local echo" switch (for devices that don't echo); "Enter" can be **CR / LF / CRLF** (default CR, matching most Linux consoles).
- While terminal mode is on, the **irrelevant format settings (HEX display / timestamp / packet-split / timeout / HEX send / checksum, etc.) are dimmed & disabled**, and periodic send is stopped — only terminal-related options stay active; everything restores when you turn it off.
- Limitation: full-screen TUIs (`vi` / `top` with whole-screen cursor positioning) aren't emulated — use a dedicated terminal for those.

---

## What's New in v1.2.3

A robustness fix release: serial-port selection and disconnect handling are more reliable, and several dialogs now remember their dragged column widths.

- **Serial selection no longer "jumps"** — when a selected port briefly drops out of enumeration during a background scan (common with USB-serial adapters), the selection no longer silently switches to another port; if the port is genuinely gone for good, the "not detected" placeholder is auto-removed and the selection falls back to the first real port.
- **Connected port removed (unplugged / driver gone)** — after a few consecutive missed scans the connection is **automatically closed with a "serial port X removed" notice**, instead of staying stuck in a fake "connected" state.
- **Serial disconnect no longer auto-reconnects in a loop** — a serial drop is almost always a physical unplug/power-off; reconnecting is pointless and could grab a different port, so a serial disconnect now just cleanly disconnects (network TCP/UDP drops still auto-reconnect with backoff).
- **Dialogs remember column widths** — column widths you drag in **Multi-Send**, **Modbus Master**, and **Auto-reply** now persist across reopen/restart and travel with the session config import/export.
- Also fixed: restoring the last serial port when the startup scan races ahead of config restore; connection-error handling now uses the actual connected protocol (avoids a misjudgment if config is imported mid-connection).

---

## What's New in v1.2.2

Two usability upgrades: **drag-to-reorder** for Multi-Send, and a **silent auto-update check** (Claude-style — checks quietly in the background and only nudges you when a newer version exists).

- **Multi-Send drag-to-reorder** — each row has a **☰ drag handle** at its start; press and drag up/down to change the send order, drop to save. The insert point snaps to the upper/lower half of the target row.
- **Auto-update check** — a silent check runs ~5s after startup and again **every 6 hours**; only a newer version is surfaced — no version / no network stays **completely silent (no popups)**. When a newer version is found, the **bottom-right version label turns into a clickable “● Update vX” badge**; click it to open About and download. The About dialog gains an **“Auto-check for updates” toggle** (on by default; turn it off to stop background checks — manual “Check for Updates” still works).

---

## What's New in v1.2.1

Builds on v1.2.0's Modbus master with **multi-write functions**, hardened **mis-operation safety**, and **draggable columns** — converged over five adversarial-review rounds:

- **Multi-write functions** — the master now supports **0F (write multiple coils) / 10 (write multiple registers)**: put several values in the Qty/Value cell, comma- or space-separated (e.g. `100,200,300`; 0F coils: `0/1`).
- **Mis-operation safety**: illegal/out-of-range **Unit (0..247) / Address (0..65535) / write value** are **refused** instead of silently clamped (so a bad Unit can't become broadcast address 0 and write every slave); a write-multi with any invalid item or over the spec limit is **rejected as a whole** (no silent truncation / address shift); after a request timeout a short **quiet window** prevents a late reply from being mis-matched to the next row; while master polling is active, auto-reply is skipped so it can't fight the built-in Modbus slave on the bus.
- **Draft editing** — while polling is on, editing a rule only stages a draft (no more auto-commit-and-send after 300 ms); click **Apply** to take effect (prevents an accidental write when switching a read to a write). Unapplied drafts survive closing/reopening.
- **Draggable columns** — drag the boundaries between Name…Value to resize; all rows and the header stay pixel-synced; the Function column is narrower by default.
- Robustness: one corrupt rule is skipped instead of wiping the whole table; the string `"false"` is correctly read as disabled; many illegal rules schedule asynchronously (no recursion/stack overflow). Behaves like v1.2.0 when the Modbus master is off.
- **Mutual exclusion + connection self-heal**: auto-reply and Modbus master are **one-click mutually exclusive** (enabling one disables the other; both dialog toggles stay in sync); TCP/serial half-frame writes drop & reconnect immediately, never polluting later frames; Modbus address/numeric inputs accept leading zeros (e.g. `08`/`010`).

---

## What's New in v1.2.0

**Modbus master / polling** — after the Modbus RTU **slave** in auto-reply, this adds the **master** side: act as a Modbus master, poll a slave's registers / coils at a per-row period and show the results live (no more hand-typing request frames for bring-up, table dumps, or periodic checks):

- **Modbus master poll** — new **Modbus Master** button atop the Data area. Each row: `Name / Unit / Function / Address / Qty (read) or Value (write) / Period ms` → live **Value (decimal + hex)** + **Status**.
  - reads **01** coils / **02** discrete inputs / **03** holding / **04** input registers; writes **05** single coil / **06** single register (re-written each period, echo shown).
  - **half-duplex**: only one request in flight; the next is sent after a response or timeout (1s); each row scheduled on its own period.
  - status at a glance: **OK / Timeout / Exception (slave's code) / Bad response / Send failed**.
- **Transport auto-select** — serial → **Modbus RTU** (with CRC), TCP Client → **Modbus TCP** (MBAP); or force RTU / TCP.
- **Local-echo mode** — tick it if your serial adapter echoes sent frames (common on RS-485 half-duplex): it strips one leading copy of the request (tolerating leading noise) before parsing the real response. Crucial for writes 05/06, whose echo is identical to a success reply — without it the echo is taken as success and the slave's exception is lost.
- **Robust validation** — checks slave id / returned count / write echo / exception-function match; RTU resyncs byte-by-byte on a bad frame (never clears the whole buffer, so a local-echo pile-up can't drop the response), TCP self-frames by MBAP length.
- Adds `src/modbus_master.py` + `src/modbus_master_dialog.py` + `tests/test_modbus_master.py` (34 cases); trilingual UI; no new dependencies; zero impact on existing features until enabled; converged over **three adversarial-review rounds**.

> Tip: don't enable "Auto-reply · Modbus slave" and "Modbus master" at the same time — one receives requests, the other sends them; mixing interferes (see the "?" help in the dialog).

---

## What's New in v1.1.9

Auto-reply gains **scripted replies** — write a little Python per rule to build the reply dynamically, for logic that static templates and bitmasks can't cover (compute the answer from the received bytes, look up a table, state-dependent responses, custom CRC, …):

- **Scripted reply** — click **Script** on a rule and define `reply(frame, ctx)`:
  - return `bytes` (one frame) / `list[bytes]` (multi-frame) / `str` (text) / `None` (no reply); the script owns the whole frame and computes its own checksum via ctx.
  - `ctx`: `.state` (state-machine state) · `.seq` · `.hits`; a **customizable CRC** `ctx.crc(data, width, poly, init, refin, refout, xorout, byteorder)` plus shortcuts `crc16` (Modbus) / `crc8` / `sum8` / `xor8` / `hexbytes` / `tohex`.
  - the editor has a built-in **Test** to run one frame; an **Enable script** toggle keeps the code while turning it off; when active the row's static reply / checksum are greyed out.
- **Isolated & safe** — scripts run in a **separate process**: on timeout (1s default) the whole process group is killed (including any subprocess the script spawned), so the GUI never freezes; preview / test and live use separate processes (no cross-contamination); importing a config that contains scripts asks for confirmation (decline blanks the scripts).
- Stacks with v1.1.8's bitmask matching; fault injection + delay + state-machine goto all apply to scripted replies; trilingual UI; adds `tests/test_script.py`; no new dependencies; scripts are off by default (behaves like v1.1.8 when unused).

---

## What's New in v1.1.8

Auto-reply matching goes **sub-byte** — beyond whole-byte `??` wildcards, you can now match by **nibble, bit, or field**:

- **Bitmask / field-level match** — matching upgrades from "exact byte / whole-byte wildcard" to a per-byte **`(value, mask)`** compare; a hit needs `(received & mask) == (value & mask)`:
  - **whole byte**: exact `AB`; wildcard `??` / `XX` (unchanged)
  - **nibble wildcard**: `A?` (high nibble = A, low nibble any), `?5` (low nibble = 5); `X` is the same as `?`
  - **bit-mask**: `b:` + 8 of `0/1/x`, where `x` = don't-care bit, e.g. `b:1xxxxxx1` checks only the top and bottom bits
  - mix: `AA b:1001xxxx ?5` = byte0 must be `AA`, byte1 high nibble `1001` / low nibble any, byte2 low nibble `5`
- **Field-level** — "the sub-field at some offset == X" is expressed by padding wildcards up to that offset + "prefix" mode (e.g. byte 3 bit0 must be 1: match `?? ?? ?? b:xxxxxxx1`, mode = prefix).
- **Backward compatible** — spaces are just separators, plain HEX is joined across spaces (`A B` = 0xAB); exact/wildcard bytes parse byte-for-byte identically to before, so existing rules are unchanged. All three modes (contains / equals / prefix) honor masks; bit-masks apply in HEX mode only.- Real-time matching and the **offline rule tester** share one parser, so both gain it; trilingual UI (placeholder + a "bit/nibble mask" section in help); adds `tests/test_match_mask.py` (17 cases); no new dependencies.

---

## What's New in v1.1.7

Auto-reply gains a **Modbus RTU slave** mode — turn the whole engine into a slave and auto-answer a master without real hardware:

- **Modbus RTU slave** (new "Modbus slave" button atop the auto-reply dialog): enable + slave address + register table (seed initial values by "space · start address · value"; addresses accept `0x` / decimal, coils use 0/1). Once on, the engine auto-answers the master's reads/writes:
  - reads: `01` coils / `02` discrete inputs / `03` holding registers / `04` input registers;
  - writes: `05` single coil / `06` single register / `0F` multiple coils / `10` multiple registers (writes mutate the runtime registers and read back);
  - illegal function / out-of-range address / illegal data return an **exception response** (`0x80|func` + exception code).
- **Robust framing** — RTU has no header, so frames are split by "function-code length + CRC self-consistency" with cross-packet buffering; on a CRC mismatch it resyncs byte-by-byte, so noise / misalignment never desyncs it permanently.
- **Reply to the requester** — as a TCP server with multiple clients, the response goes back to exactly the client that asked (per-client half-packet buffer, cleared on disconnect).
- **Fault injection still applies** — global drop / bad-CRC / bad-length still hit Modbus responses, to stress-test the master's retry / tolerance.
- When Modbus is on, rules / state machine / header-framing step aside — the dialog collapses those sections and keeps only fault injection plus a prominent banner (no more "looks enabled but doesn't reply").
- Fixes dark-theme checkboxes that didn't show checked / unchecked (added `::indicator` styling). Trilingual UI; adds `tests/test_modbus_slave.py` (the repo's first automated test); no new dependencies; Modbus is off by default (behaves exactly like v1.1.6 when off).

---

## What's New in v1.1.6

Auto-reply gains a **multi-step state machine** — chain rules into a frame-sequence handshake / session:

- **State machine box** (top of the auto-reply dialog): enable / initial state / live current state / reset. Each rule gets two optional fields:
  - **only state (when)** — the rule matches only when the current state equals it (comma-separate several, names may contain spaces, blank = any state / wildcard);
  - **go to (goto)** — after this rule replies, set the current state to it.

  Use it for "only reply to B after receiving A", a different reply per handshake stage, etc. The when/goto columns appear only when the state machine is enabled.
- **Tester sync** — the offline rule tester shows the current state, the state it would move to after replying, and a "matched by content but not by state → would not reply" hint (preview = what's actually sent; state isn't advanced).
- **Robust transitions** — goto advances only after the reply is **actually sent** (not on delay-not-elapsed / disconnected / no client / send failure / fault-drop), so host retries still hit the current state.
- **Concurrency-serialized** — while a goto reply (incl. multi-part `|` + inter-part delay) is in flight, later frames are queued (bounded FIFO) and processed in receive order — no out-of-order transitions under random delays.
- Disconnect / reconnect / toggle / config import / manual reset returns the machine to its initial state; editing rules does **not** interrupt an in-progress handshake. Trilingual UI; no new dependencies; the state machine is off by default (behaves exactly like v1.1.5 when off).

---

## What's New in v1.1.5

Five auto-reply upgrades — from "usable" to "polished + stress-capable":

- **Checksum segments (inner / extra)** — each reply can add N segments: checksum a sub-range `[start..end]`, written at an offset or appended, computed in order before the row's tail checksum. With `{rN}` placeholder echo, the inner CRC **recomputes automatically** as echoed fields change (no more hardcoding an outer Sum + inner CRC). Opened via the per-row "Chk segs" button.
- **Rule tester (offline)** — top-bar **Test**: enter one HEX frame → see which rule matches and the reply preview (placeholders + checksum-segment / tail-checksum all computed). Shares the live compose path (preview = what's actually sent); nothing is sent / counted / `{seq}`-advanced.
- **Hit counters** — live "Hits N" per rule + **Reset stats** (counts on match + RX-checksum pass; runtime, not persisted).
- **Fault injection (global, host stress test)** — by probability: **Drop** (no reply, tests retransmit) / **Bad CRC** (flip last byte, tests checksum) / **Bad len** (drop last byte, tests framing). Injected frames are marked `⚠` in the data area.
- **Range delay** — the reply Delay field accepts `100` (fixed) or `100-300` (random jitter per send, simulates device turnaround).
- The "Header + Length framing" and "Fault injection" boxes get one-line descriptions + a `?` help button with examples.

---

## What's New in v1.1.4

Stronger **auto-reply** framing plus **multi-send** polish:

- **Auto-reply "Header + Length framing"**: for protocols with a header + length field (e.g. `AA BB | seq | len | data | sum`), enter the header, length-field offset/width/endian and fixed frame overhead — frames are split at their real boundaries across packets, correctly handling serial **packet join/split** (more accurate than the idle-timeout approach, no added delay). Enable it via the checkbox at the top of the dialog.
- **Multi-send: draggable name column + Select all**: drag the divider between the name and data fields to widen the name column (long names become fully visible, all rows synced); a "Select all / none" checkbox added at the top.
- **Window min / max**: multi-send and keyword-highlight dialogs get minimize / maximize buttons.

---

## What's New in v1.1.3

A **bug-fix release** — same features as 1.1.2, with three UX fixes:

- **Drag-selection in the data area "eaten" by new data**: after selecting text with the mouse, incoming data extended the native selection along with the appended text, so freshly received lines got highlighted too. The selection is now pinned by its original offset on append, so new data no longer bleeds into it.
- **Frameless title bar lost after dragging off the top of the screen**: once dragged above the top edge (title bar out of view), the window could no longer be grabbed back. Dragging is now clamped to the screen work area — the title bar always stays on-screen (never past the top, full bar at the bottom, 80px grabbable on each side), multi-monitor aware.
- **"Check for Update" dialog: long notes truncated & icon top clipped**: very long release notes blew up the dialog, cutting off text and squeezing out the icon. Notes now sit in a height-capped scroll area (scrollable when long) and the dialog auto-sizes to its content.

---

## What's New in v1.1.2

Major **Auto-reply** upgrade and several developer-productivity additions.

**Auto-reply** (top-right `?` opens a help window with 6 worked examples):
- **Multi-frame reply**: split reply with `|` (e.g. `06 | 04 03 02 01`) — segments sent sequentially with Delay (great for ACK + DATA protocols)
- **HEX wildcard `??`**: `54 ?? 03` matches "starts with 54, byte-2 is 03, anything in between" — fewer rules
- **Reply placeholders**: `{rN}` `{rN-M}` echo bytes / `{rN+K}` `{rN^K}` arithmetic / `{seq}` counter / `{ts}` ms timestamp
- **Four timing controls**: Frame gap (Modbus de-framing) / RX checksum / reply Delay (turnaround) / Cooldown (anti-storm)
- **Double-click the "Auto-reply" button** toggles the master switch; the button highlights when enabled

**Send box**:
- **Command history** with ↑/↓ (FIFO 100, persisted across sessions). Up at first line / Down at last line.
- **Dynamic fields**: `{count}` 1-byte counter (rolls back on send failure) / `{ts}` 4-byte ms timestamp / `{randN}` N random bytes (N=1..256). Hover for full syntax tooltip.

**Connection**: **Auto-reconnect** for unexpected disconnects (runtime drop / peer closed / TCP connect fail), with 1/2/4/8/16/30s backoff. Manual open failures don't loop.

**Session config import/export** (data area right-click → "Import/Export Config", or Ctrl+Shift+S / Ctrl+Shift+O): one JSON file with 35+ settings (connection, theme/lang, multi-send, keyword highlight, auto-reply, frame parser, plot config). Applied immediately on import.

**Misc**:
- **Ctrl+F** global shortcut — focus from anywhere
- Plot and Frame Parser get `?` help buttons with 5 worked examples each
- Replaced QMessageBox with themed `InfoDialog` (rounded card + ✓/✕ icon)

---

## What's New in v1.1.1

Two data-analysis tools, both opened from the title bar:

- **Waveform plot** (title bar **Plot**) — parses numbers out of incoming RX data and draws them as live multi-channel scrolling curves (oscilloscope-style).
  - Three parse modes: **delimiter** (comma/space/Tab/semicolon/auto — one curve per column), **regex** (one per capture group), and **HEX byte fields** (for binary protocols — pick values by `offset:type` + header filter);
  - per-channel show/hide & color, window size (points), X axis by sample index or time, pause/clear/export CSV; the window can be minimized/maximized/resized.
- **Protocol frame parser** (title bar **Frames**) — decodes each received frame into a "name = value" table.
  - **Multiple frames / rules**: each rule row is "header | field definition"; each frame matches the first rule whose header prefix fits;
  - an **All** tab for the mixed frame stream plus one column-split tab per rule; index column + raw-frame column;
  - field types are numeric + `hexN`/`strN`; append `x` to a numeric type to show it in hex;
  - Ctrl+C / right-click copy & select-all, export CSV, pause, draggable column widths, scroll-lock + "↓ latest".
- The plot and the frame parser share one set of header/field definitions; new deps pyqtgraph + numpy (bundled in the installer). Trilingual UI kept in sync.

---

## What's New in v1.1.0

The status-bar RX/TX counters are upgraded from plain byte counts to **bytes · packets · live rate**:

- **Packet counts** — RX counts one packet per arriving chunk; TX counts one per successful send.
- **Live rate** — current RX/TX throughput (B/s), sampled at 1 Hz; always running, decays to zero after disconnect.
- **Hover for details** — hovering the RX/TX label shows a tooltip with total / packets / current rate / **peak rate** / error count (a ⚠ marker is appended to the label when errors > 0).
- **Reset stats** — **right-click the status bar → "Reset stats"** to zero all counters (data area untouched; follows language/theme).
- **macOS fix** — fixed transparent tooltip backgrounds on macOS that made hover text unreadable (now drawn as an opaque popup).

---

## What's New in v1.0.9 (Unified)

Merged from the serial-only SerialTool and the network-only NetworkTool — one tool now does **both serial and network**:

- **Serial support** — the **Type** dropdown in the Connection card gains **Serial**, alongside UDP / UDP Multicast / TCP Server / TCP Client; serial params (port / baud / data bits / parity / stop bits) + hot-plug port scanning. See [Connection](#connection).
- **Unified branding** — renamed to **CommTool**, with its own install identity; the old NetworkTool config is reused automatically on first launch.
- All other features (RX/TX, checksums, highlighting, logging, multi-send, themes, trilingual UI) are unchanged.

---

## What's New in v1.0.8

- **Highlight flicker fix** — with keyword/search highlighting on, newly received data at the bottom no longer flashes fully highlighted for a moment (the highlight selection no longer extends with appended text).

---

## What's New in v1.0.7

- **Stability** — the TCP Client connection now has a timeout: connecting to an unreachable address no longer waits the OS default ~20 s before reporting failure (a 10 s timeout shows "Connection timed out"); UDP clears its last-peer cache on close, so a reused connection never replies to the previous session's stale peer address.
- **Search experience** — ▲/▼ search navigation no longer stutters on large buffers; when using **search only** (Ctrl+F without any keyword-highlight rules), matches in newly received live data are now highlighted, counted and included in ▲/▼ navigation in real time.
- **Other** — version-string parsing now handles pre-release suffixes (e.g. `1.0.7-rc1`) correctly; added boundary guards to the search bar.

---

## What's New in v1.0.5

- **Data-area search (Ctrl+F)** — press Ctrl+F in the Data area to open the find bar: type a keyword to **highlight all matches**, use **▲/▼ to jump** between them, with a live "current/total" counter; ESC closes it.
- **Multi-monitor fixes** — fixes to status-bar rendering, window dragging and taskbar minimize on multi-display setups (maximize/minimize align to the correct monitor work area).
- **Dark-theme contrast** — improved text/background contrast for search and keyword highlights under dark themes.
- **Tray single-click toggle** — single-clicking the tray icon toggles show/hide of the window.

---

## What's New in v1.0.4

- **Online Update** — the tray icon's right-click menu gains an **About** entry that opens an **About** dialog (app icon, name, version, a short description, and a **Check for Updates** button). Click **Check for Updates** to fetch the latest version from the update source and compare it with the one you're running. If a newer version exists, the dialog shows the new version number, the release notes, and a **Download and Update** button: click it to download (with a live progress percentage), and when the download finishes the **regular install wizard** launches so you finish the upgrade yourself by clicking **Next / Install** (it is not a silent install). If you're already on the latest version, the dialog just tells you so. The update source tries the intranet mirror first and automatically falls back to the public one (the CommTool branch on GitHub); each source has an 8-second timeout, so it never hangs for long even on an external network. The downloaded file is integrity-checked, and closing the dialog mid-download cancels the download automatically. (See [Online Update](#online-update).)

---

## What's New in v1.0.2

- **Compact UI** — smaller fonts, inputs and toggle switches, plus tighter card spacing, so more fits on screen
- **Keyword-highlight groups** — the highlight dialog now manages **rule groups**: a group list on the left (new / rename by double-click / delete), and a **group dropdown** in the Data-area title bar selects the active group (with an **(Off)** item to disable all highlighting). The group you're editing and the active group are independent
- **Multi-Send groups** — the Multi-Send dialog now manages **command groups**: a group list on the left (new / delete / rename by double-click); each command row gains a **Name** column and a per-row **Delay (ms)** column
- **Multi-Send quick bar** — a row above the Send box: **[Multi-Send (edit)]** **[▶ Cycle]** **[group dropdown]**, plus every command in the active group laid out as a button you click to send directly — no dialog needed. Cycle send waits each row's own delay before moving on
- **Log split by file size** — a dropdown next to **Log to File** offers **No split / 1M / 2M / 5M / 10M / 20M / 50M / 100M**, plus custom typed values (e.g. `3M`, `500K`). When a log reaches the size it rolls over to a new file (original name + `_001` / `_002` …)
- **Log path in status bar** — the bottom-right shows **📝 path** of the current log file (elided in the middle, full path on hover); blank when not logging. Vertical separators now divide the status-bar items
- **Localized right-click menu** — the Data area's context menu (**Copy / Select All / Clear / Save**) now follows the app language instead of Qt's system-language default
- **Performance & stability** — dialog-edit debouncing, much faster theme-switch recolor on large buffers (no more freeze when switching themes after timed sending piles up data), and several edge-case fixes

---

## What's New in v1.0.1

- **HiDPI scaling** — UI and fonts stay properly sized on high-resolution displays (no longer tiny)
- **Scroll-lock / auto-follow** — scrolling up in the Data area freezes the view while data keeps arriving; a floating **↓ Latest** button (bottom-right) jumps back to the bottom and resumes auto-follow
- **Click to highlight** — click any line in the Data area to highlight it (click again to clear)
- **Theme-aware recolor** — switching themes recolors existing Data-area text by role (timestamp / RX / TX), so light↔dark switches never leave text invisible
- **Multi-Send dialog** — opened from the **Multi-Send** button in the Send area; manage multiple data entries and cycle through them
- **Keyword Highlighting** — opened from the **Highlight** button in the Data-area title bar; color-highlight lines that match your keyword rules
- **Matches only** filter — show only the lines that match a keyword, hiding the rest
- **Themed dialog title bars** — dialog native title bars now follow the dark/light theme
- **Auto-sizing connection labels** — English labels in the Connection settings are no longer clipped
- **Consistent HEX display** — the Data area's HEX vs text view is now governed solely by the **HEX View** switch, so RX and TX always display the same way (independent of **HEX Send**)

---

## Features

### Connection

The top-left **Connection** card configures the connection. The first row is a **Type** dropdown with **6** options (**Serial** is the default on a fresh install):

- **Serial**
- **UDP**
- **UDP Multicast**
- **TCP Server**
- **TCP Client**
- **Virtual** — no hardware; optional loopback; also the injection target for `.ctrec` replay

The fields below change to match the selected type:

- **Serial**
  - **Port** — dropdown of detected COM ports, with a **⟳** button to refresh manually (a background thread also rescans for hot-plug)
  - **Baud** — editable dropdown (common 1200–2000000)
  - **Data bits** (5/6/7/8, default 8), **Parity** (None/Even/Odd/Mark/Space), **Stop bits** (1/1.5/2)
  - click **Open Serial** to connect

- **UDP**
  - **Local IP** — dropdown of your local NIC IPs (`0.0.0.0` = all NICs)
  - **Local Port**
  - **Use remote** toggle — off = reply to the last sender; on = enables **Remote IP** / **Remote Port** and always sends to that address
    - When **off**, each incoming datagram refreshes the greyed **Remote IP** / **Remote Port** to the **last sender's address** (so you can see who you're talking to / who a send replies to; only updated when the peer changes). After you receive from a peer, just turn **Use remote** on to lock onto it — the address is already pre-filled
- **UDP Multicast**
  - **Local IP** — the interface to use (`0.0.0.0` = default)
  - **Group Addr** — e.g. `239.0.0.1` (must be in `224.0.0.0`–`239.255.255.255`)
  - **Local Port**
- **TCP Server**
  - **Local IP**, **Local Port** → **Listen**
  - Once clients connect, a **Target** dropdown appears so you can pick a specific client or **All** (broadcast) to send to
- **TCP Client**
  - **Remote IP** (required), **Remote Port** (required) → **Connect**
- **Virtual**
  - Start without hardware; optional **Loopback**
  - Used to verify auto-reply / scripts / sequences, and as the sink for session replay

**Action button** — its text depends on the protocol and state:

| Type | Button |
|----------|--------|
| Serial | Open Serial / Close Serial |
| UDP | Open / Close |
| UDP Multicast | Open / Close |
| TCP Server | Listen / Stop |
| TCP Client | Connect / Disconnect |
| Virtual | Start Virtual / Stop Virtual |

Once connected, the whole card **locks and grays out** — disabled fields are shown greyed until you close / stop / disconnect.

### Receiving Data

RX and TX share one view; arrows indicate direction:

| Marker | Meaning |
|--------|---------|
| `← RX` | data received |
| `→ TX` | data sent |

**Display options** (Data card)

- **View mode** — Text / HEX / HEX dump / Numeric (mutually exclusive); RX and TX share the same mode (independent of **HEX Send**). Dump has configurable bytes-per-row; Numeric has type / endian options
- **Word Wrap** — wrap long lines; off → horizontal scrollbar
- **Encoding** — pick Auto / UTF-8 / GBK / GB2312 / GB18030 / Big5 / ASCII / Latin-1; affects RX decode, TX text encode, and file load
- **Timestamp** — prefix each new block with `[2026/06/03 09:48:54 023]` plus the direction arrow ← / →
- **Packet Split** + **Timeout ms** — start a new block when no data arrives for the configured ms (default 20 ms; great for Modbus)
- **Line Split** + **Newline mode** — split lines on `\r\n` / `\r` / `\n`
  - **Auto**: recognises all three (Windows + Linux + classic Mac)
  - **CRLF / LF / CR**: strict mode, only the chosen terminator counts
- **Log to File** — Xshell-style live log to a `.log` file, **what you see is what gets saved** (timestamps, arrows, HEX/ASCII included)
  - **Split by size** — a dropdown next to the switch offers **No split / 1M / 2M / 5M / 10M / 20M / 50M / 100M**, or type a custom value (e.g. `3M`, `500K`). When the log reaches the chosen size it rolls over to a new file (original name + `_001` / `_002` …)
- **Max Lines** — caps the displayed line count; older lines are dropped (keeps long runs snappy). **Log file is not affected.**
- **Matches only** — a toggle button in the Data-area title bar (highlighted when on) that hides every line except those containing a keyword match (see [Keyword Highlighting](#keyword-highlighting))

**Scroll-lock / auto-follow** — by default the view auto-scrolls to the newest data. Scroll up and the view **freezes** so you can read history while data keeps arriving in the background; a floating **↓ Latest** button appears in the bottom-right. Click it (or scroll back to the bottom) to jump to the latest data and resume auto-follow.

**Highlight a line** — click any line in the data area to highlight it; click it again to clear the highlight.

**Keyword highlighting** — click the **Highlight** button in the card title bar to define color rules that mark matching lines (see [Keyword Highlighting](#keyword-highlighting)).

**Font size** — the `A−` / `A+` buttons in the top-right adjust the data area font (7–28 pt)

**Save / Clear** — buttons at the bottom of the card; save filename is `save_log_YYYYMMDD_HHMMSS.log`

**Right-click menu** — localized context menu: **Copy / Select All / Clear / Save**, plus **Convert to Text** / **Convert to HEX** for the current selection (result dialog + clipboard; 64 KiB cap)

### Sending Data

- **HEX Send** — input is parsed as bytes from a hex string; all of these work:

| Input | Parsed as |
|-------|-----------|
| `AA BB CC DD` | 4 bytes |
| `AABBCCDD` | 4 bytes |
| `AA-BB-CC-DD` | 4 bytes |
| `AA:BB:CC:DD` | 4 bytes |
| `0xAA 0xBB 0xCC` | 3 bytes |
| `// comment\nAA BB` | 2 bytes |
| `/* block */ AA BB` | 2 bytes |

  Stray non-hex characters (e.g. `AA ZZ BB`) are rejected with a format error.

- **Append CRLF** + **mode (CRLF / LF / CR)** — auto-append a newline after every send (handy for AT commands)
- **Auto Send** + **Period ms** — send the current content periodically; minimum 10 ms; stops automatically if a send fails (not connected, bad format, no target, etc.)
- **Checksum** (9 algorithms + None) — append a checksum to each transmission

| Algorithm | Bytes | Notes |
|-----------|-------|-------|
| None | 0 | No checksum |
| ADD8 | 1 | Simple byte sum |
| ~ADD8 | 1 | Bitwise NOT of the sum |
| XOR8 | 1 | XOR of all bytes |
| CRC8 | 1 | Polynomial 0x07 (standard CCITT) |
| **MOBUS** | 1 | **CRC8 with polynomial 0x31**, common in Chinese embedded code |
| ModbusCRC16 | 2 | Modbus RTU standard, little-endian |
| CCITT-CRC16 | 2 | CRC-16/CCITT-FALSE, big-endian |
| CRC32 | 4 | Ethernet / ZIP standard |
| ADD16 | 2 | 16-bit sum |

**Load File** — load a file into the send box (HEX mode auto-converts bytes to a hex string)

**Multi-Send** — the **Multi-Send** button opens a dialog for managing several data entries at once (see [Multi-Send](#multi-send))

### Keyword Highlighting

Click the **Highlight** button in the Data-area title bar to open the keyword-highlight dialog. Here you can define multiple keyword rules, each of which:

- has its own **color**, applied either as a **Background** or **Text** color
- is **scoped** to RX / TX / both
- matches as a **case-sensitive substring**

Timestamps are skipped when matching (so a keyword won't accidentally match the time prefix). Rules are persisted across restarts. Pair this with the **Matches only** toggle button in the Data-area title bar to hide every non-matching line.

**Rule groups** — rules are organised into **groups** so you can keep separate rule sets for different devices or protocols. A group list down the left of the dialog lets you **create** a new group, **rename** one (double-click), or **delete** it. Back in the Data-area title bar, a **group dropdown** picks which group is currently **active** — choose **(Off)** to disable all highlighting. The group you're editing in the dialog and the active group are independent, so you can tweak one set while another stays in effect.

### Multi-Send

Click the **Multi-Send** button in the Send area to open the multi-send dialog:

- Each **row** is one data entry with its own **checkbox**, a **Name** column, and a per-row **Delay (ms)** column
- Each row carries its own **HEX**, **newline**, and **checksum** settings
- Check several rows and use **Cycle-Send** to loop through them; each row waits its own **Delay (ms)** before the next is sent
- Rows are persisted across restarts

**Command groups** — commands are organised into **groups** so you can keep separate command sets for different tasks. A group list down the left of the dialog lets you **create** a new group, **rename** one (double-click), or **delete** it.

**Quick bar** — a row sits just above the Send box in the main window: **[Multi-Send (edit)]** opens the dialog, **[▶ Cycle]** cycle-sends the active group, and a **group dropdown** picks the active group. Every command in that group is laid out as a button — click it to send that command directly, without opening the dialog.

### Interface

- **Window chrome**: Windows / Linux use a frameless custom title bar with rounded cards and soft shadows; macOS uses the native title bar (traffic lights)
- Left sidebar (connection / data / send settings) + right data area; the divider is **draggable**
- On Windows: drag the title bar to move; double-click it to maximise; native edge resize

### Multilingual UI

A dropdown next to the title in the top-left toggles between **简体中文 / English / 繁體中文**, no restart required — all UI text (labels, buttons, placeholders, error messages, file dialogs) switches instantly.

### Themes

A second dropdown in the top-left (right next to the language picker) switches the overall color scheme. **9 themes** are available, each with a distinctive look that affects the whole window — sidebar cards, buttons, data area, status bar, even the close-confirm dialog:

| Theme | Mode | Vibe |
|-------|------|------|
| Default | light | Light default — light cards on a soft grey background |
| Dark | dark | Generic VSCode-style dark grey |
| One Half Light | light | Atom editor light, clean off-white |
| One Half Dark | dark | Atom editor dark, blue-tinted grey |
| Solarized Light | light | Cream background, easy on the eyes |
| Solarized Dark | dark | Deep teal-blue, classic terminal scheme |
| Tango Dark | dark | Linux-style charcoal |
| Campbell | dark | Pitch black (Windows Terminal default) |
| Ubuntu | dark | Aubergine purple |

Theme switching affects newly received data immediately, and existing Data-area text is recolored by role (timestamp / RX / TX) to match the new theme, so switching between light and dark never leaves text invisible. The selected theme is remembered across restarts.

### Hover Tooltips

Hover over any option label in the Data / Send cards to see a short explanation. For example, hovering "Packet Split" shows:

```
Start a new block when no data arrives for longer than the timeout below.
Merges burst data on the same line
```

### System Tray

Clicking the `×` button shows a three-choice dialog:

| Choice | Behaviour |
|--------|-----------|
| Minimize to Tray (default) | Hide window to the system tray |
| Quit | Real exit; saves config |
| Cancel | Don't close |

Tray icon:
- Single / double click → restore window
- Right-click → "Show Window" / "Quit"

### Online Update

Right-click the tray icon and choose **About** to open the **About** dialog. It shows the app icon, name, current version and a short description, plus a **Check for Updates** button.

- **Check for Updates** — fetches the latest version from the update source and compares it with the one you're running:
  - **A newer version is available** → the dialog shows the new version number, the **release notes**, and a **Download and Update** button. Click it to download (a **progress percentage** is shown). When the download completes, the **regular install wizard** opens — finish the upgrade yourself by clicking **Next / Install** (this is **not** a silent install).
  - **Already up to date** → the dialog simply tells you you're on the latest version.
- **Update sources** — the **intranet mirror** is tried first and the tool automatically **falls back to the public one** (the CommTool branch on GitHub); each source has an **8-second timeout**, so it never hangs for long even on an external network.
- **Integrity check** — the downloaded file is verified for integrity before the wizard runs.
- **Cancel anytime** — closing the dialog while a download is in progress cancels the download automatically.

### Auto-saved Configuration

On exit, settings are written to `settings.ini` in the install directory; on next launch **everything is restored**:

- Window position and size (including maximised state)
- Splitter position
- Current language
- All switches / input fields / dropdown selections
- Send box content, font size, max line count

If the install directory is read-only (e.g. Program Files without admin), the config falls back to `%APPDATA%\CommTool\settings.ini` automatically.

---

## Tips

- **Modbus debugging**: View mode = HEX + HEX Send + Packet Split (20 ms) + ModbusCRC16
- **AT command debugging**: View mode = Text + Append CRLF + Line Split (Auto)
- **Long-running monitoring**: enable Log to File → open the `.log` later in Notepad++ / VS Code for analysis
- **Comments in HEX**: in the HEX send box you can use `// line`, `/* block */`, `# line` comments — they're stripped at send time
- **Custom layout**: every divider is draggable; once you find a comfortable ratio it's persisted across sessions

---

## Status Bar

Items are divided by vertical separators.

Bottom-left:

- Connection state (red / green dot), one of:
  - `● Disconnected`
  - `● COM3 @ 115200` (serial)
  - `● UDP addr:port`
  - `● Multicast addr:port`
  - `● TCP listening addr:port`
  - `● Connected addr:port`
  - `● Connecting…`
- `RX: bytes` (auto-scales to B / KB / MB)
- `TX: bytes`

Bottom-right:

- **📝 log path** — the current log file (elided in the middle, full path on hover); blank when not logging
- current **version** (`v1.5.3`) — turns into a clickable “● Update vX” badge when a newer version is available

---

## FAQ

**Q: TCP Server "Listen" fails / port in use?**
A: The port is taken by another program or needs permission. Use another port or close the conflicting program.

**Q: TCP Client can't connect?**
A: Check the remote IP / port, that the peer is actually listening, and that the firewall allows the connection.

**Q: UDP send says "No send target"?**
A: "Use remote" is off and no peer has sent to you yet. Turn on **Use remote** and fill in the remote address, or wait for the peer to send to you first.

**Q: UDP multicast receives nothing?**
A: Check the firewall, that sender and receiver use the same group address and port, and that they're on the same subnet / NIC.

**Q: Timed send not working?**
A: The minimum period is 10 ms and you must stay connected. It pauses automatically on disconnect.

**Q: Chinese characters show as garbled text?**
A: Auto mode tries UTF-8 first and falls back to GBK. If that's still wrong, the device may use another encoding (e.g. Big5) — pick it explicitly from the **Encoding** dropdown, or switch **View mode** to HEX / HEX dump to inspect the raw bytes.

**Q: HEX send reports "length must be even"?**
A: HEX is parsed byte-by-byte. `AA B` has 3 hex chars which can't pair up — write it as `AA 0B` or `AAB0`.

**Q: Does the log file slow things down when it gets large?**
A: Writes are append-only — even hundreds of MB stay smooth. **Max Lines** only limits the on-screen display, not what's written to disk.

---

## System Requirements

- Windows 10 / 11 (64-bit); macOS packages are also published on Releases
- ~100 MB disk space
- Linux: run from source / self-build; no official installer yet

---

Found a bug or have a feature request? Get in touch with the developer.
