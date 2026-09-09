**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.8.0 正式版**：新增 SEGGER J-Link RTT 连接，补齐探针选择、器件目录与稳定性收口。

## v1.8.0 正式版

### SEGGER J-Link RTT

- 新增 **RTT** 连接类型：通过 SEGGER J-Link 读写目标 MCU 的 RTT 缓冲，沿用既有收发、日志、录制、自动化与分析管线。
- 支持器件、SWD / JTAG、速度、RTT 通道、精确控制块地址，以及“起点 + 搜索范围”两种 RAM 搜索写法；连接时复位为可选项。
- 侧栏保留常用器件和自由输入；“…” 选择窗提供完整 J-Link 器件目录、筛选、排序和回填，避免大列表拖慢主界面。
- 多把 J-Link 时可指定探针序列号；自动模式优先重连上次成功的探针，目标探针不可用才回退默认探针。显式指定序列号绝不切换到其他探针。

### 连接反馈与稳定性

- J-Link 驱动访问按进程串行化；目录加载不会和活动 RTT 会话并发进入 DLL。
- RTT 已启动但固件尚未建立控制块时显示等待提示，不误判为连接失败；运行中掉线和下行写失败会明确反馈。
- 退出测试改为正常释放 Qt / BLE 资源，不依赖 `os._exit()` 强退。

### 依赖与文档

- 新增运行时依赖 `pylink-square`；使用 RTT 仍须另行安装 SEGGER J-Link 驱动包。
- README、三语用户说明、架构基线与示例工程配置同步 RTT 字段和使用边界。

### 发布范围

- **Windows** 安装版、单文件版与 **macOS（Apple Silicon）** DMG 已发布，tag 为 `comm-v1.8.0`。
- Linux x86_64 安装包将在构建完成后追加到同一 tag；在资产出现前，应用只提供该平台的手动 Release 页面。

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.8.0.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.8.0.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon） | `CommTool_v1.8.0.dmg` | arm64 `.dmg`，拖入“应用程序”安装 |
| Linux（x86_64） | 待追加至 `comm-v1.8.0` | `.run`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。RTT 功能需额外安装 SEGGER J-Link 驱动。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
