# CommTool Usage Guide

An iOS-style serial & network debugging tool — serial port plus TCP/UDP in one app, designed for embedded development and protocol debugging.

![UI preview](./icon_preview.png)

---

## Contents

- [Quick Start](#quick-start)
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
2. In the left **Connection** panel, pick a **Type** (serial or network), fill in the serial parameters / network address & port, then click **Open Serial** / **Open** / **Connect** / **Listen** (depending on type)
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below

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

- **Compact UI** — smaller fonts, inputs and iOS switches, plus tighter card spacing, so more fits on screen
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

The top-left **Connection** card configures the connection. The first row is a **Type** dropdown with 5 options — serial plus network (**Serial** is the default on a fresh install):

- **Serial**
- **UDP**
- **UDP Multicast**
- **TCP Server**
- **TCP Client**

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

**Action button** — its text depends on the protocol and state:

| Type | Button |
|----------|--------|
| Serial | Open Serial / Close Serial |
| UDP | Open / Close |
| UDP Multicast | Open / Close |
| TCP Server | Listen / Stop |
| TCP Client | Connect / Disconnect |

Once connected, the whole card **locks and grays out** — disabled fields are shown greyed until you close / stop / disconnect.

### Receiving Data

RX and TX share one view; arrows indicate direction:

| Marker | Meaning |
|--------|---------|
| `← RX` | data received |
| `→ TX` | data sent |

**Display options** (Data card)

- **HEX View** — toggle hex / text (UTF-8 first; falls back to GBK for Chinese)
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

**Right-click menu** — right-click the data area for a localized context menu (**Copy / Select All / Clear / Save**) that follows the app language

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
- **Checksum** (10 algorithms) — append a checksum to each transmission

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

- **Frameless window** + **iOS-style rounded cards** with soft shadows
- Left sidebar (connection / data / send settings) + right data area; the divider is **draggable**
- Drag the title bar to move; double-click it to maximise
- Native edge resize (feels identical to a system window)

### Multilingual UI

A dropdown next to the title in the top-left toggles between **简体中文 / English / 繁體中文**, no restart required — all UI text (labels, buttons, placeholders, error messages, file dialogs) switches instantly.

### Themes

A second dropdown in the top-left (right next to the language picker) switches the overall color scheme. **9 themes** are available, each with a distinctive look that affects the whole window — sidebar cards, buttons, data area, status bar, even the close-confirm dialog:

| Theme | Mode | Vibe |
|-------|------|------|
| Default | light | iOS-style — light cards on a soft grey background |
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

- **Modbus debugging**: HEX View + HEX Send + Packet Split (20 ms) + ModbusCRC16
- **AT command debugging**: HEX View off + Append CRLF + Line Split (Auto)
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
- current **version** (`v1.1.5`)

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
A: Auto mode tries UTF-8 first and falls back to GBK. If that's still wrong, the device may use another encoding (e.g. Big5) — pick it explicitly from the **Encoding** dropdown, or switch to HEX View to inspect the raw bytes.

**Q: HEX send reports "length must be even"?**
A: HEX is parsed byte-by-byte. `AA B` has 3 hex chars which can't pair up — write it as `AA 0B` or `AAB0`.

**Q: Does the log file slow things down when it gets large?**
A: Writes are append-only — even hundreds of MB stay smooth. **Max Lines** only limits the on-screen display, not what's written to disk.

---

## System Requirements

- Windows 10 / 11 (64-bit)
- ~100 MB disk space

---

Found a bug or have a feature request? Get in touch with the developer.
