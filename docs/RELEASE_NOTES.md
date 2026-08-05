串口 + 网络一体调试工具。本版收尾 P1 体验缺口：**多从机行表 UI、状态栏 / 会话比较跳转会话时间、数据区书签**，并修 ANSI 清屏残留书签与重复从机地址静默丢弃。

## 1. 多从机行表 UI

自动应答 · Modbus 从机对话框用「地址 / Server ID / Extra JSON」行表替代纯 JSON 文本框：可添加、删除行；Extra 填 maps / dynamics / exception 等；重复地址提交时 toast 拒绝。手改工程 JSON 仍由运行时「同地址只留第一个」兜底。

## 2. 跳转到会话时间

- **状态栏**：点击 RX / TX 统计，跳到最近一次统计样本的 wall 时间（接通 `jump_to_session_time`）
- **会话比较**：双击差异行，经 `.ctrec` 头里的 `wall_t0` 把相对时间映射为 wall 时间后跳转；旧录制无锚点则提示重新录制
- 新录制的 `.ctrec` 会写入 `wall_t0`

## 3. 数据区书签

- `Ctrl+F2`：在当前行加 / 清书签（橙色整行高亮）
- `F2` / `Shift+F2`：下一 / 上一书签（环绕）
- 清空数据区或 ANSI 全清屏（`ESC[2J`）时一并清除书签

## 4. 其它

- P1 路线图项（P1-1–P1-5）与收尾缺口均已完成；后续能力见 P2（CLI / API / 插件 / PCAP）
- 文档与 TODO 过时「待补」表述已整理

## 5. 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.3.9.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.3.9.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.3.9.dmg` | arm64；拖入「应用程序」。未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
