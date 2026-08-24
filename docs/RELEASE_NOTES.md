**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.7.4 正式版**：更新清单校验 SHA-256/大小，Webhook 默认仅公网 HTTPS，补齐诊断包与首屏快速开始。

## v1.7.4 正式版

### 在线更新
- `latest.json` 为每个平台写 SHA-256 与文件大小；三套发版脚本调用 `update_manifest_integrity.py` 自动写入
- 缺摘要或摘要无效时，客户端只打开人工下载页，不会自动运行安装包
- 下载后再核对照摘要与大小；Windows 仍验 MZ、Linux 仍验 shebang

### 触发 Webhook
- 默认只允许公网 HTTPS；解析全部地址后钉死 IP 连接，证书/SNI 仍用原主机名，不跟随跳转
- 局域网 / 明文 HTTP 必须在该条规则上勾选「允许局域网 / HTTP」
- 本机已有、且尚未带权限字段的旧规则会显式补上兼容开关，避免升级后静默停发

### 自动应答
- 冷却把 `0` 当「从未命中」哨兵，不再在进程启动后的前一段冷却窗口里吞掉第一次合法命中
- 冷却仍按会话隔离

### 诊断与工作流
- 滚动错误日志（按配置档分文件）；「帮助 → 导出诊断包」生成脱敏 ZIP，不收录通信载荷
- 空白终端提供快速开始：Virtual 回环、内置示例、最近工程
- 帧构造器可保存个人帧模板；录制回放索引最近 `.ctrec`；工程文件可携带帧模板与操作面板资源

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗；P2 继续暂缓
- **本轮发 Windows / macOS / Linux x86_64**；同一 tag `comm-v1.7.4`
- Linux 不提供 ARM 官方包

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.7.4.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.7.4.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.7.4.dmg` | arm64；拖入「应用程序」 |
| Linux（x86_64） | `CommTool_Setup_v1.7.4_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
