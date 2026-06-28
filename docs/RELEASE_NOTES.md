# CommTool v1.1.9（自动应答·脚本应答）

串口 + 网络一体调试工具。本版给**自动应答**加上**脚本应答**：每条规则可写一段 Python，命中时动态生成应答，适配静态模板与位掩码都覆盖不了的复杂逻辑（按收到内容算回值、查表、状态相关响应、自定义 CRC 等）。

## ✨ 新功能 / 改进

- **脚本应答** —— 规则行新增「脚本」按钮，定义 `reply(frame, ctx)`：
  - 返回 `bytes`=一帧 / `list[bytes]`=多帧 / `str`=文本 / `None`=不回；脚本拥有整帧、自己用 ctx 算校验。
  - `ctx`：`.state` 状态机当前状态 · `.seq` 自增序号 · `.hits` 命中数；**可定制 CRC** `ctx.crc(data, width, poly, init, refin, refout, xorout, byteorder)` + 便捷 `crc16`(Modbus) / `crc8` / `sum8` / `xor8` / `hexbytes` / `tohex`。
  - 编辑器内置「测试」即时跑一帧看输出；「启用脚本」开关可保留代码而临时停用；启用时该行静态「回复 / 校验」让位置灰。
- **安全隔离** —— 脚本在**独立子进程**执行：超时（默认 1s）整组强制终止（含脚本自己起的子进程），不冻结 GUI；预览 / 测试与实发各用独立进程、互不污染；**导入含脚本的配置前会征求同意**（拒绝则清空脚本）。
- 可与 v1.1.8 的位掩码匹配叠加；故障注入 + 延时 + 状态机 goto 对脚本应答同样生效；三语 i18n；新增 `tests/test_script.py`（进程隔离 / 整组杀含子进程 / 超时恢复 / 预览隔离 / CRC 标准向量 / 导入门禁）；无新依赖；脚本默认空 = 不启用，关时行为与 v1.1.8 一致。

## 📦 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| Windows 安装版 | `CommTool_Setup_v1.1.9.exe` | 推荐，向导安装 + 桌面快捷方式 |
| Windows 单文件版 | `CommTool_v1.1.9.exe` | 免安装，双击直接运行（首启自解压稍慢 1~2s） |
| macOS（Apple Silicon）| `CommTool_v1.1.9.dmg` | arm64；拖入「应用程序」。未公证，首次打开见下方说明 |

> Windows 10/11（64 位）无需安装 Python。旧版用户「帮助 → 关于 → 检查更新」即可升级
> （国内走 Gitee、海外回退 GitHub）。

> **macOS 首次打开提示「已损坏，无法打开」**：把 app 拖进「应用程序」后，终端运行一次
> `xattr -dr com.apple.quarantine /Applications/CommTool.app` 即可正常打开（仅 Apple Silicon）。
