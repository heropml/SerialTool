# CommTool v1.0.9（统一版）

串口 + 网络一体调试工具。由串口版 SerialTool 与网络版 NetworkTool 合并而来：左上角「类型」下拉统一了 **Serial（串口）/ UDP / UDP 组播 / TCP Server / TCP Client** 五种连接，串口与网络共用同一套数据区 / 发送 / 高亮 / 日志 / 多条发送 / 主题 / 语言。

## ✨ 本版亮点

- **串口 + 网络合一** — 一个产品同时支持串口（pyserial）与 TCP/UDP（QtNetwork），「类型」下拉一键切换，不必在两个工具间来回倒。
- **统一品牌** — 产品、窗口标题、安装包、配置目录统一为 **CommTool / 通信调试工具**；全新独立安装身份，不覆盖旧的 SerialTool / NetworkTool，旧 NetworkTool 的配置首次启动自动沿用。
- 其余收发、10 种校验、关键字高亮、实时日志、9 套主题、三语界面等功能与原网络版一致。

## 📦 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| 安装版 | `CommTool_Setup_v1.0.9.exe` | 推荐，向导安装 + 桌面快捷方式 |
| 文件夹版 | `dist/CommTool/` | 解压即用，启动最快 |

> 无需安装 Python；Windows 10/11（64 位）。在线更新「关于 → 检查更新」走 CommTool 分支。
