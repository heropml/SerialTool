# 项目记忆日志 - CommTool

## 会话指纹
- **项目ID**: `commtool-serialtool`
- **当前会话**: `s7-loop-audit-zero-regression-2026-08-23`
- **会话链**: `v1.7.3 -> 全量复审 -> S6 全量整改 -> S7 循环审核`

## 快速恢复信息
```
恢复命令: /em rec /Users/heropml/software/SerialTool
最后活跃: 2026-08-23
```

## 关键决策
- [2026-08-23] 下一轮先修自动应答冷却、更新完整性和 Webhook 出站安全，不先扩 CAN / HID / MQTT / 插件。
- [2026-08-23] 市场借鉴优先落到“可交付工作流”：设备操作面板、可复用帧模板、会话索引与诊断包，而不是继续增加顶层入口。
- [2026-08-23] `main_window.py` 不做一次性大重写；围绕连接、RX、TX、设置四条 seam 逐段抽取并用契约测试兜底。

## 会话历史

### s7-loop-audit-zero-regression-2026-08-23 (2026-08-23)
- **主要内容**: 按“静态门禁 → 全量测试 → 高风险路径人工审查 → 畸形输入 → 再回归”循环审核，并在 follow-up 中闭环示例工程、旧 Webhook、帧模板同名与重复信号四项行为问题。
- **产出**: 修正 Python/Ruff/依赖基线、发布摘要门禁、工程/录制/资源解析边界、快速开始状态、内置示例保存语义、旧外部动作迁移、模板覆盖确认和多进程日志竞争。
- **验证**: follow-up 最终在 Python 3.11 全新锁定环境收集 1710 项，1702 passed / 8 skipped / 0 failed / 0 errors；Ruff、compileall、Bash、CI YAML、pip check、diff check 全绿；此前 20,000 组畸形输入通过。

### s6-audit-hardening-2026-08-23 (2026-08-23)
- **主要内容**: 用户确认“全部改下”；完成五阶段需求对齐与 S6-A~D 全量落地。
- **产出**: 更新/Webhook 安全、诊断/供应链、快速开始、帧模板、操作面板资源、录制索引、架构/安全文档。
- **验证**: Ruff / compileall 通过；1691 项中 1675 passed / 8 skipped；8 项仅因沙箱禁止 localhost `bind()`。

### audit-2026-08-23 (2026-08-23)
- **主要内容**: 全仓结构、传输/协议/自动化/安全、CI/发布、性能、离屏 UI 与同类产品复审。
- **产出**: `project-spec.md`、`problem-log.md`、`decision-log.md`；业务代码未修改。
- **验证**: Ruff 通过；compileall 通过；全量测试 1662 passed / 8 skipped / 9 failed；soak 子集 11 passed / 3 skipped。
