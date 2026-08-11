# CommTool example projects

| File | Use |
|---|---|
| `modbus_rtu_demo.ctproj` | Modbus RTU HEX view, CRC, sample registers |
| `at_modem_demo.ctproj` | AT line mode + snippets / smoke sequence |
| `dual_session_demo.ctproj` | Two Virtual presets for multi-tab practice |
| `nmea_gps_demo.ctproj` | NMEA GPS @ 9600 with $GPGGA sample snippets |
| `fixed_header_demo.ctproj` | AA 55 fixed-header HEX on Virtual loopback |
| `sensor_csv_demo.ctproj` | Delimiter CSV sensor lines + multi-send / plot |
| `tcp_client_debug.ctproj` | Raw TCP Client 127.0.0.1:9000 + presets |
| `keyword_highlight_demo.ctproj` | AT keywords: plain / regex / HEX highlight |
| `dash_gauge_demo.ctproj` | Dashboard gauge + thresholds on Virtual |

Open via **Project → Open**. Dual-session tabs are runtime-only: after opening the project, use **New Session** and apply the **Session B** connection preset.
Regenerate with `python scripts/build_example_projects.py`.
