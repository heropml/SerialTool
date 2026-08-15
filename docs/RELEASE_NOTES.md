**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.6.0 正式版**：分析层可按完整协议帧解析粘包/拆包；默认仍按收包兼容旧工程。日志轮转失败不再停写；Linux 在线更新等主进程退出后再覆盖。

## v1.6.0 正式版

### 协议流组帧与解析诊断
- 默认每个收包仍是一帧（旧工程、未勾选时行为不变）
- 勾选 **协议帧模式** 后，按帧头 + 长度字段组成完整帧，再喂帧解析 / 波形 HEX / 仪表盘 HEX / 结构化记录
- 配置独立于自动应答（可选用自动应答的组帧参数）；UDP 默认一数据报一帧，可选择也按流组帧
- TCP Server 按客户端隔离半帧缓存；客户端断开即丢弃该来源，避免短连接泄漏与端口复用拼成伪帧
- 组帧对话框底部显示解析计数；「没有字段」时可看最近失败原因
- 数据区显示、协议高亮、`.ctrec` 录制仍是原始收包，不按组帧结果改写

### 日志与 Linux 更新
- 按日 / 按大小轮转：先打开新段再关旧文件；新段失败则继续写旧段并提示，不再关掉「实时日志」
- Linux 安装器等待当前进程退出后再覆盖安装目录，超时可见失败（不再 `sleep 1`）
- 官方 Linux 仅 **x86_64**；非 x86_64/amd64 主机打包 / 发布脚本直接拒绝，避免生成无法上架的包名

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗
- P2（CLI / REST / 插件 dissector）继续暂缓
- **本轮先发 Windows**；macOS `.dmg` 与 Linux x86_64 `.run` 仍补到同一 tag `comm-v1.6.0`（校验后再写入 `url_mac` / `url_linux`）
- macOS 未公证，首次打开见下方 `xattr` 说明；Linux 不提供 ARM 官方包

### 测试
- 全量测试：1594 passed，11 skipped，295 subtests passed

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.6.0.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.6.0.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.6.0.dmg` | arm64；拖入「应用程序」。本轮随后补同一 Release |
| Linux（x86_64） | `CommTool_Setup_v1.6.0_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；本轮随后补同一 Release |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
