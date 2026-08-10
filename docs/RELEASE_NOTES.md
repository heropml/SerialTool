串口 + 网络一体调试工具。**v1.5.1 正式版**：在多会话基线上补齐搜索惰性分页与全局导航、可逆一键 I/O Graph、示例工程包，以及 Mac 发版门禁与显示选项矩阵回归。

## v1.5.1 正式版

### 搜索：惰性分页与全局导航
- `find_spans(..., limit=, start=)` 扫描期即止损，避免大日志一次扫完全文卡 UI
- ▲/▼ 跨页导航；`find_last_page()` 一趟定位末页；到顶/到底全局环绕
- 零宽正则匹配后安全前进，避免死循环；有更多未展示命中时计数带 `+`

### 一键 I/O Graph（可逆临时模式）
- 状态栏右键或工作区「I/O Graph」打开时间轴 + `rx_Bps` / `tx_Bps` / `rx_pps` / `tx_pps` 预设
- 进入时按通道索引快照既有曲线，关闭 / 改轴 / 清空解析器时恢复，不冲掉用户序列
- 临时模式隔离 RX `feed` 与非速率命名样本，打开时不清空已有数据

### 示例工程与安装包资源
- `examples/` 提供 Modbus RTU、AT 调制解调器、双会话预设 `.ctproj`（稳定 `preset_id`）
- Windows 安装目录带 `examples`；macOS DMG 提供可见 `Examples` 文件夹
- 双会话示例：打开后新建会话并应用 Session B；虚拟连接默认回环便于无硬件试用

### Mac 发版门禁与更新源
- `latest.json` 的 `url_mac` 仅在 DMG 经 GitHub 资产校验后写入，避免预填死链
- 更新器 Mac 候选优先 GitHub；`scripts/check_mac_asset.py` + `release_macos.sh` 门禁
- 关于/更新对话框对未就绪的 Mac 资产给出明确说明

### macOS 安装包热修复
- 修复应用级 Qt 事件过滤器在接收视图尚未创建或会话销毁时访问 `None.viewport()`，避免 PyQt 回调异常升级为 `qFatal` / `SIGABRT`
- 将 Windows 专用的 `Segoe UI Symbol` 映射为 macOS 的 `Apple Symbols`，消除启动时的字体回退告警
- 11 项 macOS 针对性回归、Apple Silicon `.app` 启动冒烟、深度签名及 DMG 映像校验通过

### 多会话显示选项与协议加固
- 活动标签显示开关以实时 UI 为准；后台标签仍用各自 `display_opts`（时间戳 / HEX / 转储 / ANSI / 分包 / 编码 / 冻结 / 日志）
- 冻结视图优先读 `display_context["freeze_view"]`
- Modbus 从机 CRC 重同步性能；主机 TCP transaction id 校验；虚拟注入过长日志截断
- 切会话时重置搜索状态，避免旧高亮串台

### 产品边界
- P2（CLI / REST / 插件 dissector）继续暂缓
- 重建 PCAP（仅 TCP Client / 单对端 UDP）排入后续 v1.6，不在本版
- macOS DMG 仍由协作者在 Mac 上跑 `release_macos.sh` 补到同一 Release；门禁通过前检查更新不提供 Mac 下载

### 测试
- 基线：**1359 passed / 11 skipped / 295 subtests**

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.5.1.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.5.1.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.5.1.dmg` | arm64；拖入「应用程序」。资产经门禁校验后才写入更新清单；未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
