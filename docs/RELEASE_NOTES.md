**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.5.7 正式版**：TCP Server 多客户端可导出 PCAP；关键字增量高亮与搜索节流；Ctrl+Enter 发送；实时日志及时落盘。

## v1.5.7 正式版

### TCP Server 多客户端 PCAP
- 多于一个对端（含定向回复与 `__all__` 广播）不再拒绝导出 `.pcap` / `.pcapng`
- 每个客户端独立 4 元组与 TCP 序号；导出前多于一个对端会列出确认
- 广播按该次发送时的对端展开；后来才连上的客户端不会被补进更早的广播帧
- 旧的单对端 `.ctrec` 仍可导出

### 关键字高亮与搜索
- 增量着色按文末累积脏区间扫描，长会话 + 头部截断不再漏高亮
- 终端模式纳入规则指纹；开关与 `ESC[2J` 全清会清掉残留选区
- 搜索栏 150ms 防抖；查询未变时跳过全文档扫描，文档增长则重建当前页

### 发送与日志
- 普通发送框 **Ctrl+Enter** 发送（Enter 仍换行）；先提交 IME 组合；终端模式不变
- 实时日志每次写入后 `flush()`，约 1 秒合并 `fsync`；磁盘满仍会关掉日志；空闲同步异常不再冒出定时器

### 工程加固
- 文案里的字面花括号不再误触发 `.format`
- TCP 普通发送加写缓冲上限，避免慢客户端无限积压
- 会话上限统一；串口 / 网络清理共用 `safe_step`；UDP 基类收口

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗
- P2（CLI / REST / 插件 dissector）继续暂缓
- macOS DMG 仍由协作者在 Mac 上跑 `release_macos.sh` 补到同一 Release；门禁通过前检查更新不提供 Mac 下载
- **Linux x86_64**：`CommTool_Setup_v1.5.7_linux_x86_64.run` 免 sudo 安装到 `~/.local/opt/CommTool`；xcb/X11 已打进包。在线更新走 `latest.json` 的 `url_linux`（GitHub）

### 测试
- 全量测试：按文件隔离 pytest 全部通过（1574 collected，11 skipped）

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.5.7.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.5.7.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.5.7.dmg` | arm64；拖入「应用程序」。资产经门禁校验后才写入更新清单；未公证，首次打开见下方说明 |
| Linux（x86_64） | `CommTool_Setup_v1.5.7_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
