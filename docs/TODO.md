# CommTool 开发待办与已知问题

> 本文件是 CommTool 的后续开发基线。后续新增功能、拆分任务和排期，优先以第四节「执行版路线图」为准；第三节仅作为市场对标后的备选功能池。
> 已落地的（Modbus ASCII、寄存器表↔绘图联动、搜索正则/HEX、时间戳多格式、冻结显示、结构化记录/设备中心帮助按钮等）不在未完成清单中。
> 产品定位：面向嵌入式研发、协议联调和产线验机的「通信协议测试工作台」，重点形成“设备预设 → 自动化测试 → 收发记录 → 失败定位 → 报告导出 → CLI/产线复用”的闭环。
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

- **书签 / 标记行跳转**（`Ctrl+F2` 加/清、`F2/Shift+F2` 跳转）
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
| ⭐ | **Modbus 网关（TCP↔RTU 路由）+ 多从机模拟** | 工业网关/ModRSsim2 | 测多设备总线、网关转发 | 中-高 | `bridge.py` 引擎 + `modbus_slave` 多实例字典 (当前单从机 `_ar_modbus.addr`) |
| ⭐ | **更多 Modbus 功能码（FC08诊断/FC11/FC17/FC23读写多）** | ModbusSimulator(14码) | 覆盖诊断与一次读写 | 中 | `modbus_master/slave._exec` / `SUPPORTED_FUNCS` |
| | 位域(bitfield)解析 | 嵌入式协议工具 | 寄存器内部按位拆 | 中 | `binproto.py` + `device_resources` 的 bit 扩展 |
| | 回放驱动真实 TX（不只注入虚拟连接） | IO Ninja | 录的帧从真实串口/网络发出去 | 中 | `rec_replay.Player` 注入路径加一条 TX 侧 |
| | 触发动作：webhook / 命中N次 / 运行外部程序 | Docklight action chain | 接运维/告警链路 | 中 | `_fire_trigger` (`main_window.py` ~5300) 扩动作集 |

### Tier 3 — 大工程/战略级（差异化壁垒，单独立项）

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
| P1-5 | DONE **会话诊断与差异定位** | 从统计异常快速跳到原始帧 | 会话比较的方向 / 时间差绝对值筛选与 CSV/JSONL 导出已完成；`jump_to_session_time` 已接到波形图：双击曲线点按采样 wall 时间定位结构化记录（有回归测试）。状态栏统计仍是聚合值、无时间轴；会话比较行时间与结构化记录不同源，不作为跳转入口 | `rec_replay.py`、`rec_diff.py`、结构化记录 |

> 待补（v1.3.7 已知缺口）：动态寄存器 / 异常注入模式·过滤 / 从机 ID 已在从机对话框提供界面；主机 FC08 数量列支持「子功能:数据」写法；多从机列表仍用 JSON。对话框的 Modbus 帮助文本与数量列 tooltip（`ar_modbus_help` / `mbm_qty_tip`）已补齐 FC08/11/17/23、多从机、异常注入与动态寄存器的说明并给出 JSON 例子，（多从机列表仍注明可写工程 JSON）；顶层 `server_id` 过去会被从机对话框的保存丢回默认值，已修复并加回归测试。另：FC08 的变长回环（子功能 0 回显 N×2 字节数据）已修好——切帧先按 8 字节试，CRC 不符再按偶数长度探测真实帧长，半包会等齐而不是退字节丢帧；回显也改成原样返回整个数据段（规范 6.8 要求响应与请求逐字节相同）。另外容错接收「只带子功能码、无数据段」的 6 字节请求：这不是规范形式（规范 6.8 给每个子功能都定了 2 字节请求数据段，0x0A–0x12 与 0x14 都是 `00 00`，合规帧就是 8 字节），但收到后回「非法值」异常总比静默丢弃好，单独到达、后面跟别的帧、以及乱码前缀后重同步三种情形都覆盖了。子功能 0 不走这条 6 字节兜底，否则可能把还在到达的长回环帧切成两半——有一条故意让前 6 字节 CRC 自洽的对抗性测试盯着。别把 `expected_len` 对 08 的返回值直接改成 6：那会让合规的 8 字节帧切错被吞、从机不再回异常，测试会红。还有一处是协议本身的二义性、不是缺陷：像 `01 08 00 00 00 01 21 CB CC DD 95 59` 这样第一个数据字恰好等于前 6 字节 CRC 的长回环帧，按 8 字节读和按 12 字节读都 CRC 自洽，RTU 没有 T3.5 静默就无从分辨。读法统一取较短的那个（与其余功能码一致）：反过来优先取长帧的话，一个 1/65536 的 CRC 巧合就会让普通 8 字节回环把后面那帧一起吞掉——丢一整条请求比回一个短回显严重得多。`test_crc_collision_prefix_reads_as_the_shorter_frame` 钉住了这个取舍。

> 待补（tooltip 换行）：Qt 只对「看起来像富文本」的 tooltip 自动换行，纯文本长串会渲染成超出屏幕的单行。全项目另有 16 条零换行的 `setToolTip` 长文案（最宽 `seq_extract_tip` 约 6273 px，其次 `mbm_echo_tip` 约 5321 px、`ar_gap_tip` 约 4199 px）；已加统一 `ui_tips.set_tooltip` 包装（转 HTML 让 Qt 自动换行），全项目 `setToolTip` 调用点与 `tr_tooltip` 刷新路径均已接入；`mbm_qty_tip` 仍自带换行。原建议（把 `\n` 转 `<br>` 并套 `<html>` 交给 Qt 自动换行），而不是逐条改三语译文。注意 `ar_modbus_hint` / `ar_test_hint` / `ms_hint` 虽然更长，但走的是带 `setWordWrap(True)` 的 QLabel，不受此影响。

### P2：平台化能力（单独立项）

| 顺序 | 功能 | 目标 | 前置条件 |
|---|---|---|---|
| P2-1 | **Headless / CLI** | 无界面运行序列、脚本、回放并输出 JUnit | 序列引擎、报告引擎与 GUI 解耦 |
| P2-2 | **REST / WebSocket API** | 让外部程序控制连接、收发、统计和测试 | CLI/API 共用同一套核心服务层 |
| P2-3 | **脚本化协议解析器/插件** | 支持用户自定义协议和字段解码 | 先稳定协议字段模型、变量上下文和资源包格式 |
| P2-4 | **TCP/UDP 专用 PCAP 导出** | 网络流量与 Wireshark 互通 | 仅对 TCP/UDP 提供；串口保留 `.ctrec` 语义 |

### 暂不纳入近期排期

- 不做完整 VT100 仿真、BLE/HID/CAN/SPI/I2C、虚拟串口驱动等偏离核心定位的能力。
- 不以“新增控件数量”为目标；图表先做双 Y 轴、XY、直方图、游标和统计，再考虑更多 gauge/LED。
- Excel/xlsx 后置，优先保证 HTML、CSV、JUnit XML 三种交付格式。
- 不支持“回放数据直接注入真实串口”作为默认能力，避免把历史 RX 数据误当成真实设备响应；如确有需要，单独设计明确的 TX 重放模式和安全确认。
- Webhook、外部程序和触发联动放到 API/事件总线之后，避免在现有触发器中继续堆积互斥逻辑。

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

测试基线：**877 passed, 4 skipped, 288 subtests**（4 个 skip 全是平台门控：3 个 POSIX-only 进程组用例 + 1 个 offscreen Qt 排版用例；带界面跑法下少 1 个 skip、多 1 个 pass）。
