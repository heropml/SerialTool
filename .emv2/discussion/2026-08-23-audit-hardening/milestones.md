# S6 子流程拆分

## S6-A：可靠性与安全闭环（优先级 1）

- 修复自动应答冷却首次命中。
- 增加更新 SHA-256 / 大小校验和旧 manifest 降级策略。
- 增加 Webhook DNS、地址分类、重定向保护。
- 验证：目标单测、更新器与触发器测试组。

## S6-B：诊断与供应链（优先级 2）

- 滚动诊断日志和诊断包核心。
- Python/依赖 constraints、CI 双版本、打包 smoke。
- 验证：纯逻辑测试、CI 配置检查、Ruff。

## S6-C：可交付工作流（优先级 3）

- 首屏快速开始。
- 操作面板资源模型最小闭环。
- 可复用帧模板与本地录制会话索引核心。
- 验证：模型单测、项目兼容测试、离屏 UI smoke。

## S6-D：架构收敛与总回归（优先级 4）

- 新策略保持 Qt-free；主窗口只接编排接口。
- 更新文档、EM 记录和发布边界。
- 验证：全量测试、soak、compileall、Ruff、关键 UI 快照。

状态：已完成。Ruff / compileall 通过；全量 1691 项中 1675 passed / 8 skipped，
另 8 项 localhost TCP/UDP 因当前沙箱禁止 `bind()` 而失败，直接 socket 探针同样返回
`PermissionError(1)`，非代码回归。
