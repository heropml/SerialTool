**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.5.4 正式版**：多条循环发送 per-session、桥接网关 timeout/unit_map、全局 QSS/切语言薄拆，以及 updater 截断响应修复与 except 抽样收窄。

## v1.5.4 正式版

### 多条循环发送 per-session
- 循环定时器挂到会话：切标签后后台会话继续轮发，与定时发送语义对齐
- 分组仍为整窗共享；编辑或切换分组时同步刷新所有正在循环的会话；新序列为空则停止对应循环
- 进终端模式 / 关机仍停止全部会话的循环

### 桥接网关 UI
- 桥接对话框暴露从机超时与 Unit ID 映射（`timeout` / `unit_map`），默认仍为 1s 与原样透传
- 设置持久化到 `bridge/gw_*`；非法映射有 toast；三语文案齐全

### 工程打磨
- 抽出 `app_style` / `i18n_ui`：`apply_style` 与 `_apply_language` 薄包装，便于改主题/文案
- B6：`updater` / `serial_io` / `net_io` 与 `main_window` 连接·发送·日志·设置、`session_host` 会话路径宽泛 `except` 抽样收窄
- 修复：HTTP 响应截断（`IncompleteRead`）不再挂死自动更新检查或泄漏半成品安装包；补 Windows updater 单测

### 产品边界
- P2（CLI / REST / 插件 dissector）继续暂缓
- 触发联动发送仍不做；完整 VT100 / BLE·HID·CAN 等不在范围
- macOS DMG 仍由协作者在 Mac 上跑 `release_macos.sh` 补到同一 Release；门禁通过前检查更新不提供 Mac 下载

### 测试
- 基线：既有套件 + updater 截断 / 网关边界 / 多会话循环刷新等新增用例（以 CI 为准）

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.5.4.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.5.4.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.5.4.dmg` | arm64；拖入「应用程序」。资产经门禁校验后才写入更新清单；未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
