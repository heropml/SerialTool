**CommTool** — 开源串口调试助手 / 网络调试工具（UART + TCP/UDP）。**v1.7.1 正式版**：打磨 Windows BLE 扫描窗口（过滤弹层、序号列、已开窗口跟语言），macOS / Linux 类型下拉不再出现 BLE。

## v1.7.1 正式版

### BLE 扫描窗口
- **过滤弹层**改为单卡片：启用开关与规则同组；规则两列对齐，不再流式挤裁
- 再点「过滤 / RSSI 过滤」可关掉弹层（点外部或 × 仍可关）；两个弹层不同时打开
- 关掉总开关后规则变灰，勾选与重启记忆不变
- 结果表最左增加 **序号** 列：按当前可见行从 1 编起，排序 / 过滤 / 搜索后重编；序号列不参与排序
- 空闲时点列头排序，序号在模型重排后再更新，避免带着旧号移动

### 语言与类型
- 已打开的扫描窗口随主界面切语言立即更新（标题、按钮、过滤文案、列头、行 tooltip）
- **macOS / Linux** 类型下拉不再出现 BLE（旧工程里的 BLE 配置对不上选项时保持串口）；底层仍拒绝非 Windows 扫描 / 连接

### 产品边界
- BLE 主机 UART 仍仅 Windows；无 GATT 浏览器、无经典 SPP、无 BLE PCAP
- 本版不做会话树、拖拽分屏、标签拖出成窗；P2 继续暂缓
- **本轮发 Windows + Linux x86_64**；macOS DMG 补同一 tag `comm-v1.7.1` 后再写 `url_mac`
- Linux 不提供 ARM 官方包

### 测试
- 全量测试：1647 passed，11 skipped，295 subtests passed

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.7.1.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.7.1.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.7.1.dmg` | arm64；拖入「应用程序」。本轮稍后补同一 Release |
| Linux（x86_64） | `CommTool_Setup_v1.7.1_linux_x86_64.run` | 免 sudo，默认 `~/.local/opt/CommTool`；glibc ≥ 2.27（Ubuntu 18.04+ / 多数麒麟） |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
