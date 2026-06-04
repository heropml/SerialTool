# SerialTool Usage Guide

An iOS-style serial port debugging tool, designed for embedded development and protocol debugging.

![UI preview](./icon_preview.png)

---

## Quick Start

1. Double-click the **SerialTool** icon on your desktop
2. In the left **Serial Setup** panel, pick a port and baud rate, then click **Open Port**
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below

---

## Features

### Serial Setup

- Auto-detects available COM ports, hot-plug refresh every 1.5 s in the background
- The port dropdown also shows the device description (helpful with multiple USB-to-serial adapters)
- Baud rate: 1200–921600, or type any custom value
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
- **Max Lines** — caps the displayed line count; older lines are dropped (keeps long runs snappy). **Log file is not affected.**

**Font size** — the `A−` / `A+` buttons in the top-right adjust the data area font (7–28 pt)

**Save / Clear** — buttons at the bottom of the card; save filename is `save_log_YYYYMMDD_HHMMSS.log`

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

### Interface

- **Frameless window** + **iOS-style rounded cards** with soft shadows
- Left sidebar (serial / data / send settings) + right data area; the divider is **draggable**
- Drag the title bar to move; double-click it to maximise
- Native edge resize (feels identical to a system window)

### Multilingual UI

The dropdown in the top-right toggles between **简体中文 / English / 繁體中文**, no restart required — all UI text (labels, buttons, placeholders, error messages, file dialogs) switches instantly.

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

Bottom-left:

- `● Disconnected` / `● Connected COMxx @ baud` (red / green dot)
- `RX: bytes` (auto-scales to B / KB / MB)
- `TX: bytes`

Bottom-right: current **version** (`v1.0.0`).

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
