串口 + 网络一体调试工具。**v1.4.1 正式版**：在 v1.4.0 能力基线上，完成 S-2 主窗口可维护拆分与 S-1/S-3/S-4/S-5 稳定性/易用性收尾。

## v1.4.1 正式版

### 架构与可维护（S-2）
- **主窗口服务层拆分（R1–R33）**：自动应答 / 序列引擎 / 报告 / 视图格式 / RX 文本 / 触发安全 / 配置键与导入导出 / 连接预设 / 串口参数等 Qt-free 模块；`CommTool` 保留薄包装
- **GUI build_* 工厂（R34–R42）**：`ui_options` / `conn_ui` / 侧栏三卡 / 收发区 / sidebar / workspace 构建全部迁出；主窗口仅组装

### 稳定性与易用性（S-1 / S-3 / S-4 / S-5）
- **S-1**：主路径静默 `except` 收敛为 debug 日志；`proc.pid` 守卫、日志切段分步关闭
- **S-3**：吞吐与重连突发基线；`COMMTOOL_SOAK` / nightly 可选长跑
- **S-4**：日志按大小切分（`parse_size_limit` / `should_roll_size`）
- **S-5**：连接/断线/发送失败可操作提示；发送历史搜索；Modbus 主机「单次读写」

### 修复
- `parse_json_list([])` / `parse_json_dict({})` 不再误返 `None`（空与缺失区分）
- 空发送仍重置发送历史导航态
- 清理 `bridge_dialog` / `main_window` 未使用导入
- 无换行连续收包的单 block 字符预算裁剪（`_trim_recv_overflow`）

### 测试
- 基线：**1148 passed / 4 skipped / 291 subtests**

## 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.4.1.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.4.1.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.4.1.dmg` | arm64；拖入「应用程序」。未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户可通过「帮助 → 关于 → 检查更新」升级（国内优先走 Gitee，海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，在终端运行一次 `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
