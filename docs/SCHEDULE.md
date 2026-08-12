# CommTool 排期报告

> 基线：**v1.5.4**（2026-08-12）  
> 综合：`docs/TODO.md`、阶段 A/B 收口事实、发版后路线图复核。  
> 产品定位不变：**轻量、稳定、好用的串口/网络协议调试工具**；闭环止于「预设 → 自动化 → 记录 → 定位 → 报告」。

---

## 1. 总原则

| 原则 | 含义 |
|---|---|
| 下一阶段主线 | 可信度 + 体验 + 跨平台回归，**不堆大功能** |
| P2 | CLI / REST / 插件 **继续暂缓** |
| 工程债 | 只排有明确 ROI 的项；不为指标而洁癖 |
| 版本策略 | 阶段 A/B → **v1.5.3 已发**；打磨向 → **v1.5.4**；大功能/P2 才考虑 v1.6 |

---

## 2. 现状基线（已核对）

| 指标 | 数值 | 备注 |
|---|---|---|
| 发布版 | `comm-v1.5.4` | Win Setup/onefile；`url_mac` 待 Mac 协作者补门禁 |
| 测试 | **~1465+ passed / 11 skipped** | Windows 按文件隔离 pytest + macOS smoke |
| `main_window.py` | ~11944 行 | S-2 55 knives **已收口**；壳层有意保留 |
| 最长函数 | `__init__` / 连接侧 | `apply_style` / `_apply_language` 已薄拆到 `app_style` / `i18n_ui` |
| `except Exception` | 宽泛约 **199**（B6 二批后）/ 静默预算冻结 **9** | 见 `tests/test_silent_except_budget.py` |
| 多会话 | `SessionHostMixin` + 契约单测 | `test_session_host` / `test_multi_session` |
| 功能路线 | P0 / P1 / v1.4 / v1.5 / v1.5.2 / v1.5.3 | **均已收口** |

审查纠偏（避免排错）：

| 原说法 | 纠正 | 排期影响 |
|---|---|---|
| `_open_modbus` 466 行 | 不存在；最长 `apply_style` ~403 | 勿按假巨函数排拆分 |
| `session_host` 零测试 | 有 multi_session 行为覆盖 | 补契约单测即可 |
| `i18n` 零测试 | 已有分区键校验 | 补**全量**对拍，非从零 |
| `snippets` 无测试 | 已有 `SnippetsCoreTests` | 降级 |
| 立刻大拆 `main_window` 开 P2 | S-2 已收口 | 长期债，非短期主线 |

---

## 3. 阶段 A · 短期（约 0.5–1.5 人日）

目标：校正真源、消除明确重复、补契约测试。可打成 1–2 个小 PR。

| # | 项 | 量 | 完成标准 | 优先级 |
|---|---|---|---|---|
| **A1** | 文档真源校准 | 0.3d | `TODO.md` 数字/第三节 DONE 对齐；三语文案去掉 “Next up is P2”，改为稳定/多会话打磨 | **DONE** |
| **A2** | 抽取 split 持久化 | 0.3d | `_load_split_sizes` / `_sync_splits` → `split_persist`；对话框复用 | **DONE** |
| **A3** | i18n 全量键对拍 | 0.2d | zh / en / zh_tw 键集合一致；缺键 CI 失败 | **DONE** |
| **A4** | `session_host` 契约单测 | 0.5d | 切标签互斥、代理属性、后台 RX 不喂引擎、循环发送自动停 | **DONE** |
| **A5** | 拆 requirements | 0.1d | 运行时 `requirements.txt` + 开发 `requirements-dev.txt` | **DONE** |
| **A6** | 静默 except 复核 | 0.3d | `plot_dialog` / `session_host` 新增静默改 debug；重跑计数脚本；补 AST 预算门禁 `tests/test_silent_except_budget.py` | **DONE** |

---

## 4. 阶段 B · 下一版本周期（约 3–7 人日 → 建议 v1.5.3）

主题：跨平台可信 + 轻量质量门禁 + 多会话体验**择一**。

### 4.1 工程与 CI

| # | 项 | 量 | 完成标准 | 状态 |
|---|---|---|---|---|
| **B1** | macOS CI 烟雾 | 0.5–1d | `macos-latest` 跑 pytest 子集，防启动期 Qt 回归 | **DONE** |
| **B2** | ruff + pre-commit | 0.5d | 零门槛起步，只拦明显错误（`ruff.toml` E9/F63/F7/F82） | **DONE** |
| **B3** | pytest-cov 收集 | 0.3d | CI 上传 coverage.xml；**先不设硬门槛** | **DONE** |

### 4.2 产品打磨（三选一为主线）

| # | 选项 | 量 | 何时选 | 状态 |
|---|---|---|---|---|
| **B4a** | 多条循环发送 per-session | 1–2d | 与定时发送语义对齐 | **DONE**（会话级定时器；切标签不停） |
| **B4b** | 网关 UI 暴露 timeout / unit_map | 0.5–1d | 产线网关要可配映射/超时 | **DONE**（桥接对话框 + 持久化） |
| **B4c** | README 补多会话边界 3–5 条 | 0.2d | 成本最低的体验补强 | **DONE**（本轮选型） |

### 4.3 按痛点可选

| # | 项 | 量 | 完成标准 |
|---|---|---|---|
| **B5** | 拆 `apply_style` / `_apply_language` | 1–2d | 抽出 QSS/文案表；薄包装；**不**重启 55 knives 式全仓搬家；**DONE**（`app_style` / `i18n_ui`） |
| **B6** | 宽泛 except 抽样收敛 | 1d | 热点路径加类型或 debug；禁止为指标把吞异常改成炸 UI；**首批** `updater`/`serial_io`/`net_io`；**第二批** `main_window` 连接/发送/日志/设置 + `session_host` 会话路径 |

---

## 5. 阶段 C · 中长期（v1.6+，按触发条件）

| 项 | 触发条件 | 说明 |
|---|---|---|
| macOS 公证 / 安装体验 | Mac 用户或投诉上升 | 消 `xattr`「已损坏」路径 |
| Linux 官方包 + Linux CI | 有明确 Linux 需求 | 现有 `build.sh`，缺发行与矩阵 |
| PCAP 多客户端 TCP Server | 多客户端压测成常见场景 | 现仅单对端 |
| 事件总线迁移触发动作 | Webhook/外部程序动作继续膨胀 | 触发器只产事件（见 TODO 约定） |
| `pyproject.toml` / 子包化 | 需要可安装包或模块边界失控 | 高成本；非当前瓶颈 |
| **P2** CLI / REST / 插件 | 核心 Qt-free + 异常可追溯 + soak 基线达标 | 前置未满足前**不排期** |

---

## 6. 明确不排期

- 完整 VT100、BLE/HID/CAN、虚拟串口驱动  
- 触发联动发送  
- 会话树 / 拖拽分屏 / 标签拖出成窗  
- 用户脚本 `exec` 沙箱（本地调试边界；已有导入门禁）  
- PyQt6 全量 `exec_()` 迁移（无迁移计划时纯债）  
- 单独清 `__future__` / 定时器常量 / updater URL 常量（可顺手）  
- 覆盖率硬门槛、测试目录大重组  

---

## 7. 推荐执行顺序

1. ~~**A1–A6 / B1–B3 / B4c**~~ **DONE**（含 v1.5.3 发版与 Windows CI 隔离加固）  
2. **v1.5.4 打磨（无产品痛点时的默认序）**  
   1. ~~**updater Windows 路径单测**~~（`tests/test_updater_win.py`）  
   2. ~~**B6 首批 + 第二批**~~（`updater`/`serial_io`/`net_io`；`main_window` 连接/发送/日志/设置与 `session_host` 抽样；其余按痛点再抽）  
   3. ~~**B4b** 网关 UI timeout / unit_map~~；~~**B4a** 循环 per-session~~  
   4. ~~**B5** 薄拆 `apply_style` / `_apply_language`~~（`src/app_style.py` + `src/i18n_ui.py`）  
3. **不上**覆盖率硬门槛（B3 只收集，见 §6）  
4. 阶段 C / P2 / PyQt6 仅按触发条件启动  

---

## 8. 与 `docs/TODO.md` 的关系

- **历史功能池 / P0–P1 / v1.4–v1.5 备查** → 仍以 `TODO.md` 为准。  
- **v1.5.3 之后「接下来做什么」** → 以本文件 §7 与阶段 C 为准。  
- 完成 A1 时应把 `TODO.md` 过时数字与「Next up is P2」类表述一并校正，避免双真源。
