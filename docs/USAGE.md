# NetworkTool Usage Guide

An iOS-style network debugging tool (TCP/UDP), designed for embedded development and protocol debugging.

![UI preview](./icon_preview.png)

---

## Contents

- [Quick Start](#quick-start)
- [Features](#features)
  - [Network](#network)
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

1. Double-click the **NetworkTool** icon on your desktop
2. In the left **Network** panel, pick a **Protocol**, fill in the address / port, then click **Open** / **Connect** / **Listen** (depending on protocol)
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below

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

- **Online Update** — the tray icon's right-click menu gains an **About** entry that opens an **About** dialog (app icon, name, version, a short description, and a **Check for Updates** button). Click **Check for Updates** to fetch the latest version from the update source and compare it with the one you're running. If a newer version exists, the dialog shows the new version number, the release notes, and a **Download and Update** button: click it to download (with a live progress percentage), and when the download finishes the **regular install wizard** launches so you finish the upgrade yourself by clicking **Next / Install** (it is not a silent install). If you're already on the latest version, the dialog just tells you so. The update source tries the intranet mirror first and automatically falls back to the public one (the NetworkTool branch on GitHub); each source has an 8-second timeout, so it never hangs for long even on an external network. The downloaded file is integrity-checked, and closing the dialog mid-download cancels the download automatically. (See [Online Update](#online-update).)

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
- **Auto-sizing Network labels** — English labels in the Network settings are no longer clipped
- **Consistent HEX display** — the Data area's HEX vs text view is now governed solely by the **HEX View** switch, so RX and TX always display the same way (independent of **HEX Send**)

---

## Features

### Network

The top-left **Network** card configures the connection. The first row is a **Protocol** dropdown with 4 options (**UDP** is the default):

- **UDP**
- **UDP Multicast**
- **TCP Server**
- **TCP Client**

The fields below change to match the selected protocol:

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

| Protocol | Button |
|----------|--------|
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
- Left sidebar (network / data / send settings) + right data area; the divider is **draggable**
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
- **Update sources** — the **intranet mirror** is tried first and the tool automatically **falls back to the public one** (the NetworkTool branch on GitHub); each source has an **8-second timeout**, so it never hangs for long even on an external network.
- **Integrity check** — the downloaded file is verified for integrity before the wizard runs.
- **Cancel anytime** — closing the dialog while a download is in progress cancels the download automatically.

### Auto-saved Configuration

On exit, settings are written to `settings.ini` in the install directory; on next launch **everything is restored**:

- Window position and size (including maximised state)
- Splitter position
- Current language
- All switches / input fields / dropdown selections
- Send box content, font size, max line count

If the install directory is read-only (e.g. Program Files without admin), the config falls back to `%APPDATA%\NetworkTool\settings.ini` automatically.

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
  - `● UDP addr:port`
  - `● Multicast addr:port`
  - `● TCP listening addr:port`
  - `● Connected addr:port`
  - `● Connecting…`
- `RX: bytes` (auto-scales to B / KB / MB)
- `TX: bytes`

Bottom-right:

- **📝 log path** — the current log file (elided in the middle, full path on hover); blank when not logging
- current **version** (`v1.0.4`)

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
