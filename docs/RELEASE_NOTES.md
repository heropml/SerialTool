# NetworkTool v1.0.8

高亮闪烁修复版。网络调试功能（UDP / UDP 组播 / TCP Server / TCP Client）与 v1.0.7 相同。

## 🐞 修复

- **高亮闪烁** — 开启关键字 / 搜索高亮时，底部新接收的数据不再「整批闪一下高亮」。
  之前是因为高亮的叠加选区(ExtraSelection)会随新追加的数据延伸、把新行也圈进高亮，约 0.15 秒后重建才恢复；现已钉住选区端点(setKeepPositionOnInsert)修复。

## 📦 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| 安装版 | `NetworkTool_Setup_v1.0.8.exe` | 推荐，向导安装 + 桌面快捷方式 |
| 文件夹版 | `dist/NetworkTool/` | 解压即用，启动最快 |

> 无需安装 Python；Windows 10/11。在线更新「关于 → 检查更新」即可检测到 v1.0.8。
