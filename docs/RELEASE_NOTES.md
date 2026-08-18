**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.7.2 正式版**：源码按领域分包，收窄连接 / 发送 / 日志异常；RX 失败提示改用界面标题。

## v1.7.2 正式版

### 源码布局
- 约百个模块迁到 `transport` / `protocol` / `modbus` / `sessions` / `automation` / `record` / `project` / `ui`
- 入口仍留在 `src` 根：`main.py`、`main_window.py`、`version.py`、`updater.py`、`app_icon.py`、`icon_data.py`
- 包名用 `sessions`，避免挡住模块 `session`；import 形如 `from transport.serial_io import …`
- 导出默认文件名仍是 `snippets.json` / `connection_presets.json`，未带包前缀

### 连接 / 发送 / 日志
- BLE 扫描 / 打开 / 连接 / GATT 写改为明确 I/O 异常 + debug traceback；关连接与 `stop_notify` 仍宽捕，避免拖死 BLE 线程
- 发送失败走 I/O 类异常，日志路径失败同样 toast 并留 traceback
- 编程错误不再伪装成「发送失败」；槽函数未捕获异常打 stderr，不拖死窗口
- 静默 `except: pass` 预算仍冻 9；宽泛 `except Exception` 总数不是 KPI

### 用户可见
- RX 侧失败 toast 用界面标题（触发告警 / 自动应答等），不再露出内部通道名
- 序列等 Modbus 回包时侧通道喂 Modbus 主机，不再挂在序列步骤通道上

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗；P2 继续暂缓
- **本轮发 Windows + Linux x86_64**；macOS DMG 补同一 tag `comm-v1.7.2` 后再写 `url_mac`
- Linux 不提供 ARM 官方包

### 测试
- 全量测试：1654 passed，11 skipped，295 subtests passed

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.7.2.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.7.2.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.7.2.dmg` | arm64；拖入「应用程序」。本轮稍后补同一 Release |
| Linux（x86_64） | `CommTool_Setup_v1.7.2_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
