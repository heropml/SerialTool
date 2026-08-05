# CommTool 开发待办与已知问题

> 本文件是 CommTool 的后续开发基线。后续新增功能、拆分任务和排期，优先以第四节「执行版路线图」为准；第三节仅作为市场对标后的备选功能池。
> 已落地的（Modbus ASCII、寄存器表↔绘图联动、搜索正则/HEX、时间戳多格式、冻结显示、结构化记录/设备中心帮助按钮等）不在未完成清单中。
> 产品定位（v1.4 起收窄）：**轻量、稳定、好用的串口/网络协议调试工具**。面向嵌入式研发、协议联调和产线验机，
> 闭环止于「设备预设 → 自动化测试 → 收发记录 → 失败定位 → 报告导出」，不再向 CLI/API/插件平台化延伸。
> 收窄理由与恢复判据见第四节「P2：平台化能力（v1.4 起暂缓）」。
> 完整路线图背景见 plan：`D:\mingl\Documents\.claude\plans\encapsulated-riding-marshmallow.md`

---

## 一、本轮已处理的低优先级遗留

| # | 严重度 | 位置 | 问题 | 建议修法 |
|---|---|---|---|---|
| 1 | 已修复 | `main_window.py` 终端模式路径 | 终端模式启用时会自动关闭并禁用冻结显示，避免开关状态与实际显示不一致 | — |
| 2 | 已修复（有限导航） | `main_window.py` `_refresh_extra_selections` 搜索段 | 搜索高亮数量受 `_KW_MAX_SELECTIONS` 限制；计数以 `+` 标记仍有未展示匹配，避免大流拖慢渲染 | 若需完整导航，可后续改为按页加载匹配 |

> 附注（非 bug，记备查）：ASCII 切帧只认 `\n` 作帧尾（规范是 CRLF）。主流设备 CRLF/LF 都能处理；纯 CR（无 LF）的非标设备会让帧累积到下一帧的 `\n`。极罕见。

---

## 二、落地 C（数据区体验包）遗留

- DONE **书签 / 标记行跳转**（`Ctrl+F2` 加/清、`F2/Shift+F2` 跳转）
  - 当初因 QTextEdit 无原生 gutter、需自建侧栏标记基建而**暂缓**
  - 轻量实现：维护 `self._bookmarks = []`（QTextCursor 列表）+ extra-selection 高亮 + 快捷键，不持久化（会话级标记）
  - 关键文件：`main_window.py` 搜索栏区 (`_build_search_bar` / `_do_search`)、`_refresh_extra_selections`

---

## 三、可借鉴功能池（未做部分）

> 本节是经过市场对标后的候选池，不代表实际开发顺序。实际顺序以第五节为准。

### Tier 1 — 高性价比（低成本、命中面广）

| # | 功能 | 对标 | 价值 | 量 | 复用点 |
|---|---|---|---|---|---|
| ⭐ | **具名连接预设/收藏夹** | YAT/Termite | 不用每次重选 COM/波特 | 低 | 新 settings 列表 + 连接栏下拉 |
| ⭐ | **关键字高亮支持正则/HEX** | 触发器已有、着色规则没有 | 统一两套匹配 | 低 | `KeywordHighlightDialog` 接 `triggers.py` 的 4 模式 (`MODE_*`) |
| ⭐ | **自动化序列：变量/上下文传递** | Postman collection runner | 上一步解析值带入下一步断言（读 SN→后续用） | 中 | `main_window._seq_*` 加上下文字典 + 模板替换 |
| ⭐ | **自动化序列：CSV 数据驱动** | 测试序列器标配 | 每行参数跑一轮、多设备批测 | 中 | `_seq_*` 读 CSV → 模板替换每步字段 |
| ⭐ | **自动化序列：JUnit XML 报告** | CI 友好 | 接 CI 流水线 | 低 | `_build_report_html/csv` (`dialogs.py`) 旁加 xml 生成 |
| ⭐ | **统计补 pps + 包大小分布 + min/max/avg** | Wireshark I/O Graph | 排障带宽/异常包 | 中 | `_tick_rate` (1Hz 采样, `main_window.py` ~8900) 已有，扩字段 |

### Tier 2 — 中等投入（旗舰体验、单点突破）

| # | 功能 | 对标 | 价值 | 量 | 复用点 |
|---|---|---|---|---|---|
| ⭐ | **绘图部件扩展：双 Y 轴 / XY / 柱状 / 直方图 / 仪表(gauge) / LED / 进度条** | Serial Studio/PlotJuggler | 可视化维度质变 | 中-高 | pyqtgraph 已在用；`plot_dialog.py` / `dashboard_dialog.py` |
| ⭐ | **绘图/仪表盘数据持久化 + CSV 回放绘图** | PlotJuggler | 关掉不丢、离线回看 | 中 | `StructuredRecorder` CSV 思路复用 |
| | **TCP/UDP 专用 PCAP/pcapng 导出** | Wireshark | 网络流量与 Wireshark 互通 | 中 | 仅针对 TCP/UDP；串口继续使用 `.ctrec`，不强行套 PCAP |
| | Excel/xlsx 导出 | ModbusSimulator | 报表交非技术同事 | 中 | 现 CSV 已防注入，加 openpyxl |
| | 吞吐量随时间曲线（I/O Graph） | Wireshark | 带宽抖动可视化 | 中 | 扩 plot，按 `_rx_rate/_tx_rate` 历史 |
| ⭐ | DONE **Modbus 网关（TCP↔RTU 路由）+ 多从机模拟** | 工业网关/ModRSsim2 | 测多设备总线、网关转发 | 中-高 | `bridge.py` 引擎 + `modbus_slave` 多实例字典（多从机与真·TCP↔RTU 网关路由均已完成；网关见 `modbus_gateway.py`） |
| ⭐ | DONE **更多 Modbus 功能码（FC08诊断/FC11/FC17/FC23读写多/FC22掩码写/FC43设备标识）** | ModbusSimulator(14码) | 覆盖诊断与一次读写 | 中 | `modbus_master/slave._exec` / `SUPPORTED_FUNCS` |
| | DONE 位域(bitfield)解析 | 嵌入式协议工具 | 寄存器内部按位拆 | 中 | `device_resources.parse_bitfields` / `decode_bitfields` + 设备中心「位域」列 |
| | 回放驱动真实 TX（不只注入虚拟连接） | IO Ninja | 录的帧从真实串口/网络发出去 | 中 | `rec_replay.Player` 注入路径加一条 TX 侧 |
| | DONE 触发动作：webhook / 命中N次 / 运行外部程序 | Docklight action chain | 接运维/告警链路 | 中 | `_fire_trigger`（`main_window.py`）扩动作集；提前落地的取舍见第四节「Webhook / 外部程序提前落地的取舍」 |

### Tier 3 — 大工程/战略级（差异化壁垒，单独立项）

> v1.4 起：本梯队的远程 API、Headless/CLI、插件式 dissector 三项已整体暂缓，理由见第四节。
> 此处保留仅作市场对标记录，不代表排期。

| # | 功能 | 对标 | 价值 | 量 |
|---|---|---|---|---|
| ⭐ | **远程控制 API（REST / WebSocket）** | ModbusSimulator(REST for Excel/VBA) | 让别的程序驱动 CommTool 收发/读统计/触发序列 | 高 |
| ⭐ | **Headless / CLI 模式**（无界面跑序列/脚本出报告） | socat/pyserial/商业 CLI | CI 里发收包+出 JUnit | 高（拆 GUI/逻辑） |
| ⭐ | **插件式协议 dissector**（脚本化协议解码器） | Wireshark Lua / IO Ninja | 生态壁垒、用户自定义协议 | 高 |
| | SSL/TLS 加密连接 | SecureCRT/MobaXterm | 加密调试通道 | 中-高（`QSslSocket` 包一层 `TcpClientConn`） |
| | 工程模板库 / 示例工程仓库 | 工程化商业工具 | 开箱即用 | 中 |

### 明确不建议借鉴（设计取舍 / 偏离定位）
- **完整 VT100 仿真**（光标/滚动区/备用屏）——刻意只做 SGR 着色，PuTTY 类终端已够用
- **触发联动发送**——刻意不做，避免与自动应答引擎互斥打架
- **蓝牙(BLE/RFCOMM)/USB HID/CAN/SPI/I2C 硬件接口**——需独立硬件驱动栈，偏离"协议调试"定位
- **OS 级虚拟串口对(com0com 类)**——需内核驱动，安装/签名成本高

---

## 四、执行版路线图（后续按此推进）

> 目标不是继续堆叠终端功能，而是把已有通信、协议、自动化、记录和可视化能力串成可复用的测试闭环。
> 优先级定义：P0 = 下一阶段直接开发；P1 = P0 稳定后开发；P2 = 核心架构完成后单独立项。

### P0：自动化测试闭环 + 工作区效率

| 顺序 | 功能 | 目标 | 完成标准 | 主要复用点 |
|---|---|---|---|---|
| P0-1 | **具名连接预设/收藏夹** ✅ | 减少重复配置，支持设备快速切换 | 保存串口/TCP/UDP 全部参数、备注、自动重连策略；支持最近使用、复制、删除；可随 `.ctproj` 打包 | 现有 settings、工程资源、连接栏 |
| P0-2 | **自动化序列变量/上下文** ✅ | 上一步结果可以驱动后续步骤 | 支持 `${name}` 模板；能从回包提取文本、HEX、正则分组和 Modbus 字段；变量作用域按单轮测试隔离 | `main_window._seq_*`、脚本/帧解析、设备资源 |
| P0-3 | **CSV 数据驱动序列** ✅ | 一套用例批测多台设备 | 每行参数执行一轮；支持跳过、失败即停、失败继续；报告能关联行号和设备标识 | 序列引擎、工程资源、CSV 导入导出 |
| P0-4 | **测试报告和测试产物** ✅ | 能交付、归档并接入 CI | 保留 HTML/CSV；新增 JUnit XML；报告包含测试参数、软件版本、开始结束时间、每步耗时、失败原因和关键收发帧 | `_build_report_html/csv`、`.ctrec`、结构化记录 |
| P0-5 | **统计与诊断增强** ✅ | 快速判断丢包、堵塞和异常延迟 | 增加 pps、包大小分布、min/max/avg、峰值、超时次数和吞吐曲线；统计可重置且不影响记录 | `_tick_rate`、现有 RX/TX 统计、绘图模块 |

### P1：Modbus 专业化 + 数据回放分析

| 顺序 | 功能 | 目标 | 完成标准 | 主要复用点 |
|---|---|---|---|---|
| P1-1 | DONE **多从机/多客户端模拟** | 模拟真实总线和网关场景 | 同一串口总线或 TCP 端口可配置多个从机；支持多个 TCP 客户端；从机地址、寄存器表和响应策略独立 | `modbus_slave.py`、`bridge.py`、设备中心 |
| P1-2 | DONE **Modbus 异常与动态数据模型** | 测试异常处理和设备状态变化 | 支持异常码注入；寄存器按递增、随机、正弦、上下限循环等方式变化；异常策略可保存到工程 | 从机 `_exec`、设备资源、工程模型 |
| P1-3 | DONE **补齐常用 Modbus 功能码** | 覆盖诊断和组合读写场景 | 优先 FC08、FC11、FC17、FC23；主机和从机行为、异常响应、超时均有单测 | `modbus_master/slave._exec`、`SUPPORTED_FUNCS` |
| P1-4 | DONE **仪表盘/图表持久化与 CSV 回放** | 关闭程序后可继续分析历史数据 | 工程保存图表布局、数据源和单位；CSV/结构化记录回放可驱动同一套图表；支持暂停、倍速、单步和进度定位 | `plot_dialog.py`、`dashboard_dialog.py`、`StructuredRecorder` |
| P1-5 | DONE **会话诊断与差异定位** | 从统计异常快速跳到原始帧 | 会话比较的方向 / 时间差绝对值筛选与 CSV/JSONL 导出已完成；`jump_to_session_time` 已接到波形图：双击曲线点按采样 wall 时间定位结构化记录（有回归测试）。状态栏 RX/TX 点击可跳到最近统计样本 wall 时间；会话比较双击行经 `wall_t0` 映射后 `jump_to_session_time`（旧 .ctrec 无锚点则 toast） | `rec_replay.py`、`rec_diff.py`、结构化记录 |

> **P1 收尾（v1.3.8–v1.3.9）已完成**：异常注入/动态寄存器/`server_id` 界面、主机 FC08、多从机行表 UI、tooltip 自动换行、波形/状态栏/会话比较 `jump_to_session_time`、数据区书签、ANSI 清屏清书签、重复从机地址拒绝。FC08 变长回环/切帧取舍仍见 `tests/test_modbus_slave.py` 中的对抗性测试备注。后续能力见 **P2**。


### v1.4：稳定性与易用性（当前推进）

> 目标不是加功能，而是「删复杂度、修细节、提稳定」。脚本、宏、虚拟连接、回放、仪表盘、
> Modbus 和自动化序列都已具备，功能面足够；v1.4 只做减法和打磨。

| 顺序 | 功能 | 目标 | 完成标准 |
|---|---|---|---|
| S-1 | **收敛静默异常** | 异常不再被无声吞掉，故障可追溯 | 逐模块收敛宽泛 `except` 与静默 `pass`；清理型代码改分步兜底，前一步失败不跳过后续步骤。当前 **235 处宽泛 `except`、其中 84 处静默 `pass`**（跑 `python scripts/count_exception_handling.py` 重算，别手数）。`net_io.py` 已完成（9 处静默归零，回归见 `tests/test_net_io_cleanup.py`），`bridge.py` 的网关 tick 同步改为记日志 + 一次性 `error_occurred`；`main_window.py`（146/68）、`serial_io.py`（12/6）待做 |
| S-2 | **拆分 `main_window.py`** | 12334 行、占 src 37865 行 33% 的巨类拆成可单测的服务层 | 按连接、数据区、发送、Modbus、序列分块外移，每块有独立测试；顺带满足 P2 的前置条件 |
| S-3 | **长时间运行与高频收发测试** | 把「稳定」变成可度量的 | 补 soak（持续运行）与吞吐压力用例，覆盖内存增长、缓冲上限、断线重连。当前 984 个用例全是短平快功能验证，无一条长跑 |
| S-4 | **日志按大小切分** | 长期监测不产生超大单文件 | `log_naming.py` 现只有按日轮转（`should_roll_date`），补按大小切分及两者组合 |
| S-5 | **错误提示与高频操作打磨** | 降低日常使用的心智负担 | 错误提示给出可操作建议而非原始 `errorString`；常用 Modbus 读写收敛成简化表单；补发送历史全文搜索 |

> 已具备、不要重复投入：连接预设与最近使用（`connection_presets.py`，含 `recent`/`last_used`）、
> 发送历史 FIFO 100 与上下键导航（`_send_hist`）、快捷发送栏（`_ms_quick_host`）、
> 片段库（`snippets.py`，带 filter）、日志按日轮转。

### P2：平台化能力（v1.4 起暂缓）

> 整体暂缓，不排期。暂缓不等于否定，而是前置条件尚未满足：
>
 > - 本节末验收要求第 1 条要求核心逻辑抽成 Qt-free 模块，而 `main_window.py` 现有 12334 行、
 >   占 src 全部 37865 行的 33%，内含 146 处宽泛异常捕获（68 处静默）。CLI 与 API 都要从这里
>   往外拆逻辑，插件式 dissector 还要等协议字段模型稳定之后才能定接口。
> - 在此前提下开 P2，等于在一个尚未解耦、异常路径不透明的核心上再架一层远程接口。
>
> 恢复排期的判据：S-2 拆分完成、S-1 异常收敛到位、S-3 有长跑与吞吐基线数据。

| 顺序 | 功能 | 状态 | 恢复排期的前置条件 |
|---|---|---|---|
| P2-1 | Headless / CLI | 暂缓 | 序列引擎、报告引擎与 GUI 解耦（S-2） |
| P2-2 | REST / WebSocket API | 暂缓 | CLI/API 共用同一套核心服务层（S-2） |
| P2-3 | 脚本化协议解析器/插件 | 暂缓 | 先稳定协议字段模型、变量上下文和资源包格式 |
| P2-4 | TCP/UDP 专用 PCAP 导出 | 保留候选 | 属导出格式而非平台化，不受本次收窄影响；仅对 TCP/UDP 提供，串口保留 `.ctrec` 语义 |

### 暂不纳入近期排期

- 不做完整 VT100 仿真、BLE/HID/CAN/SPI/I2C、虚拟串口驱动等偏离核心定位的能力。
- 不以“新增控件数量”为目标；图表先做双 Y 轴、XY、直方图、游标和统计，再考虑更多 gauge/LED。
- Excel/xlsx 后置，优先保证 HTML、CSV、JUnit XML 三种交付格式。
- 不支持“回放数据直接注入真实串口”作为默认能力，避免把历史 RX 数据误当成真实设备响应；如确有需要，单独设计明确的 TX 重放模式和安全确认。
- 触发联动发送（匹配后自动回发）仍不做，避免与自动应答引擎互斥打架（同第三节末「明确不建议借鉴」）。
- v1.4 起明确划出边界、不做：远程 API / CLI / 插件系统（见上）、窗口内多标签与拖拽窗口、
  云端与协作、AI 能力、更多冷门协议、复杂权限与操作员体系。

### Webhook / 外部程序提前落地的取舍

原计划把 Webhook 和外部程序排在 API/事件总线之后，实际在 v1.3.9 之后直接落到了触发器里。
理由和补偿措施记在这里，后续做事件总线时按此边界迁移：

1. 提前的理由：这两个动作不依赖总线的编排能力，只要「匹配到就发一次」；等总线会把告警链路
   压后一整个大版本。
2. 没有堆积互斥逻辑：两者都不占用统一占用表，不与脚本、序列、传输、回放和 Modbus 抢收发
   通道，因此不构成本节验收要求第 3 条所说的「第二套收发互斥机制」。
3. 失控防护：在途动作数上限 `_TRG_MAX_ACTIONS`（8），超出即丢弃并计数，避免冷却设成 0 时
   线程和子进程无限增长。
4. 权限边界：`import_config` / `_apply_loaded_settings` 检测到 `run_cmd` 或 `webhook_url` 时，
   走与脚本库、脚本应答同一套信任确认；用户拒绝则剥离这两类字段后再导入。
5. 迁移约定：事件总线落地后，触发器侧只保留「产生事件」，动作执行统一挪到总线消费端，
   并发上限和导入门禁一并移交。

### 每个功能的统一验收要求

1. 核心逻辑尽量抽成 Qt-free 模块，GUI 只负责配置和展示，后续可直接复用到 CLI。
2. 同步补齐三语文案、工程/设置兼容、异常路径和回归测试。
3. 不新增第二套收发任务互斥机制；所有脚本、序列、传输、回放和 Modbus 任务继续使用统一占用表。
4. 对涉及数据的功能，必须明确数据边界、文件大小上限、失败恢复和向后兼容策略。
5. 新增功能完成后，更新 `README.md`、三语使用说明和发布说明，不只修改 TODO。

### 市场对标依据

- [Serial Studio Help](https://serial-studio.com/help)：实时仪表盘、CSV 回放、数据变换、API 和 CLI。
- [Docklight Scripting](https://docklight.de/manual/docklightscripting-overview.html)：脚本、序列、TCP/UDP 和协议测试。
- [Modbus Studio Simulator](https://modbusstudio.com/manual/simulator/)：多客户端和设备模拟。
- [PlotJuggler](https://github.com/PlotJuggler/PlotJuggler)：布局保存、实时流、CSV 和时序分析。
- [Wireshark User’s Guide](https://www.wireshark.org/docs/wsug_html/)：pcapng 网络捕获和导入导出边界。

## 五、本轮已落地（备查，勿重复）

- **A** Modbus ASCII 模式 + RTU-over-TCP（TCP Client 上选 RTU 变体即 RTU-over-TCP）
- **B** 寄存器表 ↔ 波形图/仪表盘一键联动（右键菜单 + 随工程打包）
- **C** 数据区搜索（纯文本/正则/HEX + 大小写）、时间戳四格式（日期/时间/相对/Unix）、冻结显示；缓冲上限可配（`ed_max_lines`，本就有）
- 结构化记录 / 设备中心 两处"?"帮助按钮 + i18n 三语
- 修复：从机 variant 穿透规范化、ASCII 主机剥本地回显、ASCII 超时按 hex 编码估算、`_modbus_send`/`_mbm_timeout_ms` 按 variant 路由（不嗅探首字节，避开 RTU addr=58=`:` 误判）、ASCII 超时隔离 guard、ASCII feed 循环重同步、冻结不切断实时日志、右键作用于所点行、联动前 commit
- `tests/test_ansi_integration::test_survives_window_destroy_and_recreate` 在 offscreen 下挂的预存在 flake（closeEvent 弹模态框）已修

### v1.3.9 之后本轮落地

- **D** 寄存器显示格式与位域：u64/i64/f64、8 种字序、0/1 地址基、位域拆解、预警与报警阈值；设备中心补 4 列并随工程往返
- **E** Modbus 主机多视图分组轮询：分标签编辑、共用一套半双工引擎；提交时按全局下标就地合并，不打乱其他视图的规则顺序；标签顺序取自持久化的 `modbus_master_views`
- **F** FC22 掩码写（0x16）+ FC43/14 设备标识（0x2B/0x0E）：主机、从机、UI 与单测齐全
- **G** 触发动作链：Webhook / 外部程序 / 命中阈值（`min_hits`、`every_n`），带在途并发上限与配置导入门禁（取舍见第四节）
- **H** 真·Modbus TCP/RTU 网关（`modbus_gateway.py`）：TCP 流缓冲重组、请求排队（上限 32）、广播不等回包、超时回 MBAP 异常 0x0B、从机异常响应原样转发；`bridge.py` 挂 100ms 专用 tick 并双向记速。**默认行为**：Unit ID 原样透传（`unit_map` 留空）、从机超时 1s，这两项界面暂不开放，已写进网关开关的提示文字。**多客户端**：每个 TCP 客户端独立重组缓冲（上限 16 个），请求入队时记来源，响应经 `TcpReply(client, frame)` 定向回发起方；客户端断开时清掉它的缓冲与排队请求，在途请求的响应直接丢弃而不广播
- 修复：启动时 `QStackedLayout` 页面未挂父窗口导致的窗口闪现；`QComboBox` 弹出层取样式时的瞬时白框（`dialogs._style_one_combo_popup`）
- **I（v1.4 S-1 首块）** `net_io.py` 异常收敛：9 处静默 `except Exception: pass` 归零。清理动作改为分步兜底（`_safe`）——
  退组或 abort 失败不再连带跳过 `close`/`deleteLater`（原会泄漏 socket 且没退组），半帧污染的客户端先摘表再释放
  （原 abort 抛异常会把它留在客户端表里继续接收后续写入）；回归见 `tests/test_net_io_cleanup.py`
- **J** 发布前收尾三项：
  - 地址基与阈值接通到界面。设备中心地址列按 `display_address` 显示、存回时换算回 0 基（解码与匹配始终用协议地址）；
    `level` / `display_address` 进结构化记录与 CSV，记录表新增「级别」列；仪表盘按 `level` 着色（报警闪红、预警稳定琥珀色）
  - 退出回收外部程序子进程。`_trg_procs` 记住活动句柄，`_shutdown()` 统一终止；
    `run_cmd` 用 `shell=True`，句柄指向 shell 本身，只 terminate() 会漏掉孙进程，所以
    Windows 走 `taskkill /T`、POSIX 用 `start_new_session` 成组后 `killpg`
  - 关掉 Popen 与句柄登记之间的竞态。`_trg_stopping` 竖起后不再放行新动作，
    `_trg_launching` 记住在途的启动；登记排在释放占位之前，退出态下即使 Popen
    卡过 2s，句柄登记后也会由当前 worker 立即回收，不会漏进程
  - 外部动作失败改记 debug 日志；POSIX 进程组在 SIGTERM 后无条件补 SIGKILL，
    避免父 shell 先退、孙进程仍存活
  - 网关 tick 不再静默吞异常：记 debug 日志并发一次 `error_occurred`（tick 100ms 一次，用门閙避免刷屏，恢复后再故障会再报）

- **K** 外部审核收尾（发布前）：
  - `run_cmd` 占位符的值做 shell 转义。命令本体仍走 `shell=True`（用户要管道与重定向），但
    `{name}` / `{pattern}` 展开的值不再参与解析：POSIX 用 `shlex.quote`，Windows 加双引号并去掉 cmd.exe
    在引号内仍会展开的 `%` / `!`。堵的是「命令看着无害、name 里藏毒」：导入门禁只让人确认
    「这份配置含外部命令动作」，不会逐字段去读 name（非远程面：占位符取不到报文内容）
  - `SEND_NO_TARGET`（-1）不再报成「sent -1 of N bytes」：网关回包遇到对端已走直接丢，
    普通转发改报「no receiver connected」
  - 网关解析失败改用 `_gw_ok` 门闙并归 A 侧；原来蹭 `_send_ok_b`，会把后续真正的 B 侧发送失败静默掉
  - 仪表盘文本解析路径清掉寄存器留下的 `level`（否则同名通道值已正常、卡片还一直标红）
  - 测试可达性与确定性：`test_triggers.py` 的 `__main__` 块回到文件末尾（直接运行从 28 恢复到 30 条）；
    网关超时改用 `tick(now=)` 注入时间，`run_cmd` 并发上限用哨兵文件控制子进程寿命，
    两处不再依赖 sleep 里程（机器一卡 sleep 超调就会偶发失败）
  - 网关 `tick()` 补 6 条确定性用例：未到点不动 / 0x0B 定向回发起方 / 超时后释放总线发下一条 / 客户端已走不回包

> 本轮审核里有两条是误报，已写成用例钉住：`_gw_ok` 实际不可达（`_reset_stats()` 在 `start()` 里早于
> timer 启动，且 `_tick_gateway` 先看 `_active`），但仍在 `__init__` 补了一行；FC23 非法读数量不会崩轮询引擎，
> 建帧阶段就报 `ValueError: FC23 requires read/write fields` 并被那条规则的 try/except 收走，走不到算超时那一步。

- **L** 外部审核第二轮（中危 5 项）：
  - `TcpClientConn.close()` 在 connecting 阶段不再发 `state_changed(False)`。从未发过 True 却补一个
    False，会被主窗口读成「对端已断开」→ 弹提示并触发自动重连；`_on_conn_timeout` 早就避了这个坑
  - 删视图先确认。`_del_view` 会当场清空那些规则的分组并落盘、无 undo，而 + / - 相邻且只有
    28×28；确认文案告知受影响条数，并说明规则本身不删、只回默认视图
  - `atexit` 兵底。`closeEvent` 跑不到的路径（未捕获异常、`sys.exit`）也要收子进程；
    正常退出后 `unregister`，否则每开一个窗口就多拉着一个已销毁的窗口
  - `run_cmd` 等子进程加 30s 上限（`_TRG_CMD_TIMEOUT`）。挂死的命令原本会永久占着一个
    并发名额，`_TRG_MAX_ACTIONS` 个全卡住就等于这个功能废了；到点按整组收掉。
    代价是长命命令会被打断，但退出时这些子进程本来就一律回收，本身活不过 CommTool
  - 歧义交替分支的回溯。面上看是 `(a|ab){12,16}` 这类写法没拦，实际关键在 CPython 会把
    公共前缀提出来——歧义早就表现为「分支带空选项」且已在检测，只是它只在 `amplifies`
    成立时才查，而 `hi-lo` 小、`hi` 不超 100 的写法不算 amplifies。把累计上界并进 `amplifies`
    即可，不需另造一套判断；阀值 12 来自实测（`(\w|\w\w){k,k+5}$` 打 50 字符：上界
    10 约 0.003s、15 约 0.07s、20 约 1.6s、23 约 11s），首字符互斥的 `(ERR|WARN)` 不误伤

> 报告里给的 `(a|ab){2,10}c` 实测 0.000s，不算灾难性回溯：重复上界只有 10，搜索空间被夹住了。
> 真正能冻住 GUI 的是上界更大的同形写法，所以判据钉在累计上界而不是“带交替分支”。

测试基线：**984 passed, 3 skipped, 291 subtests**（3 个 skip 全是 POSIX-only 进程组用例；Qt 平台插件落到 offscreen 时另有 1 个排版用例会 skip）。
