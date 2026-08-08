串口 + 网络一体调试工具。**v1.4.2 正式版**：在 v1.4.1 可维护基线上，收齐 S-2 运行时/显示/设置/连接抽离与 S-3 断线重连 soak；v1.4 主线功能冻结。

## v1.4.2 正式版

### 架构与可维护（S-2 R43–R55）
- **运行时编排（R43–R50）**：重连策略 / Modbus 轮询计划 / 序列编排 / 自动应答门控 / RX 分发 / TX 计划 / Modbus 收流 / AR post-hit 抽出为 Qt-free 模块；`CommTool` 保留薄包装
- **显示与设置 I/O（R51–R55）**：`config_io` 加载门控、`view_format` 块前缀与日志拼装、`connection_presets` 开连字段采集、新模块 `term_vt`（终端流状态 / tooltip 色）；设置分区与 `settings.ini` 命名决策迁出
- **刻意保留**：整段 QSS、`_apply_language` 控件遍历、VT 解析循环、`_settings_file` 路径 I/O（Qt 壳，不再作为刀目标）

### 稳定性（S-3）
- `VirtualConn.simulate_link_drop` 断线重连基线；CI 虚拟掉线 / churn 测试
- 可选门禁：`COMMTOOL_SOAK_DISCONNECT`、`COMMTOOL_SOAK_SERIAL=COMx[,COMy]` 真机 open/close（未设或占用则 skip）、`COMMTOOL_SOAK_NIGHTLY` 加密循环

### 产品边界
- **v1.4 主线（S-1～S-5）收齐**；P2（CLI / REST / 插件 dissector）继续暂缓，功能冻结，优先修 bug 与发版

### 测试
- 基线：**1185 passed / 6 skipped / 291 subtests**

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.4.2.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.4.2.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.4.2.dmg` | arm64；拖入「应用程序」。未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
