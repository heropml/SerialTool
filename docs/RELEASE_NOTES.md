**CommTool** 串口调试助手 / 网络调试工具（UART + RTT + TCP/UDP）。**v1.8.4**：新增「雾白」浅色皮肤。

## v1.8.4 更新内容

### 雾白皮肤

- 在顶部主题下拉框选择「雾白 / Mist / 霧白」，立即切换整套界面配色。
- 冷灰窗口背景、纯白卡片、浅灰输入框与细边框，搭配炭黑操作按钮和低饱和文字，主界面与弹窗保持一致。
- 接收区使用纯白背景，发送文字保留独立的柔和紫色；连接状态、警告和错误仍使用各自的状态色。
- 原有 9 套主题的配色与样式保持一致；继续支持主题即时切换、历史文字重绘及重启恢复。

### 兼容性与安装包

- 通信协议、收发逻辑与配置格式保持不变，无新增运行时依赖；随包示例工程版本同步为 v1.8.4。
- 自本版本起，Windows 仅提供 Setup 安装包，停止发布免安装单文件版。
- Windows、macOS Apple Silicon 与 Linux x86_64 安装包对应同一版本和源代码。

## 下载与安装

| 平台 | 文件 | 安装方式 |
|------|------|----------|
| Windows 10/11（64 位） | `CommTool_Setup_v1.8.4.exe` | 向导安装，可创建桌面快捷方式 |
| macOS（Apple Silicon） | `CommTool_v1.8.4.dmg` | 打开 `.dmg`，拖入“应用程序”安装 |

Linux x86_64：`CommTool_Setup_v1.8.4_linux_x86_64.run`，执行后安装到 `~/.local/opt/CommTool`，无需 sudo，要求 glibc ≥ 2.27（Ubuntu 18.04+）。

> Linux `.run` 按仓库发布渠道约定，仅在 [GitHub Release](https://github.com/heropml/SerialTool/releases/tag/comm-v1.8.4) 提供；Windows Setup 和 macOS DMG 在 GitHub、Gitee 均提供。

RTT 需另装 SEGGER J-Link 驱动。首次使用新皮肤时，在顶部主题下拉框选择「雾白」。
