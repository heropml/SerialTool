# 项目规格单：CommTool

## Meta
- **创建日期**: 2026-08-23
- **项目类型**: 跨平台桌面通信调试工具（PyQt5；Serial / TCP / UDP / Virtual / BLE）
- **当前步骤**: S7 循环审核与零回归缺陷闭环
- **整体状态**: v1.7.3 已发布；S6/S7 整改和循环回归已完成，待正常发布流程出包
- **项目路径**: `/Users/heropml/software/SerialTool`
- **芯片型号**: 不适用（本仓库不是 MCU 固件）

## 开发步骤状态

| 步骤 | 名称 | 状态 | 日期 |
|------|------|------|------|
| S1 | 串口 / 网络 / Virtual 传输基线 | 已完成 | 2026-08-23 复核 |
| S2 | 协议、Modbus、录制回放与自动化 | 已完成 | 2026-08-23 复核 |
| S3 | 多会话、三语、跨平台打包 | 已完成 | 2026-08-23 复核 |
| S4 | CI、静态检查、soak 与发布流程 | 已完成（平台签名凭据除外） | 2026-08-23 |
| S5 | 更新信任、外部动作安全、架构收敛与产品体验 | 已完成本轮范围 | 2026-08-23 |
| S6 | 审计问题全量整改 | 已完成 | 2026-08-23 |
| S7 | 循环审核、边界加固与全量回归 | 已完成 | 2026-08-23 |

## 现状基线

- Git：`CommTool` 与 `origin/CommTool` 同步；审计开始时工作区干净；HEAD `ac2e85c`。
- 规模：`src + tests + scripts` 共 92,693 行 Python；`src/main_window.py` 13,023 行。
- 异常处理：宽泛捕获 199 处，静默捕获 9 处；新增宽泛捕获用于原子文件清理后重抛。
- 静态检查：现有 Ruff 门禁通过；`compileall` 通过（缓存改到 `/tmp` 以避开沙箱权限）。
- 测试：最终在正常 localhost 权限、Python 3.11 + NumPy 2.2.6 + pytest 9 环境全量 `1994 passed / 8 skipped / 0 failed / 0 errors`（共 2002 项）。
- 边界审计：20,000 组随机畸形 JSON/资源输入无崩溃；Ruff、compileall、Bash 语法、CI YAML 解析与 `git diff --check` 均通过。
- 性能烟雾：默认 RX 路径 2,000 × 128 B 用时约 0.80 s（约 318 KB/s）；现有 soak 子集 11 passed / 3 skipped。

## 问题追踪

### 后续边界

- Windows Authenticode、macOS Developer ID / notarization、Linux detached signature 仍需要发布者证书/密钥；本轮已完成客户端 SHA-256/大小门禁和无摘要人工降级。
- Qt5 → Qt6 属独立迁移版本，不与本轮可靠性整改混做；新策略与资源模型均已 Qt-free，为迁移收窄范围。
- `main_window.py` 不做高风险一次性重写，后续继续按连接/RX/TX/设置 seam 小步抽取。

详见 `problem-log.md`。

### 已解决问题

- 首次自动应答冷却、更新完整性、Webhook DNS/重绑定/跳转边界、滚动日志与脱敏诊断包。
- Python 3.11–3.13 基线、3.11/3.13 兼容 CI、NumPy 2.2.6 约束、发布摘要原子写入/错误码门禁。
- 内置示例按未保存模板打开、连接中禁止 Virtual 快捷切换、多配置进程日志分文件。
- 快速开始、工程级帧模板、操作面板资源和本地 `.ctrec` 会话索引。
- 传输、协议、自动化、多会话、三语、项目文件、录制回放、跨平台 smoke 已形成较完整功能与测试基线。

## 参考文档

- 项目说明：`README.md`
- 当前排期：`docs/SCHEDULE.md`
- 发布说明：`docs/RELEASE_NOTES.md`
- 芯片手册 / 开发板原理图：不适用
