**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.7.3 正式版**：运行时配置迁入 `config/`，触发 Webhook/外部程序改走事件总线；对话框与绘图误报 toast 收窄。

## v1.7.3 正式版

### 配置目录
- 设置落到 `<可写基目录>/config/settings.ini`（多窗口 `settings-2.ini` …）；锁文件 `.mwlock` 跟着走
- 打包版优先 exe 同级 `config\`（绿色版可连目录拷走）；写不进则 `%APPDATA%\CommTool\config\`
- macOS 固定 `~/Library/Application Support/CommTool/config/`，不写进 `.app`
- 首次启动把旧版同级 `settings.ini` / `settings-*.ini` 迁入 `config\`：复制成功才删源文件；目标已有则保留旧文件，下次再试
- 开发模式写 `src/config/`（已 gitignore）
- 安装脚本建 `{app}\config`；升级时新旧路径都没有 `settings.ini` 才按安装语言 seed

### 事件总线
- 触发器命中只发 `trigger.hit`；响铃 / 托盘 / 打标仍在界面
- Webhook POST 与外部程序由 `TriggerActionRunner` 消费：并发上限 8、子进程回收、私有地址拦截不变
- 导入含 `run_cmd` / `webhook_url` 仍走原信任确认

### 对话框 / 绘图
- 波形图恢复已存的非法正则 / 帧头 / 字段不再弹错误；当场改错仍提示
- 序列 CSV 加载与报告导出补上 `csv.Error`；xlsx 非法字符走 `ValueError`
- 保存失败不再把程序内部异常包装成文件错误

### 产品边界
- 本版不做会话树、拖拽分屏、标签拖出成窗；P2 继续暂缓
- **本轮发 Windows + Linux x86_64**；macOS DMG 补同一 tag `comm-v1.7.3`
- Linux 不提供 ARM 官方包

### 测试
- 全量测试：1668 passed，11 skipped，295 subtests passed

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.7.3.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.7.3.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.7.3.dmg` | arm64；拖入「应用程序」。本轮稍后补同一 Release |
| Linux（x86_64） | `CommTool_Setup_v1.7.3_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
