# 问题追踪

## 当前问题

### [2026-08-23] P1-01 首次自动应答可能被冷却窗口误拦
- **状态**: closed
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: 冷却逻辑把“从未命中”的默认时间 `0.0` 当成真实时间戳；当 `time.monotonic()` 小于冷却时长时，首次合法命中会直接返回。

### 分析
- `tests/test_multi_session.py::test_auto_reply_cooldown_is_session_owned` 独立复现失败，计划发送列表为空。
- 当前环境 `time.monotonic()` 约 0.007 s，`cooldown_blocks(now, 0.0, 60000)` 返回 `True`。
- 影响范围是新进程 / 新启动环境、长冷却规则及每会话首次命中。

### 解决方案
- 仅当 last 时间戳真实存在且大于 0 时才应用冷却；新增首次命中、跨会话和时钟起点很小的纯逻辑单测。

### 闭环记录
- **解决日期**: 2026-08-23
- **验证方式**: 目标单测 + 自动应答全组 + 多会话全组
- **证据**: `src/automation/auto_reply_gate.py:85`、`src/main_window.py:7945`

---

### [2026-08-23] P1-02 在线更新缺少内容完整性与发布者校验
- **状态**: mitigated（自动安装门禁已闭环；平台发布者签名待凭据）
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: manifest 只有版本和 URL；下载完成仅检查 Windows `MZ` / Linux `#!`，macOS 甚至没有内容校验。HTTPS 只能保护传输，不能在源账号、镜像或发布链被篡改时证明安装包来自预期发布者。

### 分析
- `latest.json` 无 `sha256` 或签名字段。
- Windows / Linux 下载后会被直接启动；macOS 仅下载打开。

### 解决方案
- 最低限度：manifest 增加每平台 SHA-256 和文件大小，下载时流式校验。
- 推荐：对 manifest 做 Ed25519 签名并在客户端内置公钥；Windows 使用 Authenticode，macOS 使用 Developer ID + notarization，Linux 发布 detached signature / checksum。

### 闭环记录
- **解决日期**: 2026-08-23（SHA-256 / 大小 / 人工降级）
- **验证方式**: 正确包、篡改包、错误大小、签名错误、回退源一致性测试
- **证据**: `src/updater.py:189`、`src/updater.py:261`、`latest.json`

---

### [2026-08-23] P1-03 Webhook 私网保护可被域名解析与跳转绕过
- **状态**: closed
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: `is_private_url()` 只拦截 localhost 和私网 IP 字面量，明确不解析域名；`urlopen()` 还会自动跟随跳转。公共域名可解析到私网地址，或公开 URL 可 30x 跳向 localhost / 内网。

### 分析
- 导入外部动作已有信任确认，这是有效的第一道门，但不能替代运行时出站策略。
- 当前允许明文 `http://`，且请求前后都没有对解析地址和 redirect target 复检。

### 解决方案
- 默认仅允许 HTTPS；解析全部 A / AAAA 并拒绝私网、回环、链路本地、保留和元数据地址。
- 禁止自动跳转或逐跳复检；连接阶段防 DNS rebinding（校验实际 peer / 使用固定解析结果）；提供显式“允许私网 Webhook”高级开关。

### 闭环记录
- **解决日期**: 2026-08-23
- **验证方式**: DNS->127.0.0.1、IPv4-mapped IPv6、30x->私网、多地址混合和 TOCTOU 用例
- **证据**: `src/automation/trigger_safe.py:12`、`src/automation/trigger_actions.py:102`

---

### [2026-08-23] P2-01 诊断日志没有可交付出口
- **状态**: closed
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: 多个热点已把异常改为 `_log.debug(..., exc_info=True)`，但仓库中未发现统一日志初始化、滚动文件或“导出诊断包”。发行版用户遇到偶发串口 / BLE / Qt 错误时，信息仍会消失。

### 解决方案
- 在配置目录增加默认关闭敏感载荷的滚动诊断日志，记录版本、平台、连接类型、状态迁移和 traceback；增加一键导出并脱敏。

### 闭环记录
- **解决日期**: 2026-08-23
- **证据**: `src/diagnostics.py`、帮助 → 导出诊断包、`tests/test_diagnostics.py`

---

### [2026-08-23] P2-02 主窗口与热点路径复杂度继续升高
- **状态**: mitigated（新增领域逻辑 Qt-free；主窗继续分 seam 抽取）
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: `main_window.py` 13,023 行，含 UI、连接编排、RX/TX、自动应答、Modbus、录制、设置和发布交互；复杂度扫描显示 `open_conn`、`close_conn`、`_on_data_received_impl`、`_send_text`、`_load_settings` 等均有大量分支。

### 解决方案
- 不做大重写；先定义 `ConnectionController`、`RxPipeline`、`TxPipeline`、`SettingsRepository` 四个接口，按一条路径一个小 PR 抽取；保持 Qt-free 核心和现有契约测试。

---

### [2026-08-23] P2-03 平台基线、CI 与依赖供应链不一致
- **状态**: mitigated（Python/constraints/CI 已闭环；Qt6/SBOM 后续独立项）
- **步骤**: S4
- **发现时间**: 2026-08-23
- **描述**: README 声明 Python 3.9+，本地环境为 Python 3.9.6 / Qt 5.15.14 / PyQt 5.15.11；CI 只测 Python 3.12。Python 3.9 已 EOL，Qt 5.15 标准支持也已结束。requirements 只有下界、无锁定/哈希/SBOM，跨时间重建不可复现。

### 解决方案
- 短期把发行构建固定到 Python 3.11 或 3.12，并用 lock / constraints 固定直接与间接依赖；CI 测“最低支持 + 构建版本”。
- 中期做 PySide6 / Qt 6.8 LTS 兼容分支和启动 smoke，不在主分支一次性迁移。
- 加依赖漏洞扫描、SBOM、打包后启动 smoke 与更新器篡改测试。

---

### [2026-08-23] P2-04 产品入口密度高，空状态缺少任务引导
- **状态**: closed
- **步骤**: S5
- **发现时间**: 2026-08-23
- **描述**: 默认界面信息架构已较整齐，但首屏有 7 个工作区、左侧多卡片和大量工具；接收区空状态完全空白，新用户不知道应先连接、打开示例工程还是用 Virtual 回环。

### 解决方案
- 空状态加入“串口快速连接 / Virtual 回环演示 / 打开示例工程 / 最近工程”。
- 将多条发送 + 仪表盘 + 工程资源组合成可分享的“设备操作面板 / 只运行模式”。
- 把现有帧构造器升级为工程级可复用帧模板，支持字段编辑、派生长度/校验和 RX 解码。
- 录制文件增加本地索引、标签、搜索和一键复现；避免直接上云同步。

---

### [2026-08-23] P1-04 Python 3.13 CI 被 NumPy 约束破坏
- **状态**: closed
- **步骤**: S7
- **描述**: 兼容 CI 声明 Python 3.13，但 `constraints-runtime.txt` 锁定 NumPy 2.0.2；该版本只支持 Python 3.9–3.12，3.13 环境无对应 wheel。
- **解决方案**: 固定 NumPy 2.2.6（Python 3.10–3.13，manylinux2014/glibc 2.17+）；构建脚本仅选 3.11–3.13，发布脚本强制 3.13。
- **闭环证据**: Python 3.11 全新 venv 安装约束成功，最终 2002 项全量回归零失败。

---

### [2026-08-23] P1-05 快速开始可造成连接表单/实际链路错配
- **状态**: closed
- **步骤**: S7
- **描述**: 已有串口/网络连接打开且接收区为空时，点 Virtual 快捷入口会把表单切成 Virtual，但底层仍持有原连接。
- **解决方案**: 活动连接期间禁用该入口且方法二次防护；内置示例改为未保存模板，避免保存覆盖 `_MEIPASS`/源码示例。
- **闭环证据**: `tests/test_workspace.py` 快速开始与 template 语义测试。

---

### [2026-08-23] P2-05 损坏资源与多配置日志竞争
- **状态**: closed
- **步骤**: S7
- **描述**: 帧模板/操作面板/录制索引的容器类型异常可引发 UI 打开失败；不同 profile 进程共写同一个 `RotatingFileHandler` 文件存在轮转竞争。
- **解决方案**: 限制工程/索引/头部大小，严格版本类型，规范化元数据，为每个 profile 分配独立日志文件。
- **闭环证据**: 20,000 组畸形输入通过；`tests/test_product_resources.py` / `tests/test_diagnostics.py` 回归通过。

---

### [2026-08-23] P1-06 示例工程覆盖恢复锚点与旧 Webhook 兼容中断
- **状态**: closed
- **步骤**: S7 follow-up
- **描述**: 以模板方式打开打包示例会删除 `last_project_path`；同时，升级前没有 `webhook_allow_insecure` 字段的 HTTP / 局域网 Webhook 会被新版安全默认静默拦截。
- **解决方案**: 示例模板只清当前保存目标，不再清上次工程；本机旧规则一次性显式化既有 Webhook 权限，外部导入仅在用户确认保留外部动作后迁移，显式 `False` 与新建规则继续保持安全默认。
- **闭环证据**: `tests/test_workspace.py`、`tests/test_triggers.py`、`tests/test_review_fixes.py`；Python 3.11 最终全量 1710 项零失败。

---

### [2026-08-23] P2-06 帧模板同名保存静默删除与首接收框重复刷新
- **状态**: closed
- **步骤**: S7 follow-up
- **描述**: 编辑模板 A 并保存为已存在的 B 会无提示删除 B；首个会话接收框的 `textChanged` 同时在卡片和会话宿主绑定，导致空状态重复刷新。
- **解决方案**: 同名冲突改为显式异常并由 UI 三语确认后才覆盖；接收框信号统一由 `SessionHostMixin` 单点绑定。
- **闭环证据**: `tests/test_product_resources.py` 的冲突/确认领域契约；`tests/test_workspace.py` 断言首接收框只有一个 `textChanged` 接收者。

---

## 历史归档

<!-- 已闭环问题归档索引 -->
