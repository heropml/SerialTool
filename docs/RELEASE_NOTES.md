**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.5.2 正式版**：绘图与仪表盘可视化扩展、Excel/xlsx 导出、PCAP/pcapng 增强、回放驱动真实 TX，以及一轮 High/Medium/Low 稳定性打磨。

## v1.5.2 正式版

### 绘图与仪表盘
- 波形图：视图模式波形 / XY / 直方图；双 Y 轴与光标统计（min/max/mean）；`plot_stats` 有限值过滤与安全柱宽
- 工程持久化 `plot_view` / `plot_dual_y`
- 仪表盘控件：Number / Gauge / LED / Progress（`dash_widgets` + `dash_widget` 工程字段）
- 寄存器来源通道的告警 level 不被文本 `feed` 清掉，避免阈值闪烁

### 导出与抓包互通
- 序列报告 / 结构化记录支持 **Excel/xlsx**（`openpyxl`）；公式样单元格按文本落盘
- PCAP：**TCP Client/Server（单客户端）、UDP、UDP 组播** → 经典 `.pcap` + `.pcapng`；通配 `0.0.0.0` 解析为具体主机 IPv4；串口等仍用 `.ctrec`

### 回放驱动真实 TX
- `Player(mode=drive_tx)` + UI 危险确认（非默认；默认仍 Virtual 注入 RX）
- 连续失败暂停、同 tick 立即停发；部分写视为失败；末帧 abort+finished 优先清理占用
- 与 Modbus / 自动应答互斥；循环/最快需二次确认

### 多会话与示例
- 切标签时**自动停止多条循环发送**（toast）；脚本/Modbus 等仍硬拦切标签
- 示例工程扩展：NMEA / 定长帧头 / 传感器 CSV / TCP Client / 关键字高亮 / 仪表盘等
- 工作区与会话条补充多会话边界说明（`workspace_terminal_tip` / `session_list_tip`）

### 稳定性与防御（审计收尾）
- High/Medium：结构化回放过滤同步、串口重配竞态、`stop` 短等待、陈旧 RX 按连接身份丢弃、侧信道 warning+节流 toast、TCP Server 广播快照、搜索防抖、CSV 打开失败不静默停录、报告步骤号、keyword mode 白名单、MultiSend 安全 int、`.ctrec` 头扫描、`addr_base` 不静默钳位等
- Low：日志 toast `{path}`、HEX 搜索与触发器清洗对齐、`sequence_split` 进 CFG、`open_conn` 替换守卫、TCP/UDP 失败路径 `deleteLater`、`pytest` 写入开发依赖
- `compile_regex` 对所有格量词仍保守拒绝（有意保留）

### 产品边界
- P2（CLI / REST / 插件 dissector）继续暂缓
- 触发联动发送仍不做；完整 VT100 / BLE·HID·CAN 等不在范围
- macOS DMG 仍由协作者在 Mac 上跑 `release_macos.sh` 补到同一 Release；门禁通过前检查更新不提供 Mac 下载

### 测试
- 基线：**1433 passed / 11 skipped / 295 subtests**

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.5.2.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.5.2.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.5.2.dmg` | arm64；拖入「应用程序」。资产经门禁校验后才写入更新清单；未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
