**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.7.0 正式版**：Windows 上新增 BLE 主机 UART（Notify + Write），扫描改为独立窗口；连上后走现有收发管线。macOS / Linux 仍提示不支持 BLE。

## v1.7.0 正式版

### Windows BLE 主机 UART
- 类型下拉新增 **BLE**（英文标签不变）；Windows 上作为 BLE Central，按 UART 风格 Notify + Write 收发
- 连上后走现有 TX/RX 管线（文本 / HEX、日志、`.ctrec`、自动应答、序列、脚本、组帧）
- 模板：FFF0、FFE0、Nordic UART、Microchip UART、Custom；可对调写入与通知 UUID
- **写入方式** 默认自动（按特征属性选 Write 或 Write Without Response）
- 同一地址不能被两个会话同时占用（含连接中）；地址格式 `AA-BB` / `AA:BB` 视为同一设备
- 无 GATT 浏览器、无经典 SPP（仍走 Serial COM）、无 BLE PCAP
- macOS / Linux 可选该类型，操作为不支持提示

### 独立扫描窗口
- 侧栏不再内嵌设备表；点「扫描」弹出独立窗口（搜索、按列排序、双击或「使用此设备」填回名称 / 地址）
- 结果按地址去重并刷新 RSSI；过滤默认开（无名空包、可连接、UUID、厂商、过期、用过）；可选 RSSI 滑条
- **观测间隔（估算）** 是本机两次扫描回调的平滑时间差，不是外设真实 Advertising Interval
- 「上次连接」只在真正连上后写入，不只选中设备
- 切主题会重绘已有行；切语言会刷新行 tooltip；窗口隐藏时停过期计时器

### 写入、重连与扫描互斥
- 自动重连按已保存的地址 + UUID，不再扫描，最多 **10** 次（与串口相同预算）
- 扫描停止后再连接；等待扫描空闲超时后继续，避免 Windows 无线电被扫描占住而一直「连接中」
- 分包写入异常会失败并归还队列；关闭连接不再误复位排空标志，避免重连后计数交叉污染
- 过期的 `state_changed(True)` 不再把已关闭会话标成已连接

### 打包与示例
- `requirements` 含 `bleak>=0.22`；PyInstaller 收集 bleak，仍排除 QtBluetooth
- 示例工程同步 `ble_write_mode` 与 `app_version`
- Linux 系统库打包脚本不再写死本机路径

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗
- P2（CLI / REST / 插件 dissector）继续暂缓
- **本轮先发 Windows**；macOS `.dmg` 与 Linux `.run` 仍补同一 tag `comm-v1.7.0`（校验后再写入 `url_mac` / `url_linux`）
- macOS 未公证，首次打开见下方 `xattr` 说明；Linux 不提供 ARM 官方包；BLE 仅 Windows

### 测试
- 全量测试：1644 passed，11 skipped，295 subtests passed

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.7.0.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.7.0.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.7.0.dmg` | arm64；拖入「应用程序」。本轮随后补同一 Release |
| Linux（x86_64） | `CommTool_Setup_v1.7.0_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
