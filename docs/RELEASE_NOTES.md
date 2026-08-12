**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.5.3 正式版**：主界面防误触滚轮、数据区选区转文本/HEX，以及阶段 A/B 工程打磨与 CI 加固。

## v1.5.3 正式版

### 主界面防误触
- 主窗口内的 `QComboBox`（含其内部编辑框）在弹出列表未打开时**忽略鼠标滚轮**，避免划过参数区时误改波特率 / 类型等
- 应用级 `eventFilter` 常驻安装；仅拦截「主窗口祖先 + 未弹列表」路径，不影响其它对话框与已展开的下拉
- 会话重命名 / 连接预设命名等单行输入框改用主题按钮（`MsPrimaryBtn` / `MsGhostBtn`），不再落回 Windows 原生 `QInputDialog` 样式

### 数据区选区转换
- 接收区右键新增 **转为文本** / **转为 HEX**：按当前选区做 HEX↔文本互转
- 结果在信息对话框中展示，并**复制到剪贴板**；成功/失败/空选均有 toast
- 单次转换上限 **64 KiB**（编码前字符数与编码后字节数），防止超大选区卡 UI
- 转 HEX 时按文本编码；转文本时对选区做 HEX 清洗解析（空白剥离为有意行为）

### 工程与 CI（阶段 A/B）
- 文档真源与依赖拆分、split/i18n 契约、session_host 契约单测、静默 `except` 预算门禁
- macOS CI 烟雾（offscreen 子集）、`ruff` 门禁、覆盖率收集（先不设硬门槛）
- README 多会话边界说明；路由契约 / ruff 注释与 macOS smoke 依赖精简等收口

### 产品边界
- P2（CLI / REST / 插件 dissector）继续暂缓
- 触发联动发送仍不做；完整 VT100 / BLE·HID·CAN 等不在范围
- 多条循环发送已改为 per-session（切标签不停，与定时发送对齐）；网关 UI 的 timeout / unit_map 已在桥接对话框开放
- 工程向：全局 QSS / 切语言表抽出为 `app_style` / `i18n_ui`（CommTool 薄包装）
- macOS DMG 仍由协作者在 Mac 上跑 `release_macos.sh` 补到同一 Release；门禁通过前检查更新不提供 Mac 下载

### 测试
- 基线：**1465 passed / 11 skipped / 295 subtests**（CI 在既有 1454 上叠加本版相关用例）

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.5.3.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.5.3.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.5.3.dmg` | arm64；拖入「应用程序」。资产经门禁校验后才写入更新清单；未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
