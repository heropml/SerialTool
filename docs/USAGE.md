# SerialTool Usage Guide

An iOS-style serial port debugging tool, designed for embedded development and protocol debugging.

![UI preview](./icon_preview.png)

---

## Contents

- [Quick Start](#quick-start)
- [Features](#features)
  - [Serial Setup](#serial-setup)
  - [Receiving Data](#receiving-data)
  - [Sending Data](#sending-data)
  - [Keyword Highlighting](#keyword-highlighting)
  - [Multi-Send](#multi-send)
  - [Interface](#interface)
  - [Multilingual UI](#multilingual-ui)
  - [Themes](#themes)
  - [Hover Tooltips](#hover-tooltips)
  - [System Tray](#system-tray)
  - [Auto-saved Configuration](#auto-saved-configuration)
- [Tips](#tips)
- [Status Bar](#status-bar)
- [FAQ](#faq)
- [System Requirements](#system-requirements)

---

## Quick Start

1. Double-click the **SerialTool** icon on your desktop
2. In the left **Serial Setup** panel, pick a port and baud rate, then click **Open Port**
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below

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
- **High-speed baud rates** — the dropdown now includes 256000, 500000, 512000, 600000, 750000, 1000000, 1500000 and 2000000 (custom values still accepted)
- **Auto-sizing Serial-Setup labels** — English labels in Serial Setup are no longer clipped
- **Consistent HEX display** — the Data area's HEX vs text view is now governed solely by the **HEX View** switch, so RX and TX always display the same way (independent of **HEX Send**)

---

## Features

### Serial Setup

- Auto-detects available COM ports, hot-plug refresh every 1.5 s in the background
- The port dropdown also shows the device description (helpful with multiple USB-to-serial adapters)
- Baud rate: 1200–2000000 (including high-speed rates 256000, 500000, 512000, 600000, 750000, 1000000, 1500000, 2000000), or type any custom value
- Data bits 5/6/7/8, parity None/Even/Odd/Mark/Space, stop bits 1/1.5/2

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
- **Auto Send** + **Period ms** — send the current content periodically; minimum 10 ms; pauses automatically when the port closes
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
- Left sidebar (serial / data / send settings) + right data area; the divider is **draggable**
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

### Auto-saved Configuration

On exit, settings are written to `settings.ini` in the install directory; on next launch **everything is restored**:

- Window position and size (including maximised state)
- Splitter position
- Current language
- All switches / input fields / dropdown selections
- Send box content, font size, max line count

If the install directory is read-only (e.g. Program Files without admin), the config falls back to `%APPDATA%\SerialTool\settings.ini` automatically.

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

- `● Disconnected` / `● Connected COMxx @ baud` (red / green dot)
- `RX: bytes` (auto-scales to B / KB / MB)
- `TX: bytes`

Bottom-right:

- **📝 log path** — the current log file (elided in the middle, full path on hover); blank when not logging
- current **version** (`v1.0.4`)

---

## FAQ

**Q: "Access denied" when opening the port?**
A: Another program is holding it (another serial tool, an IDE's serial monitor, etc.). Close that one first.

**Q: Auto-send sometimes doesn't fire?**
A: The minimum period is 10 ms and the port must stay open. Auto-send pauses automatically if the port closes.

**Q: Chinese characters show as garbled text?**
A: Auto mode tries UTF-8 first and falls back to GBK. If that's still wrong, the device may use another encoding (e.g. Big5) — pick it explicitly from the **Encoding** dropdown, or switch to HEX View to inspect the raw bytes.

**Q: HEX send reports "length must be even"?**
A: HEX is parsed byte-by-byte. `AA B` has 3 hex chars which can't pair up — write it as `AA 0B` or `AAB0`.

**Q: Does the log file slow things down when it gets large?**
A: Writes are append-only — even hundreds of MB stay smooth. **Max Lines** only limits the on-screen display, not what's written to disk.

**Q: I unplugged the USB-to-serial adapter but the port list didn't refresh?**
A: Some drivers don't notify the system on unplug. Click the `⟳` button next to the port dropdown to force a refresh.

---

## System Requirements

- Windows 10 / 11 (64-bit)
- ~100 MB disk space

---

Found a bug or have a feature request? Get in touch with the developer.
