**CommTool** 串口调试助手 / 网络调试工具支持 UART、RTT 和 TCP/UDP。v1.8.9 支持在同一个窗口同时连接多把 J-Link，并改进 RTT 探针列表、重连和发送失败提示。

## RTT 多探针

- 每个 RTT 标签可连接一把独立的 J-Link。即使两块目标板型号相同，也可以按调试器序列号分别连接。
- 展开「调试器」时后台扫描当前连接的探针，保留当前选择。自动重连会沿用该会话已识别的探针。
- 所选 RTT 通道缺少下行缓冲区时，应用会提示无法发送并保留连接。通道由各块板的固件分别配置，两块板都在通道 0 提供终端时，两个标签均可选择通道 0。
- Windows 实机验证使用两把 J-Link 的两个标签分别发送 `help`，均收到自身目标的帮助菜单。没有下行缓冲区的一路提示发送失败后，两路仍保持连接。

## 使用说明

简体中文、繁体中文和英文使用说明的目录和更新正文都只保留最近 5 个版本。更早的版本记录可在 [GitHub Releases](https://github.com/heropml/SerialTool/releases) 查看。

Linux 覆盖安装会保留安装目录中的用户配置和日志。

## 下载与安装

| 平台 | 文件 | 安装方式 |
|------|------|----------|
| Windows 10/11（64 位） | `CommTool_Setup_v1.8.9.exe` | 运行安装向导 |
| macOS（Apple Silicon） | `CommTool_v1.8.9.dmg` | 打开镜像，将应用拖入「应用程序」 |
| Linux x86_64 | `CommTool_Setup_v1.8.9_linux_x86_64.run` | 赋予执行权限后运行，默认安装到 `~/.local/opt/CommTool` |

RTT 连接需安装 SEGGER J-Link 驱动。Gitee 未提供 Linux 安装包时，请从 [GitHub Release](https://github.com/heropml/SerialTool/releases/tag/comm-v1.8.9) 下载。
