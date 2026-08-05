串口 + 网络一体调试工具。本版收尾 1.3.7 之后的体验与配置缺口：**Tooltip 自动换行、Modbus 异常注入 / 动态寄存器 / FC08 配置界面、波形图双击跳转会话时间**，并修若干回归问题。

## 1. Tooltip 自动换行

长提示以前在 Windows 上常被 Qt 画成超宽单行。新增 `ui_tips.set_tooltip`：把纯文本转成带换行的 HTML，全项目对话框与语言切换刷新路径统一接入。系统托盘图标仍用纯文本（Windows 托盘会把 HTML 原样显示）。

## 2. Modbus 高级配置界面

自动应答的 Modbus 从机对话框补齐原先只能写工程 JSON 的项：

- **异常注入**：模式（always / once / n）、次数、功能码过滤、起始地址过滤，以及原有的启用开关与异常码
- **动态寄存器**：表格配置 space / addr / mode / step / min / max / period
- **从机 ID**（`server_id`，供 FC17）
- 多从机列表仍用 JSON 文本框

主机轮询页：功能码 08 的数量列支持 `子功能:数据`（如 `0:1`）；切换功能码时自动改写单元格并刷新 tooltip。切到读类功能码时数量至少钳制为 1；动态寄存器 `max=0` 可正确保存。

## 3. 波形图跳转会话时间

双击波形图数据点，按采样 wall 时间跳到结构化记录中对应时刻（接通已有的 `jump_to_session_time`）。速率通道（`rx_Bps` / `tx_Bps` / `rx_pps` / `tx_pps`）不参与跳转。

## 4. 其它修复

- 自动应答对话框合并重复的 `closeEvent`，关闭时会 `_commit` 未落盘改动并 `settings.sync()`（列宽等拆分条尺寸能刷盘）
- 帮助文案不再写「异常注入 / 动态寄存器目前没有界面」

## 5. 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.3.8.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.3.8.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.3.8.dmg` | arm64；拖入「应用程序」。未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
