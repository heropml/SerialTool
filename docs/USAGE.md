# CommTool Usage Guide

**Serial debugger + network debugging tool** in one app — UART serial terminal and TCP/UDP share the same UI, for embedded development, device bring-up, Modbus / custom protocols, and communication log analysis.

![UI preview](./icon_preview.png)

---

## Contents

- [Quick Start](#quick-start)
- [What's New in v1.8.9](#whats-new-in-v189)
- [What's New in v1.8.8](#whats-new-in-v188)
- [What's New in v1.8.7](#whats-new-in-v187)
- [What's New in v1.8.6](#whats-new-in-v186)
- [What's New in v1.8.5](#whats-new-in-v185)
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
- [Install (Windows / macOS / Linux)](#install-windows--macos--linux)
- [System Requirements](#system-requirements)

---

## Quick Start

1. Install from [Releases](https://github.com/heropml/SerialTool/releases) (see [Install](#install-windows--macos--linux)), then double-click the **CommTool** icon
2. In the left **Connection** panel, pick a **Type** (serial / RTT / network / Virtual / BLE), fill in the parameters, then click **Open Serial** / **Connect** / **Listen** / **Start Virtual** (depending on type)
3. Received and sent data appear in the right-hand **Data** area; type what you want to send into the **Send** box below
4. Use **New Session** for multi-tab concurrent connections (serial / RTT / TCP / UDP / Virtual / BLE)

On an empty terminal, use the **Quick start** bar for a Virtual loopback, a bundled example, or the most recent project. Frame Builder can save reusable personal frame templates; Record / Replay indexes recently saved or opened `.ctrec` files. **Help → Export diagnostics** creates a redacted support ZIP. Webhooks default to public HTTPS; only enable the LAN / HTTP override for a service you trust.

---

## What's New in v1.8.9

- **Multiple RTT sessions** — Each tab can connect to a different J-Link, even when the targets use the same device model. Reopen the Probe list to refresh it.
- **RTT sends** — If the selected channel has no down buffer, CommTool shows a send notice and keeps the connection open.

## What's New in v1.8.8

- Terminal mode shows the current command as each keystroke is sent. Press Enter or click Send to transmit the selected line ending and clear the preview. Local echo follows cursor edits and deletions. Text committed through an input method is also sent.
- Each serial or RTT tab writes its own HEX or terminal text log, including in the background. Turning on live logging opens the file chooser on the first click. A manual reconnect prompts for a new file if logging was active. A file chosen during the handshake remains selected.
- Serial display, logs and recordings use the time of the underlying read. The RX status bar shows read chunks and, when configured, silence-delimited groups and decoded frames. Hover over RX for byte and chunk rates. The 20 ms boundary uses the interval between reads.

## What's New in v1.8.7

- Serial connections default to QSerialPort in a dedicated thread. The main window and serial bridge share the connection interface. Set `COMMTOOL_SERIAL_BACKEND=pyserial` before startup to compare backends.
- The 20ms silence framer uses read timestamps. Parity, framing, break and unsupported optional modem-line operations allow the data connection to continue.
- Mark/Space parity on macOS and 1.5 stop bits on POSIX are rejected explicitly. Driver-rejected live settings produce a notice and restore the controls after successful rollback. Failed rollback closes the connection and cleans up the thread.
- Sending returns the byte count accepted into Qt's output queue, with a 4MiB backlog limit. Write failure clears the output and closes the connection.
- Update checks add certifi roots to the system default trust configuration, fixing certificate verification failures in some packaged environments.
- **Live log folder** — the save dialog opens in the last successfully used directory for the current profile and suggests a new timestamped filename.

## What's New in v1.8.6

- Serial reception waits for the first byte, includes the suffix already available in the driver buffer, and timestamps the completed chunk in the reader thread.
- Packet-split display and auto-reply silence framing use reader timestamps even when GUI delivery is delayed. A 20ms silence interval suits normal use.
- Activity is registered before reading the suffix to prevent early frame completion. Already-read bytes survive suffix errors, and disconnect cancels blocking reads.
- Auto-reply silence buffers are limited to 1MiB per session. An oversized frame is discarded with a notice, and matching resumes after silence. Packet Split controls display. Configure the auto-reply gap separately, with gap=0 matching each received chunk immediately.

## What's New in v1.8.5

- **Dropdown selection contrast** — selected entries now use the theme's highlight background with white text, fixing invisible text in the Mist theme's flow-control dropdown.
- **Theme-matched switches** — enabled switches use the same accent color as primary buttons; Mist uses charcoal tracks and white knobs, with light-grey tracks when off. Main-window and dialog switches follow theme changes.
- Mouse and keyboard selection remain available. Windows Setup, macOS Apple Silicon DMG and Linux x86_64 installers use the same version source.

For earlier versions, see [GitHub Releases](https://github.com/heropml/SerialTool/releases).

---

## Features

### Connection

The top-left **Connection** card configures the connection. The first row is a **Type** dropdown with **8** options on Windows, or **7** where BLE is unavailable (**Serial** is the default on a fresh install):

- **Serial**
- **RTT** — SEGGER J-Link Real-Time Transfer
- **UDP**
- **UDP Multicast**
- **TCP Server**
- **TCP Client**
- **Virtual** — no hardware; optional loopback; also the injection target for `.ctrec` replay
- **BLE** — Windows BLE central UART-style Notify/Write (classic SPP still uses Serial)

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
- **RTT (SEGGER J-Link)**
  - Pick a **Device**, **Probe** (Auto or serial number), **Interface** (SWD/JTAG), **Speed** in kHz, and **Channel**. Auto keeps the previous successful probe when possible; an explicit serial number is never silently replaced.
  - Open one RTT tab per probe and select a different serial number in each tab. Channel numbers belong to each target, so both tabs can use channel 0 if the firmware listens there. Automatic reconnection retries the same probe once its serial number is known. A channel without a down buffer can still receive data.
  - Use **…** beside Device to search and sort the complete J-Link device catalog. The sidebar list intentionally contains only common shortcuts and accepts free text.
  - **RTT address** accepts Auto, an exact address, or `start+size` / `start..end` to search an aligned RAM range. **Reset on open** is optional.
  - Requires the SEGGER J-Link driver. After J-Link starts RTT, a missing firmware control block is reported as a waiting state rather than a disconnect.
- **BLE (Windows)**
  - **Scan** opens a window with name / address / advertised **UUID** / RSSI (with bars) / **TX** / **connectable** / **observed interval (estimate)** / **manufacturer** (deduped by address). The interval column is this PC’s smoothed time between scan callbacks (Windows / Bleak batching, scan responses, and missed packets all affect it) — not the peripheral’s real Advertising Interval. **Filter** is on by default with selectable rules (hide empty unnamed packets; optionally named only / connectable / has UUID / has manufacturer data / hide stale / used before); turn it off to list every device. Turn on **RSSI filter** and drag the −100 to −30 dBm slider to hide weaker devices. Select a row for the advertisement pane (type, Flags, appearance name, manufacturer name, advertised service count, last connected time, service data, copyable RAW). Rows with no recent advertisements gray out. Search by name, address, UUID, or manufacturer. Double-click or **Use this device** to fill the sidebar
  - Then pick a **preset** (FFF0 / FFE0 / Nordic UART / Microchip UART / Custom) and edit Service / **Write (PC→device)** / **Notify (device→PC)** UUIDs; **Swap** if the direction is reversed. **Write mode** Auto follows the characteristic (Write vs Write Without Response)
  - **Connect**; while connecting the status shows Connecting… and the button is Disconnect (cancel). The status bar shows name + address + **MTU**
  - After connect, the existing TX/RX pipeline applies (text/HEX, log, `.ctrec`, auto-reply, sequences, scripts, stream framing). **No PCAP** (not a NIC capture). macOS / Linux show an unsupported toast
  - Two sessions cannot open the same device; auto-reconnect uses the saved address + UUIDs (no rescan) and stops after 10 attempts (same budget as serial)

**Action button** — its text depends on the protocol and state:

| Type | Button |
|----------|--------|
| Serial | Open Serial / Close Serial |
| RTT | Connect / Disconnect |
| UDP | Open / Close |
| UDP Multicast | Open / Close |
| TCP Server | Listen / Stop |
| TCP Client | Connect / Disconnect |
| Virtual | Start Virtual / Stop Virtual |
| BLE | Connect / Disconnect |

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

**Frame Parse** (Functions → Frame Parse) — by default each received chunk is one frame. For serial/TCP sticky or split packets, enable **Protocol frames** (header + length field; can copy from auto-reply). Plot HEX, dashboard HEX, and structured record share that frame source. UDP stays one datagram = one frame. The data view and `.ctrec` still record raw chunks. A status line shows parse counts and the last failure reason.

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

- **Ctrl+Enter** — sends the current box (Enter still inserts a newline). Terminal mode is unchanged (Enter is passed through).
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

A second dropdown in the top-left (right next to the language picker) switches the overall color scheme. **10 themes** are available, each with a distinctive look that affects the whole window — sidebar cards, buttons, data area, status bar, even the close-confirm dialog:

| Theme | Mode | Vibe |
|-------|------|------|
| Mist | light | Cool grey, white cards and charcoal buttons |
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
  - **A newer version is available** → the dialog shows the new version number, the **release notes**, and a **Download and Update** button. Click it to download (a **progress percentage** is shown).
    - **Windows**: the **install wizard** opens — finish with **Next / Install** (**not** a silent install).
    - **macOS**: the `.dmg` opens; drag the app into Applications and relaunch (unsigned: see `xattr` under Install).
    - **Linux**: the `.run` installer starts after the app quits and overwrites `~/.local/opt/CommTool`.
  - **Already up to date** → the dialog simply tells you you're on the latest version.
- **Update sources** — the version manifest tries **Gitee first**, then **GitHub**; each source has an **8-second timeout**. Windows Setup is on Gitee; macOS `.dmg` and Linux `.run` are on GitHub (Gitee also hosts Setup and DMG; Linux packages are published on GitHub only).
- **Integrity check** — the downloaded file is verified with SHA-256 (and size when present) before the installer runs. A manifest without a digest only offers the manual download page.
- **Cancel anytime** — closing the dialog while a download is in progress cancels the download automatically.

### Auto-saved Configuration

On exit, settings are written to `config/settings.ini` in the install directory; on next launch **everything is restored**:

- Window position and size (including maximised state)
- Splitter position
- Current language
- All switches / input fields / dropdown selections
- Send box content, font size, max line count

If the install directory is read-only (e.g. Program Files without admin), the config falls back to `%APPDATA%\CommTool\config\settings.ini` automatically. A leftover root-level `settings.ini` from older builds is moved into `config\` on startup.

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
- current **version** (`v1.8.9`) — turns into a clickable “● Update vX” badge when a newer version is available

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

**Q: RTT cannot find a J-Link or its control block?**
A: Install the official SEGGER J-Link driver, then confirm the selected probe, interface, target device, and speed. “Waiting for control block” means the probe is connected but firmware has not yet initialized RTT; verify the firmware’s RTT setup or use the address/range supplied by the target.

**Q: Timed send not working?**
A: The minimum period is 10 ms and you must stay connected. It pauses automatically on disconnect.

**Q: Chinese characters show as garbled text?**
A: Auto mode tries UTF-8 first and falls back to GBK. If that's still wrong, the device may use another encoding (e.g. Big5) — pick it explicitly from the **Encoding** dropdown, or switch **View mode** to HEX / HEX dump to inspect the raw bytes.

**Q: HEX send reports "length must be even"?**
A: HEX is parsed byte-by-byte. `AA B` has 3 hex chars which can't pair up — write it as `AA 0B` or `AAB0`.

**Q: Does the log file slow things down when it gets large?**
A: Writes are append-only — even hundreds of MB stay smooth. **Max Lines** only limits the on-screen display, not what's written to disk.

---

## Install (Windows / macOS / Linux)

Download the v1.8.9 installers from [GitHub Releases](https://github.com/heropml/SerialTool/releases/tag/comm-v1.8.9) or check available mirrored assets on [Gitee](https://gitee.com/heropml/SerialTool/releases/tag/comm-v1.8.9).

### Windows

- Windows 10 / 11 (64-bit)
- Recommended: `CommTool_Setup_v1.8.9.exe` — wizard install, optional desktop shortcut; per-user install does not need admin

### macOS

- **Apple Silicon** (arm64) only: download `CommTool_v1.8.9.dmg` from `comm-v1.8.9`
- Open the DMG and drag CommTool into **Applications**
- If macOS says the app is damaged (not notarized), run once:

```bash
xattr -dr com.apple.quarantine /Applications/CommTool.app
```

### Linux

- **x86_64**, glibc ≥ 2.27 (Ubuntu 18.04+ / most Kylin desktops). xcb / X11 libs are bundled; you usually do not need extra `apt` packages
- File: `CommTool_Setup_v1.8.9_linux_x86_64.run`

```bash
chmod +x CommTool_Setup_v<version>_linux_x86_64.run
./CommTool_Setup_v<version>_linux_x86_64.run
```

- Installs to `~/.local/opt/CommTool` (**no sudo**), with an application-menu entry and a desktop icon
- Launch from the menu / desktop icon, or `~/.local/opt/CommTool/CommTool` (`CommTool` if `~/.local/bin` is on `PATH`)
- Uninstall: `~/.local/opt/CommTool/uninstall.sh`
- Empty serial-port list: add your user to `dialout` and log in again: `sudo usermod -aG dialout $USER`

---

## System Requirements

- Windows 10 / 11 (64-bit); macOS Apple Silicon; Linux x86_64 with glibc ≥ 2.27
- About 100–200 MB disk
- RTT additionally requires the official SEGGER J-Link driver; the application bundles the Python wrapper.

---

Found a bug or have a feature request? Get in touch with the developer.
