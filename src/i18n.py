# -*- coding: utf-8 -*-
"""多语言文案 TR 与校验算法键 CHECKSUM_KEYS。"""


# ============== 翻译表 ==============
TR = {
    "zh": {
        "app_title": "通信调试工具",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "数据区",
        "legend_rx": "← 收",
        "legend_tx": "→ 发",
        "to_bottom": "↓ 最新",
        "hex_display": "HEX 显示",
        "encoding": "字符编码",
        "encoding_auto": "自动",
        "theme": "主题",
        # 主题名 — 国际通用术语（Solarized/Tango/Campbell/Ubuntu）保留原名，仅翻译 Light/Dark 后缀
        "theme_default": "默认",
        "theme_dark": "暗色",
        "theme_one_half_lt": "One Half 浅色",
        "theme_one_half_dk": "One Half 深色",
        "theme_solar_lt": "Solarized 浅色",
        "theme_solar_dk": "Solarized 深色",
        "theme_tango_dk": "Tango 深色",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "自动换行",
        "show_timestamp": "显示时间戳",
        "packet_split": "时间分包",
        "line_split": "换行分包",
        "nl_auto": "自动",
        "timeout": "超时",
        "real_time_log": "实时记录",
        "log_split_none": "不分包",
        "log_path_idle": "（未记录）",
        "log_split_tip": "实时记录按文件大小分包：写到设定大小就切到新文件(原名加 _001/_002…)。\n可手填自定义，如 3M / 500K；选「不分包」则单文件不限。",
        "max_lines": "最大行数",
        "save": "保存",
        "ctx_copy": "复制",
        "ctx_select_all": "全选",
        "clear": "清空",
        "font_dec": "字号减小",
        "font_inc": "字号增大",
        "conn_settings": "连接设置",
        "protocol_type": "类型",
        "port": "串口",
        "baud_rate": "波特率",
        "data_bits": "数据位",
        "parity": "校验位",
        "stop_bits": "停止位",
        "btn_serial_open": "打开串口",
        "btn_serial_close": "关闭串口",
        "no_ports": "无可用串口",
        "port_missing": "{port}（未检测到）",
        "serial_removed": "串口 {port} 已移除，连接已断开",
        "err_no_port": "请选择串口",
        "err_bad_baud": "波特率无效",
        "err_open_failed": "打开串口失败: {e}",
        "local_ip": "本地IP",
        "local_port": "本地端口",
        "remote_ip": "远程IP",
        "remote_port": "远程端口",
        "target_client": "目标",
        "client_all": "全部",
        "btn_listen": "开始监听",
        "btn_listen_stop": "停止监听",
        "btn_connect": "连接",
        "btn_disconnect": "断开",
        "btn_udp_open": "打开",
        "btn_udp_close": "关闭",
        "net_connecting": "● 连接中…",
        "net_listening": "● {proto} 监听 {addr}",
        "net_connected": "● 已连接 {addr}",
        "net_udp_bound": "● UDP {addr}",
        "err_bad_port": "端口号无效 (1-65535)",
        "err_bad_ip": "IP 地址无效",
        "err_listen_failed": "监听失败: {e}",
        "err_connect_failed": "连接失败: {e}",
        "err_bind_failed": "绑定失败: {e}",
        "err_conn_timeout": "连接超时",
        "err_serial_runtime": "串口连接已断开: {e}",
        "updater_no_source": "所有更新源都连不上",
        "updater_cancelled": "已取消",
        "updater_bad_installer": "下载内容不是有效安装包（可能是错误页面）",
        "updater_bad_url": "更新源地址不安全（仅允许 https）",
        "net_peer_closed": "对端已断开",
        "auto_reconnect_in": "将在 {sec}s 后自动重连…",
        "auto_reconnect_try": "尝试重连 #{n}…",
        "cfg_export": "导出配置…",
        "cfg_import": "导入配置…",
        "cfg_exported": "✓ 配置已成功导出到：{path}",
        "cfg_export_fail": "导出失败: {err}",
        "cfg_imported": "✓ 配置导入成功（{n} 项），主题/语言/规则已即时生效；当前已开的连接需手动重连",
        "cfg_import_fail": "导入失败: {err}",
        "net_no_target": "无可发送目标",
        "net_not_open": "未连接",
        "net_send_failed": "发送失败",
        "about": "关于",
        "help": "帮助",
        "about_desc": "iOS 风格的串口 / 网络调试工具（串口 + TCP/UDP）",
        "check_update": "检查更新",
        "update_checking": "正在检查…",
        "update_latest": "已是最新版本（v{ver}）",
        "update_found": "发现新版本 v{ver}",
        "update_download": "下载并更新",
        "update_downloading": "下载中 {pct}%",
        "update_failed": "检查更新失败：{e}",
        "update_dl_failed": "下载失败：{e}",
        "update_installing": "正在启动安装程序，即将退出…",
        "update_open_page": "已在浏览器打开下载页",
        "update_badge": "● 可更新 v{ver}",
        "update_badge_tip": "发现新版本 v{ver}，点击查看并更新",
        "auto_check_update": "自动检查更新",
        "search": "搜索",
        "search_ph": "搜索数据区…",
        "search_prev": "上一个",
        "search_next": "下一个",
        "search_no_match": "无匹配",
        "use_remote": "指定远程",
        "use_remote_tip": "开 = 固定发往下面的远程地址；关 = 回复最近发来数据的对端",
        "group_addr": "组播地址",
        "net_group_joined": "● 组播 {addr}",
        "err_not_multicast": "组播地址须在 224.0.0.0 ~ 239.255.255.255",
        "send_area": "发送区",
        "hex_send": "HEX 发送",
        "append_newline": "追加换行",
        "period": "定时",
        "checksum": "校验",
        "ck_none": "无",
        "ck_sum": "和校验",
        "ck_neg_sum": "累加和取反",
        "ck_xor": "异或",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "在这里输入要发送的内容...   HEX 示例: AA BB CC 01 02   动态字段: {count} {ts} {randN}",
        "send_box_tip": (
            "动态字段（发送时自动替换，HEX 模式输出 2 位十六进制）：\n"
            "  {count}  序号自增 1 字节，每次发 +1（0..FF 回绕）\n"
            "  {ts}     当前毫秒时间戳 4 字节（高位在前）\n"
            "  {rand}   随机 1 字节（= {rand1}）\n"
            "  {randN}  随机 N 字节，N=1..256（如 {rand4}、{rand16}）\n"
            "\n"
            "示例（HEX 模式）：在框里输入\n"
            "  54 {count} 00 03 FF\n"
            "第 1 次发实际发出：54 01 00 03 FF\n"
            "第 2 次：54 02 00 03 FF……\n"
            "\n"
            "发送命令历史（↑↓）：\n"
            "  光标在首行按 ↑ 取上一条发过的命令\n"
            "  光标在末行按 ↓ 往后翻 / 回到当前草稿"
        ),
        "multi_send": "多条发送",
        "multi_send_title": "多条发送",
        "ms_add": "＋ 添加一条",
        "ms_cycle": "▶ 循环",
        "ms_cycle_stop": "■ 停止",
        "ms_send_one": "发送",
        "ms_nl_none": "无",
        "ms_placeholder": "数据（HEX 或文本）",
        "ms_none_checked": "请先勾选要循环发送的条目",
        "ms_hint": "左侧管理分组；每行可独立设 名称 / 延时 / HEX / 换行 / 校验。勾选多条 → 循环发送：发完每条等其「延时」再发下一条，到底再从头。",
        "ms_name_ph": "名称",
        "ms_select_all": "全选",
        "ms_delay_tip": "延时(ms)：发完本条后等这么久再发下一条",
        "kw_highlight": "关键字高亮",
        "kw_title": "关键字高亮",
        "kw_add": "＋ 添加关键字",
        "kw_mode_bg": "背景",
        "kw_mode_fg": "文字",
        "kw_color": "选择高亮颜色",
        "kw_placeholder": "关键字（区分大小写）",
        "kw_hint": "数据区匹配到关键字就按设定颜色高亮（区分大小写）。每条可限定 收 / 发 / 收发。",
        "kw_scope_both": "收发",
        "kw_scope_rx": "收",
        "kw_scope_tx": "发",
        "filter_highlight": "只显高亮行",
        "kw_default_group": "默认",
        "kw_group_off": "（关闭）",
        "kw_group_label": "分组",
        "kw_new_group": "新建",
        "kw_rename_group": "重命名",
        "kw_del_group": "删除",
        "kw_group_name_prompt": "分组名称：",
        "kw_group_min": "至少保留一个分组",
        "kw_new_group_default": "新分组",
        "kw_group_tip": "双击分组名可改名",
        "read_file": "读取文件",
        "send_btn": "发  送",
        "state_closed": "● 未连接",
        "stat_pkt_unit": "包",
        "stat_reset": "重置统计",
        "stat_tip_rx": "接收 RX",
        "stat_tip_tx": "发送 TX",
        "stat_total": "总量",
        "stat_packets": "包数",
        "stat_rate": "当前速率",
        "stat_peak": "峰值速率",
        "stat_errors": "错误数",
        "ar_open": "自动应答",
        "ar_title": "自动应答",
        "ar_enable": "启用自动应答",
        "ar_add": "添加规则",
        "ar_help_btn": "使用说明",
        "ar_help_title": "自动应答 — 使用说明",
        "ar_match": "收到",
        "ar_reply": "回复",
        "ar_mode_contains": "包含",
        "ar_mode_equals": "相等",
        "ar_mode_prefix": "前缀",
        "ar_cooldown": "冷却",
        "ar_delay": "延时",
        "ar_gap": "整包超时",
        "ar_gap_tip": "整包：累积收到的字节、静默这么久(ms)视作一整帧再匹配(Modbus 等分帧)；0=每包即时。注意分帧在匹配前进行、整条串口共用，实际取所有启用规则中的最大值。",
        "ar_verify": "收包校验",
        "ar_verify_tip": "对收到的整帧做校验：尾部按所选算法校验通过才应答，不通过(坏帧)不回。选「无」=不校验。本设备=MOBUS。",
        "ar_match_ph": "匹配（HEX：?? 整字节、A?/?5 半字节、b:1xxxxxx1 位掩码 通配，如 54 ?? 03）",
        "ar_script_err": "⚠ 脚本错误：{e}",
        "ar_script_btn": "脚本",
        "ar_script_tip": "脚本应答：写一段 Python（def reply(frame, ctx)）动态生成应答，替代静态模板。空=不启用。",
        "ar_script_mode_tip": "脚本模式：此行由脚本生成应答，静态「回复 / 校验 / 校验段」已忽略",
        "ar_script_enable": "启用脚本",
        "ar_script_timeout": "脚本执行超时（>{s}s），疑似死循环或阻塞",
        "ar_script_title": "脚本应答 — 编辑",
        "ar_script_import_title": "导入配置 — 含脚本",
        "ar_script_import_warn": "此配置含 {n} 段脚本，导入后它们会在规则命中时执行 Python 代码。\n信任来源并导入脚本？（选「否」= 导入配置但清空脚本）",
        "ar_script_test_ph": "测试帧 HEX（如 AA 11 22 33）→ 跑脚本看应答",
        "ar_script_none": "（脚本返回不应答）",
        "ar_script_tmpl": "def reply(frame, ctx):\n    # frame: bytes（命中帧）；ctx: state/seq/hits + crc/crc16/sum8/xor8/hexbytes/tohex\n    # 返回 bytes / list[bytes] / str / None\n    return bytes([0x06]) + frame[1:3]\n",
        "ar_script_help": "<b>脚本应答</b>：定义 <code>reply(frame, ctx)</code>，命中时动态生成应答（替代静态回复模板；脚本拥有整帧、<b>不自动叠校验</b>，自己用 ctx 算）。返回 <code>bytes</code>=一帧 / <code>list[bytes]</code>=多帧 / <code>str</code>=文本 / <code>None</code>=不回。<br><b>ctx</b>：<code>.state</code> 当前状态 · <code>.seq</code> 自增序号 · <code>.hits</code> 命中数；<code>.crc(data, width=16, poly=0x1021, init=0, refin=False, refout=False, xorout=0, byteorder='big')</code> 通用可定制 CRC；便捷 <code>.crc16</code>(Modbus) / <code>.crc8</code> / <code>.sum8</code> / <code>.xor8</code>；<code>.hexbytes('AA BB')</code>→bytes · <code>.tohex(b)</code>→'AA BB'。<br>故障注入 + 延时仍生效。⚠ 脚本在本机执行 Python；导入他人配置中的脚本会先征求同意。",
        "ar_mask_help": "<b>匹配语法</b>（HEX 模式）<br>• <code>AB</code> 整字节精确　<code>??</code>/<code>XX</code> 整字节通配<br>• <code>A?</code> / <code>?5</code> 半字节通配（高 / 低 4 位，<code>X</code> 同 <code>?</code>）<br>• <code>b:1xxxxxx1</code> 位掩码（8 位 <code>0/1/x</code>，<code>x</code>=该位不关心）<br>• 混写：<code>AA b:1001xxxx ?5</code><br>• 字段级：<code>?? ?? ?? b:xxxxxxx1</code> + 模式「前缀」= 第 4 字节 bit0 须为 1",
        "ar_reply_ph": "应答（{r3}=第3字节 {r1+1}=加1 {r1^FF}=异或 {seq}=自增 {ts}=时间戳 | 分多帧）",
        "ar_btn_tip": "单击=打开配置，双击=切换开关",
        "ar_toast_on": "自动应答已开启",
        "ar_toast_off": "自动应答已关闭",
        "ar_cooldown_tip": "冷却(ms)：同一规则在此窗口内只响一次，防止匹配帧连续高频到达造成应答风暴。延时是 turnaround、冷却是限流，是两回事。",
        "ar_frame_on": "帧头+长度组帧",
        "ar_frame_hdr": "帧头",
        "ar_frame_off": "长度偏移",
        "ar_frame_width": "宽",
        "ar_frame_extra": "整帧=长度+",
        "ar_cs_btn": "校验段",
        "ar_hits": "命中 {n}",
        "ar_hits_tip": "命中次数（本次运行）：匹配 + 收包校验通过即 +1（含被冷却抑制的）。点「重置统计」清零。",
        "ar_test": "测试",
        "ar_reset_stats": "重置统计",
        "ar_test_title": "规则测试器（离线）",
        "ar_test_hint": "输入一帧 HEX，点「测试」→ 看命中哪条规则、会回什么（含占位符替换 + 校验段/尾部校验计算结果）。只预览、不发送、不计数。",
        "ar_test_ph": "输入一帧 HEX，如 01 06 12 34 56 78",
        "ar_test_run": "测试",
        "ar_test_bad_hex": "HEX 格式错误（需偶数个十六进制字符）。",
        "ar_test_no_match": "无规则命中。",
        "ar_delay_tip": "回复延时(ms)：固定如 100，或范围 100-300（每次随机抖动，模拟设备 turnaround）。",
        "ar_fault_on": "故障注入",
        "ar_fault_tip": "全局压测主机：对所有自动应答按概率制造故障（丢包=超时不回测重传、错CRC=末字节翻转测校验、错长度=砍末字节测分帧）。被注入的帧在数据区有标记。",
        "ar_fault_drop": "丢包",
        "ar_fault_badcrc": "错CRC",
        "ar_fault_badlen": "错长度",
        "ar_fault_badcrc_short": "错CRC",
        "ar_fault_badlen_short": "错长度",
        "ar_fault_note_drop": "⚠ 故障注入·丢包（未发送）",
        "ar_frame_desc": "有帧头+长度字段时勾选 → 按真实帧边界分帧，正确处理粘包/拆包",
        "ar_fault_desc": "勾选后按概率搞坏应答 → 压测主机的重传与容错",
        # C8 多步状态机
        "ar_sm_on": "状态机",
        "ar_sm_tip": "多步状态机：每条规则可设「仅在某状态应答」与「应答后跳转」，把多条规则串成按帧序列推进的握手/会话。关闭=忽略 状态/跳转（等于普通模式）。",
        "ar_sm_init": "初始状态",
        "ar_sm_init_ph": "如 S0，留空=空",
        "ar_sm_cur": "当前",
        "ar_sm_reset": "重置状态",
        "ar_sm_desc": "按收到的帧序列推进状态：规则可限「仅某状态」并「应答后跳转」",
        "ar_sm_empty": "(空)",
        "ar_when_ph": "仅状态",
        "ar_when_tip": "仅当『当前状态』等于这里(可逗号分隔多个，如 S1,S2)时，此规则才会命中应答。留空=任意状态(通配)。仅状态机开启时生效。",
        "ar_goto_ph": "→状态",
        "ar_goto_tip": "此规则应答发出后，把『当前状态』切到这里。留空=状态不变。仅状态机开启时生效。",
        "ar_test_state": "当前状态：{s}",
        "ar_test_goto": "应答后状态 → {s}",
        "ar_test_state_skip": "（状态机开：当前状态「{s}」下，此规则的「仅状态」不匹配 → 实际不会应答）",
        "ar_sm_help_title": "多步状态机 — 说明与例子",
        "ar_sm_help": "把多条规则串成<b>按帧序列推进</b>的状态机，用于握手/会话流程。<br>每条规则两个可选字段：<br>• <b>仅状态</b>：只有当『当前状态』等于它（可逗号分隔多个，如 <code>S1,S2</code>）时，这条规则才有资格命中。留空=任意状态（通配）。<br>• <b>跳转</b>：这条规则应答发出后，把『当前状态』切到它。留空=不变。<br><br><b>初始状态</b>：连接 / 重置时的状态（留空=空状态）。<b>当前状态</b>实时显示，可随时<b>重置</b>。规则仍是<b>首条命中即停</b>：同一状态下按从上到下第一条命中的来。<br><br><b>例（三步握手）</b>，初始 <code>S0</code>：<br>规则1 仅状态 <code>S0</code>、匹配 <code>AA 01</code> → 应答…、跳转 <code>S1</code><br>规则2 仅状态 <code>S1</code>、匹配 <code>AA 02</code> → 应答…、跳转 <code>S2</code><br>规则3 仅状态 <code>S2</code>、匹配 <code>AA 03</code> → 应答…、跳转 <code>S0</code><br>主机必须按 01→02→03 顺序握手，乱序帧不会命中。<br><b>通配技巧</b>：一条「仅状态留空、匹配 <code>RESET</code>、跳转 <code>S0</code>」的规则，可在任意状态把会话拉回起点。",
        # B4 Modbus RTU 从机
        "ar_modbus": "Modbus 从机",
        "ar_modbus_tip": "把程序当成一个 Modbus RTU 从机：地址匹配 + CRC 正确就按功能码(读 01/02/03/04、写 05/06/0F/10)从寄存器表自动应答主机。开启后规则/状态机让位。",
        "ar_modbus_title": "Modbus RTU 从机",
        "ar_modbus_hint": "开启后程序作为 Modbus RTU 从机：从机地址匹配 + CRC 正确就按功能码自动应答（读 线圈/离散/保持/输入，写 单个/多个，非法请求自动回异常）。下表配置各寄存器初值（未列地址默认 0）；主机的写会改运行态，断开/重连复位回初值。寄存器值可十进制或 0x 十六进制、逗号分隔连续填入；线圈/离散用 0/1。",
        "ar_modbus_on": "启用 Modbus 从机",
        "ar_modbus_active": "● Modbus 从机模式开启：下方规则 / 状态机 / 帧头组帧不参与（故障注入仍作用于 Modbus 响应）。点上方「Modbus 从机」可关闭。",
        "ar_modbus_addr": "从机地址",
        "ar_modbus_space": "空间",
        "ar_modbus_start": "起始地址",
        "ar_modbus_values": "值（逗号分隔，连续填入）",
        "ar_modbus_add": "添加行",
        "ar_mb_holding": "保持寄存器 4x",
        "ar_mb_input": "输入寄存器 3x",
        "ar_mb_coil": "线圈 0x",
        "ar_mb_discrete": "离散输入 1x",
        "ar_modbus_help_title": "Modbus 从机 — 说明与例子",
        "ar_modbus_help": "让程序模拟一个 <b>Modbus RTU 从机</b>设备。开启后，收到的帧按 Modbus RTU 解析，<b>从机地址匹配且 CRC 正确</b>就按功能码自动组装标准响应回发：<br>• 读：<code>01</code> 线圈 / <code>02</code> 离散输入 / <code>03</code> 保持寄存器 / <code>04</code> 输入寄存器<br>• 写：<code>05</code> 单线圈 / <code>06</code> 单寄存器 / <code>0F</code> 多线圈 / <code>10</code> 多寄存器<br>• 非法功能码 / 地址 / 数据 自动回<b>异常响应</b>（0x80|功能码 + 异常码）<br><br><b>寄存器表</b>：每行选「空间 + 起始地址 + 值」，值从起始地址起<b>连续填入</b>（逗号分隔）。寄存器值十进制或 <code>0x</code> 十六进制（0~65535）；线圈 / 离散用 <code>0/1</code>。未配置的地址默认 0。主机的写（05/06/0F/10）改<b>运行态</b>寄存器，断开 / 重连 / 关 Modbus 复位回这里的初值。<br><br><b>例</b>：空间「保持寄存器」、起始 <code>0</code>、值 <code>0x1234, 0x5678, 100</code> → 寄存器 0/1/2 = 0x1234 / 0x5678 / 100。主机发「读保持寄存器、起始 0、数量 2」→ 自动回 <code>01 03 04 12 34 56 78 …</code>。<br><b>注意</b>：开启 Modbus 从机后，普通应答规则与状态机不参与（整条引擎作为 Modbus 从机）；RTU 无帧头，本程序按「功能码长度 + CRC」切帧、跨包缓冲、CRC 错自动重同步。TCP 服务器模式会把响应精确发回请求客户端。",
        "ar_frame_help_title": "帧头+长度组帧 — 说明与例子",
        "ar_frame_help": "用于<b>有固定帧头 + 长度字段</b>的二进制协议：程序跨包缓冲收到的字节，按帧头定位、读长度字段算出整帧边界来切分，正确处理串口/TCP 的<b>粘包/拆包</b>（比「整包静默超时」更准、不引入延迟）。不勾选时按「每个接收块=一帧」或「静默超时」分帧。<br><br>各项：<br>• <b>帧头</b>：hex，如 <code>AA BB</code>，只认以它开头的帧<br>• <b>长度偏移</b>：长度字段在帧内的字节位置（0 基）<br>• <b>宽</b>：长度字段占几字节（1/2/4）<br>• <b>LE/BE</b>：长度字段的字节序（小端/大端）<br>• <b>整帧=长度+</b>：整帧总长 = 长度字段的值 + 这个固定开销（帧头/长度/校验等没算进长度字段的字节数）<br><br><b>例</b>：协议 <code>AA BB │ 长度(1B) │ 数据… │ 校验(1B)</code>，长度字段 = 数据字节数。<br>设：帧头 <code>AA BB</code>、长度偏移 <code>2</code>、宽 <code>1</code>、<code>LE</code>、整帧=长度+ <code>4</code>（=帧头2 + 长度1 + 校验1）。<br>收到 <code>AA BB 03 11 22 33 7E</code> → 长度=3 → 整帧=3+4=7 字节，正好切一帧；粘了下一帧也能正确切开。",
        "ar_fault_help_title": "故障注入 — 说明与例子",
        "ar_fault_help": "全局开关，<b>对所有自动应答</b>按概率制造故障，专门<b>压测主机</b>的重传与容错。每次发送前掷骰：<br><br>• <b>丢包%</b>：整条<b>不发</b>（=超时不回）→ 测主机的重传/补发逻辑<br>• <b>错CRC%</b>：把应答<b>末字节翻转</b>（^0xFF），校验必然不符 → 测主机是否丢弃坏帧<br>• <b>错长度%</b>：<b>砍掉末字节</b> → 测主机的长度/分帧容错<br>三者独立掷骰；丢包命中就不再判其余。被注入的帧在数据区有 <code>⚠ 故障注入·…</code> 标记。<br><br><b>例 1</b>（测重传）：你的设备「主机没收到应答会补发 3 次」。把<b>丢包</b>设 <code>30</code>、其余 <code>0</code> → 平均每 3 条丢 1 条，就能看到主机触发补发，验证重传是否正确。<br><b>例 2</b>（测坏帧处理）：<b>错CRC</b> 设 <code>20</code> → 看主机收到校验错的帧会不会丢弃并重试，而不是误用。",
        "ar_fault_note_corrupt": "⚠ 故障注入·{what}",
        "ar_test_matched": "命中规则 #{n}：",
        "ar_test_verify_fail": "（命中，但收包校验不通过 → 实际不会应答）",
        "ar_test_no_reply": "（无应答内容）",
        "ar_test_reply_bad": "（应答 HEX 解析失败）",
        "ar_cs_tip": "内层 / 额外校验：对应答帧的子段算校验、写到指定位置，在行尾「校验」之前按顺序计算（用于外层 Sum + 内层 CRC 这类两层校验）。",
        "ar_cs_title": "校验段（内层 / 额外校验）",
        "ar_cs_add": "添加段",
        "ar_cs_algo": "算法",
        "ar_cs_start": "起始",
        "ar_cs_end": "结束",
        "ar_cs_at": "填入位置",
        "ar_cs_help": "每段对应答帧 [起始..结束]（含端点）字节算校验、写到「填入位置」。\n• 顺序：从上到下（内层在前）；之后再加应答行尾的「校验」（外层）。\n• 填入位置留空 = 追加到帧尾；填数字 = 覆盖该偏移处的字节（应答里需先留好占位字节，如 00 00）。\n• 起始 / 结束 / 位置：0 基，负数从末尾（-1 = 最后一字节）；结束留空 = 到当前帧尾。\n例：应答 AA BB {r2} 06 12 34 00 00，加一段 ModbusCRC16 起始=2 结束=5 位置=6 → 把 CRC 覆盖到那两个 00；行尾「校验」选 ADD8 → 对整帧（含内层 CRC）求和追加。",
        "ar_frame_tip": (
            "勾选后按「帧头+长度字段」组帧（适合 AA BB… 这类带帧头+长度的协议），正确处理串口"
            "粘包/拆包；优先级高于各规则的「整包」静默超时。\n"
            "帧头=十六进制(如 AA BB)；长度偏移=长度字段相对帧头首字节的偏移；宽=长度字段字节数"
            "(1/2/4)；LE/BE=长度字段小端/大端；整帧=长度+N 表示整帧字节数=长度字段值+N(帧头/序号/"
            "校验等固定开销)。\n例(本设备)：帧头 AA BB · 长度偏移 4 · 宽 2 · LE · 整帧=长度+7。"),
        "ar_help": (
            "<b>用法</b>：收到数据按规则匹配 → 自动发应答。多条规则按顺序，命中第一条即停（一帧最多回一条）。仅在已连接 + 总开关开启时生效。<br>"
            "<b>匹配</b>：HEX/文本 × 包含/相等/<b>前缀</b>。HEX 模式 <code>??</code> 通配单字节（如 <code>54 ?? 03</code>）；更细粒度可用 <b>半字节</b> <code>A?</code>/<code>?5</code>（高/低 4 位）和 <b>位掩码</b> <code>b:1xxxxxx1</code>（8 位 <code>0/1/x</code>，<code>x</code>=该位不关心）。按帧首字节区分类型 <b>请用「前缀」别用「包含」</b>（避免别帧数据里同字节误命中）。<br>"
            "<b>应答占位符</b>（在「回复」框写）："
            "<code>{rN}</code>=收到帧第 N 字节(0基) &nbsp; "
            "<code>{rN-M}</code>=第 N..M 字节 &nbsp; "
            "<code>{rN+K}</code>=加 K(mod256) &nbsp; "
            "<code>{rN^K}</code>=XOR K &nbsp; "
            "<code>{seq}</code>=自增 1B &nbsp; "
            "<code>{ts}</code>=毫秒时间戳 4B BE。"
            "用 <code>|</code> 分多帧（如 <code>06 | 04 03 02 01</code> 先回 06、隔延时再回 04 03 02 01）。<br>"
            "<b>时序</b>：<b>整包超时</b>=静默 N ms 视作整帧再匹配（Modbus 分帧）；<b>延时</b>=匹配后等待 N ms 再回（从机 turnaround）；<b>冷却</b>=同一规则 N ms 内只响一次（防风暴）。<br>"
            "<br><b>例 1（MOBUS 设备，回包带回收到帧字节 + 自动补 CRC）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = 54     HEX ✓  模式=前缀   收校验 = MOBUS\n"
            "回复 = 03 {r2} {r1} 00   HEX ✓  校验 = MOBUS\n"
            "收: 54 03 01 02 ... CRC  →  回: 03 01 03 00 ... CRC（CRC 自动补）</pre>"
            "<b>例 2（心跳应答带本机序号 + 时间戳）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AA   HEX ✓  模式=相等\n"
            "回复 = 55 {ts} {seq}   HEX ✓\n"
            "收: AA  →  回: 55 F4 50 38 17 01（4B 时戳 + 自增序号）</pre>"
            "<b>例 3（HEX 通配 + 多帧 ACK+DATA）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = 54 ?? 03   模式=包含    回复 = 06 | 04 03 02 01    延时 = 10 ms\n"
            "任何形如 54 X 03 的帧都触发：先回 06，10ms 后再回 04 03 02 01</pre>"
            "<b>例 4（AT 命令 — 文本模式）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AT+VER?   文本（HEX 不勾）   模式=相等\n"
            "回复 = +VER:1.2.3\\r\\nOK\\r\\n   文本   校验=无\n"
            "收: AT+VER?  →  回: +VER:1.2.3&lt;CR&gt;&lt;LF&gt;OK&lt;CR&gt;&lt;LF&gt;</pre>"
            "<b>例 5（多规则按帧类型分流 — 命中即停）：</b>"
            "<pre style='margin:2px 0 2px 16px'>设备协议多种帧类型，每种一条规则按顺序排：\n"
            "  规则 1: 匹配 = 54   模式=前缀   →   回 03 {r2} {r1} 00   校验=MOBUS\n"
            "  规则 2: 匹配 = 02   模式=前缀   →   回 03 {r1} 00 00     校验=MOBUS\n"
            "  规则 3: 匹配 = 04   模式=前缀   →   回 03 {r1} {r2} {r3} 校验=MOBUS\n"
            "首字节决定走哪条；前缀模式按字节对齐，绝不会因别帧数据里含 02 误触发</pre>"
            "<b>例 6（字节范围 + 算术 + 限流，{r1-4} {r1+1} {r2^FF}）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AA   HEX ✓   模式=相等   冷却 = 200 ms\n"
            "回复 = {r1-4} {r1+1} {r2^FF}   HEX ✓\n"
            "收: AA 10 20 30 40 50  →  回: 10 20 30 40 50 11 DF\n"
            "  ({r1-4}=回填第1..4字节  {r1+1}=10+1=11  {r2^FF}=20 XOR FF = DF)\n"
            "即使设备 10ms 发一帧，每 200ms 才回一次（冷却把中间的吃掉）</pre>"
        ),
        "plot_open": "波形图",
        "plot_need_lib": "波形图需要 pyqtgraph 库：{e}",
        "plot_title": "数据波形图",
        "plot_help_btn": "使用说明",
        "plot_help_title": "数据波形图 — 使用说明",
        "plot_help": (
            "<b>用法</b>：从 RX 数据里解析数值，按通道实时绘曲线。三种解析模式按设备协议选——文本流走「分隔符/正则」，二进制 HEX 帧走「HEX 字节字段」。<br>"
            "<b>分隔符模式</b>：逐行按选定分隔符切，每列 = 一条曲线。<br>"
            "<b>正则模式</b>：每行用正则匹配，每个 <b>捕获组</b> = 一条曲线（非捕获组用 <code>(?:…)</code>）。<br>"
            "<b>HEX 字节字段模式</b>：把每个收到包视作一帧（按数据区「时间分包」切），按「<code>名称=偏移:类型</code>」从指定偏移取数。可选「帧头」过滤：填 hex 帧头只解析以它开头的帧。<br>"
            "<br><b>例 1（分隔符模式 — CSV 文本流）：</b>"
            "<pre style='margin:2px 0 2px 16px'>设备输出：<code>1.23,4.56,7.89\\n2.34,5.67,8.90\\n…</code>\n"
            "模式 = 分隔符   分隔符 = 逗号\n"
            "→ 3 条曲线（CH0/CH1/CH2），每行一组采样</pre>"
            "<b>例 2（正则模式 — 带标签的文本）：</b>"
            "<pre style='margin:2px 0 2px 16px'>设备输出：<code>T=23.4 H=56.7 P=1013\\n</code>\n"
            "模式 = 正则   正则 = <code>T=([\\d.]+)\\s+H=([\\d.]+)\\s+P=([\\d.]+)</code>\n"
            "→ 3 条曲线（温度/湿度/气压），分别取 3 个捕获组的数</pre>"
            "<b>例 3（HEX 字节字段 — 二进制协议）：</b>"
            "<pre style='margin:2px 0 2px 16px'>设备每帧：<code>54 00 0A 04 7F …</code>（4 字节 i16le 后跟 i16le）\n"
            "模式 = HEX 字节字段   字段 = <code>X=1:i16le, Y=3:i16le</code>\n"
            "收: 54 00 0A 04 7F → X=0x0A00=2560 (le)  Y=0x047F=1151\n"
            "→ 2 条曲线（X/Y），按帧绘点</pre>"
            "<b>例 4（HEX 模式 + 帧头过滤 — 多帧类型只画一类）：</b>"
            "<pre style='margin:2px 0 2px 16px'>设备混发多种帧（54 类、02 类、04 类），只想看 54 类：\n"
            "模式 = HEX 字节字段   <b>帧头 = 54</b>   字段 = <code>X=1:i16le, Y=3:i16le</code>\n"
            "其它帧（02xx…/04xx…）被过滤掉，只解析 54 开头的</pre>"
            "<b>例 5（浮点数据 — 加速度计/陀螺仪等）：</b>"
            "<pre style='margin:2px 0 2px 16px'>每帧 12 字节：3 个 f32le 浮点（X/Y/Z 加速度）\n"
            "模式 = HEX 字节字段   字段 = <code>aX=0:f32le, aY=4:f32le, aZ=8:f32le</code>\n"
            "→ 3 条加速度曲线，每帧一个采样点</pre>"
            "<br><b>X 轴</b>可切「样本序号」或「时间」；<b>窗口</b>下拉控制最多保留点数（超出滚动丢弃，长跑不爆内存）；右上角<b>暂停/清空/导出 CSV</b>。<br>"
            "<b>⚠️ HEX 字节字段模式按接收块分帧</b>（一块=一帧，不拆粘包）。串口/TCP 请配合数据区<b>「时间分包」</b>让每帧单独成块。"
        ),
        "plot_mode": "解析",
        "plot_mode_delim": "分隔符",
        "plot_mode_regex": "正则",
        "plot_mode_hex": "HEX 字节",
        "plot_fields_ph": "二进制字段 偏移:类型，如 3:u8, 9:i16le（每包当一帧）",
        "plot_fields_bad": "字段格式错误，应为 偏移:类型，如 3:u8,9:i16le",
        "plot_header_ph": "帧头 hex 可空，如 54",
        "plot_header_bad": "帧头需为 hex，如 54 或 5400",
        "frame_open": "帧解析",
        "mbm_open": "Modbus 主机",
        "mbm_title": "Modbus 主机轮询",
        "mbm_enable": "启用轮询",
        "mbm_variant": "传输",
        "mbm_variant_auto": "自动(按连接)",
        "mbm_echo": "本地回显",
        "mbm_echo_tip": "串口适配器会回显发出的帧时勾选（RS-485 半双工常见）。开启后先剥掉一份与请求相同的回显再解析真实响应——尤其写功能码 05/06 的回显与「写成功」同形，不开会把回显当成功、丢掉从机的异常。",
        "mbm_variant_rtu": "Modbus RTU",
        "mbm_variant_tcp": "Modbus TCP",
        "mbm_apply": "应用",
        "mbm_apply_first": "请先应用待生效的轮询规则",
        "mbm_reconnect_first": "连接参数已变化或当前连接不支持轮询，请先重连串口或 TCP Client",
        "mbm_add": "添加",
        "mbm_help_btn": "使用说明",
        "mbm_hint": "按每行周期轮询从机：串口走 Modbus RTU、TCP Client 走 Modbus TCP。编辑规则后必须点「应用」才会生效；写功能不会因编辑自动发送。",
        "mbm_col_name": "名称",
        "mbm_col_unit": "从机ID",
        "mbm_col_func": "功能码",
        "mbm_col_addr": "起始地址",
        "mbm_col_qty": "数量/写值",
        "mbm_qty_tip": "读类填数量；写单 05/06 填一个值；写多 0F/10 填多个值，逗号或空格分隔，如 100,200,300（0F 线圈填 0/1）。",
        "mbm_col_period": "周期ms",
        "mbm_col_value": "值",
        "mbm_col_status": "状态",
        "mbm_f1": "01 读线圈",
        "mbm_f2": "02 读离散输入",
        "mbm_f3": "03 读保持寄存器",
        "mbm_f4": "04 读输入寄存器",
        "mbm_f5": "05 写单线圈",
        "mbm_f6": "06 写单寄存器",
        "mbm_f7": "0F 写多线圈",
        "mbm_f8": "10 写多寄存器",
        "mbm_st_ok": "OK",
        "mbm_st_timeout": "超时",
        "mbm_st_senderr": "发送失败",
        "mbm_st_exc": "异常 {code}",
        "mbm_st_written": "已写 [{addr}]={val}",
        "mbm_st_written_multi": "已写 [{addr}] ×{n}",
        "mbm_st_badresp": "响应无效",
        "mbm_st_noval": "写值为空/非法",
        "mbm_st_badparam": "从机ID/地址/数量/周期无效",
        "mbm_st_pending": "待应用",
        "mbm_st_broadcast": "广播已发送（无响应）",
        "mbm_st_broadcast_read": "广播地址不支持读操作",
        "mbm_help_title": "Modbus 主机轮询 — 说明",
        "mbm_help": "Modbus 主机轮询：把本工具当 Modbus 主机，按每行设定的周期轮询从机并实时显示结果。\n\n• 传输：自动=串口→RTU、TCP Client→Modbus TCP；也可强制选择。\n• 功能码 01-04 为读：「数量」是寄存器/线圈个数，结果显示十进制+十六进制。\n• 功能码 05/06 为写：「数量/写值」格填写入值（05 写线圈填 0/1），周期到点重复写并显示回显。\n• 功能码 0F/10 为写多：「数量/写值」格填多个值，逗号或空格分隔，如 100,200,300（0F 线圈填 0/1）；数量由值的个数决定，任一值非法则整行不发送。\n• 半双工：一次只在途一条请求，收到响应或超时后再发下一条；串口超时按帧长和波特率动态计算。\n• 状态：OK / 超时 / 异常(从机返回的异常码) / 发送失败 / 响应无效。\n• 本地回显：串口适配器若回显发出的帧(RS-485 半双工常见)，勾选「本地回显」——尤其写 05/06 的回显与「写成功」同形，不开会把回显当成功、丢掉从机异常。\n\n用法：先在主界面连接(串口或 TCP Client)，添加规则，勾选上方「启用轮询」即开始。\n注意：不要同时开启「自动应答 · Modbus 从机」——一个收请求、一个发请求，混用会互相干扰。",
        "frame_title": "协议帧解析",
        "frame_hdr": "帧头",
        "frame_fld": "字段",
        "frame_fields_ph": "名称=偏移:类型，如 温度=9:i16le, 状态=15:u8（支持 hexN/strN）",
        "frame_col_time": "时间",
        "frame_col_raw": "原始帧",
        "frame_col_rule": "规则",
        "frame_col_fields": "字段",
        "frame_rules": "解析规则",
        "frame_add_rule": "添加规则",
        "frame_help_btn": "使用说明",
        "frame_help_title": "协议帧解析 — 使用说明",
        "frame_help": (
            "<b>用法</b>：填好「帧头 + 字段」规则后点「应用」。收到的每个数据块按帧头前缀匹配规则解析，命中第一条即停。<br>"
            "<b>规则字段</b>：<br>"
            "&nbsp;&nbsp;<b>帧头</b>：hex 串如 <code>02</code>；留空 = 兜底匹配前面规则未命中的帧<br>"
            "&nbsp;&nbsp;<b>字段定义</b>：<code>名称=偏移:类型</code> 多个用逗号分隔，偏移从 0 数起<br>"
            "<b>类型表</b>：<br>"
            "&nbsp;&nbsp;数值：<code>u8 i8 u16le u16be i16le i16be u32le u32be i32le i32be f32le f32be f64le f64be</code><br>"
            "&nbsp;&nbsp;数值后加 <code>x</code> = HEX 显示（如 <code>u8x</code> 显示 0x1F 而不是 31）<br>"
            "&nbsp;&nbsp;<code>hexN</code> = N 字节原始 HEX 串；<code>strN</code> = N 字节 ASCII 文本<br>"
            "<br><b>例 1（最简单 — 单字节字段）：</b>"
            "<pre style='margin:2px 0 2px 16px'>帧头 = 02   字段 = 序号=1:u8, 长度=2:u8, 类型=3:u8\n"
            "收: 02 0A 04 7F → 序号=10  长度=4  类型=127</pre>"
            "<b>例 2（多字节数值，含端序）：</b>"
            "<pre style='margin:2px 0 2px 16px'>帧头 = 54   字段 = ID=1:u16le, 温度=3:i16le, 时间=5:u32be\n"
            "收: 54 34 12 5C FF 00 00 04 D2 → ID=0x1234=4660  温度=-164  时间=1234</pre>"
            "<b>例 3（HEX 显示 + 原始字节）：</b>"
            "<pre style='margin:2px 0 2px 16px'>帧头 = AA   字段 = 状态=1:u8x, MAC=2:hex6, 名称=8:str8\n"
            "收: AA 1F 00 11 22 33 44 55 CommTool → 状态=0x1F  MAC=00 11 22 33 44 55  名称=CommTool</pre>"
            "<b>例 4（HEX 数值，便于按位看寄存器）：</b>"
            "<pre style='margin:2px 0 2px 16px'>帧头 = 06   字段 = 状态=1:u8x, 故障=2:u16lex\n"
            "收: 06 80 34 12 → 状态=0x80  故障=0x1234</pre>"
            "<b>例 5（多规则按帧头分流 — 命中即停）：</b>"
            "<pre style='margin:2px 0 2px 16px'>规则 1: 帧头=54  字段=序号=1:u8, 类型=2:u8\n"
            "规则 2: 帧头=02  字段=应答=1:u8\n"
            "规则 3: 帧头=（空） 字段=类型=0:u8x          ← 兜底\n"
            "首字节决定走哪条；54/02 分别有专属解析，其它帧走兜底规则</pre>"
            "<br><b>⚠️ 按接收块分帧</b>：一个数据块 = 一帧，不做跨块粘包拆分（半帧会缺字段、粘连帧只解析第一帧、帧头不在块首则整帧丢弃）。串口/TCP 请在<b>数据区开启「时间分包」</b>，让每帧单独成块。"
        ),
        "frame_rules_ph": "每行一条：帧头 | 字段。例： 02 | 序号L=1:u8, 序号H=3:u8x",
        "frame_apply": "应用",
        "frame_tab_all": "全部",
        "frame_rule_bad": "规则格式错误：{line}",
        "frame_export_title": "导出帧数据",
        "frame_hint": "每行一条规则「帧头 | 字段」，每帧按帧头前缀匹配第一条规则解析（帧头可空=兜底）。改完点「应用」。「全部」标签按时间看混合帧流，其余每规则一个分列表。数值后加 x=十六进制；支持 hexN/strN；原始帧列便于核实。",
        "plot_sep_comma": "逗号 ,",
        "plot_sep_space": "空白",
        "plot_sep_tab": "Tab",
        "plot_sep_semicolon": "分号 ;",
        "plot_sep_auto": "自动",
        "plot_regex_ph": "捕获组=通道，如 temp=(\\d+).*hum=(\\d+)",
        "plot_regex_bad": "正则表达式无效",
        "plot_window": "窗口点数",
        "plot_xaxis": "X 轴",
        "plot_x_index": "样本序号",
        "plot_x_time": "时间(s)",
        "plot_pause": "暂停",
        "plot_resume": "继续",
        "plot_clear": "清空",
        "plot_export": "导出 CSV",
        "plot_export_title": "导出波形数据",
        "plot_no_data": "暂无数据可导出",
        "plot_hint": "逐行解析 RX 文本里的数值：分隔符模式每列一条曲线，正则模式每个捕获组一条曲线；绘图 1Hz 之上 ~30FPS 刷新，不随收包频率。\n⚠️ HEX 字节字段模式按接收块分帧（一块=一帧，不拆粘包），串口/TCP 请配合数据区「时间分包」。",
        "dlg_save_data": "保存接收数据",
        "dlg_log_path": "选择日志保存路径",
        "dlg_load_file": "读取发送内容",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== 日志开始 {time} ==========\n",
        "log_footer": "\n========== 日志结束 {time} ==========\n",
        "log_started": "实时记录已开启",
        "log_stopped": "实时记录已停止",
        "saved_to": "已保存到 {path}",
        "err_hex_odd": "HEX 长度必须为偶数",
        "err_hex_bad": "HEX 格式错误: {e}",
        "err_hex_invalid_chars": "非法字符 {chars}",
        "err_send_failed": "发送失败: {e}",
        "err_checksum": "校验计算失败: {e}",
        "err_save_failed": "保存失败: {e}",
        "err_read_failed": "读取失败: {e}",
        "err_period_bad": "周期错误: {e}",
        "err_min_period": "周期最小 10ms",
        "err_open_log": "打开失败: {e}",
        "err_log_write": "写日志失败: {e}",
        "err_rx": "接收处理出错: {e}",
        "font_size_msg": "字号: {size} pt",
        "close_prompt": "你想怎么关闭程序？",
        "close_minimize": "最小化到托盘",
        "close_quit": "退出程序",
        "close_cancel": "取消",
        "tray_show": "显示窗口",
        "tray_quit": "退出",
        "tray_minimized": "{app} 已最小化到系统托盘",
        # —— 鼠标悬停说明 ——
        "hex_display_tip": "勾选后数据按 16 进制显示\n关闭：按文本/ASCII 显示",
        "encoding_tip": "字符编码（影响 RX 解码 / TX 编码 / 文件加载）\n自动：UTF-8 优先，乱码自动回退 GBK\n指定 UTF-8/GBK/GB2312/Big5 等则严格按选定编码",
        "theme_tip": "数据区配色方案（终端风格）\n切换后历史也会一并重涂为新主题色\n想全部刷新点「清空」即可",
        "auto_wrap_tip": "行太长自动折行\n关闭：超出宽度需横向滚动查看",
        "show_timestamp_tip": "每个数据块前显示 [年/月/日 时:分:秒 毫秒] 时间戳和 ←/→ 收发方向箭头",
        "packet_split_tip": "收到数据后超过下方「超时」时间无新数据就开新行\n用于把短时间到达的连续数据合并显示",
        "timeout_tip": "时间分包的间隔阈值（毫秒）\n两次接收间隔超过此值就开新行",
        "line_split_tip": "按换行符自动分行显示\n可选自动识别 / CRLF / LF / CR",
        "real_time_log_tip": "收发数据实时追加保存到日志文件\n显示什么就记什么(含时间戳/箭头/HEX)，关闭后停止写入",
        "max_lines_tip": "数据区最多保留的行数\n超出会丢弃最早的（防止内存涨爆）",
        "hex_send_tip": "把输入框的 16 进制字符串按字节发送（如 AA BB CC）\n关闭：按文本原样发送",
        "append_newline_tip": "每次发送后自动追加换行符\n可选 CRLF / LF / CR",
        "period_tip": "按右侧间隔（毫秒）周期性自动发送当前内容",
        "checksum_tip": "发送前在末尾追加校验字节\n支持 和校验/CRC8/MOBUS/CRC16/CRC32 等多种算法",
    },
    "en": {
        "app_title": "CommTool",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "Data",
        "legend_rx": "← RX",
        "legend_tx": "→ TX",
        "to_bottom": "↓ Latest",
        "hex_display": "HEX View",
        "encoding": "Encoding",
        "encoding_auto": "Auto",
        "theme": "Theme",
        # English: keep original recognized theme names
        "theme_default": "Default",
        "theme_dark": "Dark",
        "theme_one_half_lt": "One Half Light",
        "theme_one_half_dk": "One Half Dark",
        "theme_solar_lt": "Solarized Light",
        "theme_solar_dk": "Solarized Dark",
        "theme_tango_dk": "Tango Dark",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "Word Wrap",
        "show_timestamp": "Timestamp",
        "packet_split": "Packet Split",
        "line_split": "Line Split",
        "nl_auto": "Auto",
        "timeout": "Timeout",
        "real_time_log": "Log to File",
        "log_split_none": "No split",
        "log_path_idle": "(not logging)",
        "log_split_tip": "Split the log file by size: when it reaches the set size, a new file is started (original name + _001/_002…).\nType a custom value like 3M / 500K; pick \"No split\" for a single unbounded file.",
        "max_lines": "Max Lines",
        "save": "Save",
        "ctx_copy": "Copy",
        "ctx_select_all": "Select All",
        "clear": "Clear",
        "font_dec": "Decrease Font",
        "font_inc": "Increase Font",
        "conn_settings": "Connection",
        "protocol_type": "Type",
        "port": "Port",
        "baud_rate": "Baud",
        "data_bits": "Data Bits",
        "parity": "Parity",
        "stop_bits": "Stop Bits",
        "btn_serial_open": "Open",
        "btn_serial_close": "Close",
        "no_ports": "No ports",
        "port_missing": "{port} (not detected)",
        "serial_removed": "Serial port {port} removed — disconnected",
        "err_no_port": "Select a port",
        "err_bad_baud": "Invalid baud rate",
        "err_open_failed": "Open failed: {e}",
        "local_ip": "Local IP",
        "local_port": "Local Port",
        "remote_ip": "Remote IP",
        "remote_port": "Remote Port",
        "target_client": "Target",
        "client_all": "All",
        "btn_listen": "Listen",
        "btn_listen_stop": "Stop",
        "btn_connect": "Connect",
        "btn_disconnect": "Disconnect",
        "btn_udp_open": "Open",
        "btn_udp_close": "Close",
        "net_connecting": "● Connecting…",
        "net_listening": "● {proto} listening {addr}",
        "net_connected": "● Connected {addr}",
        "net_udp_bound": "● UDP {addr}",
        "err_bad_port": "Invalid port (1-65535)",
        "err_bad_ip": "Invalid IP address",
        "err_listen_failed": "Listen failed: {e}",
        "err_connect_failed": "Connect failed: {e}",
        "err_bind_failed": "Bind failed: {e}",
        "err_conn_timeout": "Connection timed out",
        "err_serial_runtime": "Serial connection lost: {e}",
        "updater_no_source": "Cannot reach any update source",
        "updater_cancelled": "Cancelled",
        "updater_bad_installer": "Downloaded file is not a valid installer (maybe an error page)",
        "updater_bad_url": "Unsafe update URL (https only)",
        "net_peer_closed": "Peer disconnected",
        "auto_reconnect_in": "Auto-reconnect in {sec}s…",
        "auto_reconnect_try": "Reconnect attempt #{n}…",
        "cfg_export": "Export config…",
        "cfg_import": "Import config…",
        "cfg_exported": "✓ Config exported successfully to: {path}",
        "cfg_export_fail": "Export failed: {err}",
        "cfg_imported": "✓ Config imported ({n} keys); theme/language/rules applied; reconnect manually if a connection is currently open",
        "cfg_import_fail": "Import failed: {err}",
        "net_no_target": "No send target",
        "net_not_open": "Not connected",
        "net_send_failed": "Send failed",
        "about": "About",
        "help": "Help",
        "about_desc": "An iOS-style serial & network debugging tool (Serial + TCP/UDP)",
        "check_update": "Check for Updates",
        "update_checking": "Checking…",
        "update_latest": "You're on the latest version (v{ver})",
        "update_found": "New version v{ver} available",
        "update_download": "Download & Update",
        "update_downloading": "Downloading {pct}%",
        "update_failed": "Update check failed: {e}",
        "update_dl_failed": "Download failed: {e}",
        "update_installing": "Launching installer, quitting…",
        "update_open_page": "Opened the download page in your browser",
        "update_badge": "● Update v{ver}",
        "update_badge_tip": "New version v{ver} available — click to view and update",
        "auto_check_update": "Auto-check for updates",
        "search": "Search",
        "search_ph": "Search…",
        "search_prev": "Previous",
        "search_next": "Next",
        "search_no_match": "No match",
        "use_remote": "Use remote",
        "use_remote_tip": "On = always send to the remote below; Off = reply to the last sender",
        "group_addr": "Group Addr",
        "net_group_joined": "● Multicast {addr}",
        "err_not_multicast": "Group address must be in 224.0.0.0 ~ 239.255.255.255",
        "send_area": "Send",
        "hex_send": "HEX Send",
        "append_newline": "Append CRLF",
        "period": "Auto",
        "checksum": "Checksum",
        "ck_none": "None",
        "ck_sum": "ADD8",
        "ck_neg_sum": "~ADD8",
        "ck_xor": "XOR8",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "Type data to send...   HEX example: AA BB CC 01 02   Dynamic fields: {count} {ts} {randN}",
        "send_box_tip": (
            "Dynamic fields (auto-replaced on send; HEX mode outputs 2-digit hex):\n"
            "  {count}  auto-increment counter, 1 byte, +1 per send (0..FF wraps)\n"
            "  {ts}     current ms timestamp, 4 bytes (big-endian)\n"
            "  {rand}   1 random byte (= {rand1})\n"
            "  {randN}  N random bytes, N=1..256 (e.g. {rand4}, {rand16})\n"
            "\n"
            "Example (HEX mode): type in box\n"
            "  54 {count} 00 03 FF\n"
            "1st send produces: 54 01 00 03 FF\n"
            "2nd: 54 02 00 03 FF, etc.\n"
            "\n"
            "Send history (Up/Down):\n"
            "  Up at first line  -> previous sent command\n"
            "  Down at last line -> next command / back to draft"
        ),
        "multi_send": "Multi-Send",
        "multi_send_title": "Multi-Send",
        "ms_add": "＋ Add Row",
        "ms_cycle": "▶ Cycle",
        "ms_cycle_stop": "■ Stop",
        "ms_send_one": "Send",
        "ms_nl_none": "None",
        "ms_placeholder": "Data (HEX or text)",
        "ms_none_checked": "Check at least one item to cycle-send",
        "ms_hint": "Manage groups on the left; each row has its own name / delay / HEX / newline / checksum. Check items → Cycle Send: after each command waits its delay, then loops.",
        "ms_name_ph": "Name",
        "ms_select_all": "Select all",
        "ms_delay_tip": "Delay (ms): wait this long after this command before the next",
        "kw_highlight": "Highlight",
        "kw_title": "Keyword Highlight",
        "kw_add": "＋ Add Keyword",
        "kw_mode_bg": "Background",
        "kw_mode_fg": "Text",
        "kw_color": "Pick highlight color",
        "kw_placeholder": "Keyword (case-sensitive)",
        "kw_hint": "Matching text in the data area is highlighted (case-sensitive). Each rule can target RX / TX / both.",
        "kw_scope_both": "RX+TX",
        "kw_scope_rx": "RX",
        "kw_scope_tx": "TX",
        "filter_highlight": "Matches only",
        "kw_default_group": "Default",
        "kw_group_off": "(Off)",
        "kw_group_label": "Group",
        "kw_new_group": "New",
        "kw_rename_group": "Rename",
        "kw_del_group": "Delete",
        "kw_group_name_prompt": "Group name:",
        "kw_group_min": "Keep at least one group",
        "kw_new_group_default": "New Group",
        "kw_group_tip": "Double-click a group to rename",
        "read_file": "Load File",
        "send_btn": "Send",
        "state_closed": "● Disconnected",
        "stat_pkt_unit": "pkt",
        "stat_reset": "Reset Statistics",
        "stat_tip_rx": "Received (RX)",
        "stat_tip_tx": "Sent (TX)",
        "stat_total": "Total",
        "stat_packets": "Packets",
        "stat_rate": "Current rate",
        "stat_peak": "Peak rate",
        "stat_errors": "Errors",
        "ar_open": "Auto-reply",
        "ar_title": "Auto-reply",
        "ar_enable": "Enable auto-reply",
        "ar_add": "Add rule",
        "ar_help_btn": "Help",
        "ar_help_title": "Auto-reply — Help",
        "ar_match": "On",
        "ar_reply": "Reply",
        "ar_mode_contains": "contains",
        "ar_mode_equals": "equals",
        "ar_mode_prefix": "prefix",
        "ar_cooldown": "Cooldown",
        "ar_delay": "Delay",
        "ar_gap": "Frame gap",
        "ar_gap_tip": "Frame gap: buffer bytes and treat them as one frame after this idle time (ms) before matching (Modbus framing); 0 = per-chunk. Note: framing happens before matching and is shared by the connection, so the LARGEST value among enabled rules is used.",
        "ar_verify": "RX checksum",
        "ar_verify_tip": "Verify the whole received frame's trailing checksum with this algorithm; reply only if it passes (bad frames get no reply). 'None' = no check. This device = MOBUS.",
        "ar_match_ph": "match (HEX: ?? byte, A?/?5 nibble, b:1xxxxxx1 bit-mask wildcards, e.g. 54 ?? 03)",
        "ar_script_err": "⚠ Script error: {e}",
        "ar_script_btn": "Script",
        "ar_script_tip": "Scripted reply: write Python (def reply(frame, ctx)) to build the reply dynamically, replacing the static template. Blank = off.",
        "ar_script_mode_tip": "Script mode: this row's reply is built by the script; the static reply / checksum are ignored",
        "ar_script_enable": "Enable script",
        "ar_script_timeout": "Script timed out (>{s}s) — likely an infinite loop or blocking call",
        "ar_script_title": "Scripted reply — edit",
        "ar_script_import_title": "Import config — contains scripts",
        "ar_script_import_warn": "This config contains {n} script(s); once imported they run Python when a rule matches.\nTrust the source and import the scripts? (No = import config but blank the scripts)",
        "ar_script_test_ph": "test frame HEX (e.g. AA 11 22 33) → run the script",
        "ar_script_none": "(script returned no reply)",
        "ar_script_tmpl": "def reply(frame, ctx):\n    # frame: bytes (matched frame); ctx: state/seq/hits + crc/crc16/sum8/xor8/hexbytes/tohex\n    # return bytes / list[bytes] / str / None\n    return bytes([0x06]) + frame[1:3]\n",
        "ar_script_help": "<b>Scripted reply</b>: define <code>reply(frame, ctx)</code> to build the reply dynamically (replaces the static template; the script owns the whole frame, <b>no checksum is auto-appended</b> — compute it via ctx). Return <code>bytes</code>=one frame / <code>list[bytes]</code>=multi / <code>str</code>=text / <code>None</code>=no reply.<br><b>ctx</b>: <code>.state</code> current state · <code>.seq</code> · <code>.hits</code>; <code>.crc(data, width=16, poly=0x1021, init=0, refin=False, refout=False, xorout=0, byteorder='big')</code> general customizable CRC; shortcuts <code>.crc16</code>(Modbus) / <code>.crc8</code> / <code>.sum8</code> / <code>.xor8</code>; <code>.hexbytes('AA BB')</code>→bytes · <code>.tohex(b)</code>→'AA BB'.<br>Fault injection + delay still apply. ⚠ scripts run Python locally; scripts inside imported configs ask for consent first.",
        "ar_mask_help": "<b>Match syntax</b> (HEX mode)<br>• <code>AB</code> exact byte　<code>??</code>/<code>XX</code> byte wildcard<br>• <code>A?</code> / <code>?5</code> nibble wildcard (high / low 4 bits; <code>X</code> = <code>?</code>)<br>• <code>b:1xxxxxx1</code> bit-mask (8 of <code>0/1/x</code>; <code>x</code> = don't-care)<br>• mix: <code>AA b:1001xxxx ?5</code><br>• field: <code>?? ?? ?? b:xxxxxxx1</code> + 'prefix' mode = byte 4 bit0 must be 1",
        "ar_reply_ph": "reply ({r3}=byte 3 {r1+1}=add {r1^FF}=xor {seq}=counter {ts}=timestamp; | splits into multiple frames)",
        "ar_btn_tip": "Click = open config, double-click = toggle on/off",
        "ar_toast_on": "Auto-reply enabled",
        "ar_toast_off": "Auto-reply disabled",
        "ar_cooldown_tip": "Cooldown (ms): a single rule fires at most once per window — prevents reply storms when matching frames arrive in rapid succession. Different from Delay (turnaround); cooldown is rate-limiting, delay is output timing.",
        "ar_frame_on": "Header+Length framing",
        "ar_frame_hdr": "Header",
        "ar_frame_off": "Len offset",
        "ar_frame_width": "W",
        "ar_frame_extra": "frame=len+",
        "ar_cs_btn": "Chk segs",
        "ar_hits": "Hits {n}",
        "ar_hits_tip": "Hit count (this session): +1 on match + RX-checksum pass (incl. cooldown-suppressed). Click Reset stats to clear.",
        "ar_test": "Test",
        "ar_reset_stats": "Reset stats",
        "ar_test_title": "Rule tester (offline)",
        "ar_test_hint": "Enter one HEX frame and click Test → see which rule matches and what it would reply (with placeholder substitution + checksum-segment / tail-checksum results). Preview only — nothing is sent or counted.",
        "ar_test_ph": "one HEX frame, e.g. 01 06 12 34 56 78",
        "ar_test_run": "Test",
        "ar_test_bad_hex": "Bad HEX (need an even number of hex digits).",
        "ar_test_no_match": "No rule matched.",
        "ar_delay_tip": "Reply delay (ms): fixed e.g. 100, or a range 100-300 (random jitter per send, simulates device turnaround).",
        "ar_fault_on": "Fault inject",
        "ar_fault_tip": "Global host stress test: inject faults into all auto-replies by probability (Drop = no reply, tests retransmit; Bad CRC = flip last byte, tests checksum; Bad len = drop last byte, tests framing). Injected frames are marked in the data area.",
        "ar_fault_drop": "Drop",
        "ar_fault_badcrc": "Bad CRC",
        "ar_fault_badlen": "Bad len",
        "ar_fault_badcrc_short": "bad CRC",
        "ar_fault_badlen_short": "bad len",
        "ar_fault_note_drop": "⚠ fault-inject · dropped (not sent)",
        "ar_frame_desc": "Tick for header+length protocols → split at real frame boundaries (handles packet join/split)",
        "ar_fault_desc": "Tick to corrupt replies by probability → stress-test the host's retransmit / tolerance",
        # C8 multi-step state machine
        "ar_sm_on": "State machine",
        "ar_sm_tip": "Multi-step state machine: each rule can set 'reply only in state' and 'go to state after replying', chaining rules into a frame-sequence handshake/session. Off = ignore when/goto (plain mode).",
        "ar_sm_init": "Initial",
        "ar_sm_init_ph": "e.g. S0, blank=empty",
        "ar_sm_cur": "Now",
        "ar_sm_reset": "Reset state",
        "ar_sm_desc": "Advance state by received-frame sequence: rules can require 'only in state' and 'go to' after replying",
        "ar_sm_empty": "(empty)",
        "ar_when_ph": "only state",
        "ar_when_tip": "This rule can match only when the current state equals this (comma-separate several, e.g. S1,S2). Blank = any state (wildcard). Effective only when the state machine is on.",
        "ar_goto_ph": "→ state",
        "ar_goto_tip": "After this rule replies, set the current state to this. Blank = unchanged. Effective only when the state machine is on.",
        "ar_test_state": "Current state: {s}",
        "ar_test_goto": "State after reply → {s}",
        "ar_test_state_skip": "(state machine on: in state \"{s}\", this rule's 'only state' doesn't match → would not reply)",
        "ar_sm_help_title": "Multi-step state machine — help & examples",
        "ar_sm_help": "Chain rules into a state machine that <b>advances by frame sequence</b>, for handshakes/sessions.<br>Each rule has two optional fields:<br>• <b>only state</b>: this rule can match only when the current state equals it (comma-separate several, e.g. <code>S1,S2</code>). Blank = any state (wildcard).<br>• <b>go to</b>: after this rule replies, set the current state to it. Blank = unchanged.<br><br><b>Initial</b>: the state on connect / reset (blank = empty state). The <b>current</b> state is shown live and can be <b>reset</b> anytime. Rules are still <b>first-match-wins</b>: within a state, the first matching rule top-to-bottom is used.<br><br><b>Example (3-step handshake)</b>, initial <code>S0</code>:<br>Rule 1 only <code>S0</code>, match <code>AA 01</code> → reply…, go to <code>S1</code><br>Rule 2 only <code>S1</code>, match <code>AA 02</code> → reply…, go to <code>S2</code><br>Rule 3 only <code>S2</code>, match <code>AA 03</code> → reply…, go to <code>S0</code><br>The host must handshake in order 01→02→03; out-of-order frames won't match.<br><b>Wildcard tip</b>: a rule with 'only state' blank, match <code>RESET</code>, go to <code>S0</code> pulls the session back to start from any state.",
        # B4 Modbus RTU slave
        "ar_modbus": "Modbus slave",
        "ar_modbus_tip": "Act as a Modbus RTU slave: when the slave address matches and CRC is valid, auto-reply by function code (read 01/02/03/04, write 05/06/0F/10) from the register tables. Rules / state machine step aside when on.",
        "ar_modbus_title": "Modbus RTU slave",
        "ar_modbus_hint": "When on, the app is a Modbus RTU slave: on matching address + valid CRC it auto-replies by function code (read coils/discrete/holding/input; write single/multiple; illegal requests get an exception reply). The table below sets each register's initial value (unlisted addresses = 0); the master's writes change the runtime model and reset on disconnect/reconnect. Register values: decimal or 0x hex, comma-separated and filled consecutively; coils/discrete use 0/1.",
        "ar_modbus_on": "Enable Modbus slave",
        "ar_modbus_active": "● Modbus slave mode is on: the rules / state machine / header-length framing below are inactive (fault injection still applies to Modbus responses). Click 'Modbus slave' above to turn it off.",
        "ar_modbus_addr": "Slave addr",
        "ar_modbus_space": "Space",
        "ar_modbus_start": "Start addr",
        "ar_modbus_values": "Values (comma-separated, filled consecutively)",
        "ar_modbus_add": "Add row",
        "ar_mb_holding": "Holding 4x",
        "ar_mb_input": "Input 3x",
        "ar_mb_coil": "Coils 0x",
        "ar_mb_discrete": "Discrete 1x",
        "ar_modbus_help_title": "Modbus slave — help & examples",
        "ar_modbus_help": "Make the app emulate a <b>Modbus RTU slave</b> device. When on, incoming frames are parsed as Modbus RTU; if the <b>slave address matches and CRC is valid</b>, a standard response is auto-built by function code:<br>• Read: <code>01</code> coils / <code>02</code> discrete inputs / <code>03</code> holding regs / <code>04</code> input regs<br>• Write: <code>05</code> single coil / <code>06</code> single reg / <code>0F</code> multiple coils / <code>10</code> multiple regs<br>• Illegal function / address / value auto-returns an <b>exception</b> (0x80|func + code)<br><br><b>Register table</b>: each row picks Space + Start addr + Values, filled <b>consecutively</b> from the start (comma-separated). Register values are decimal or <code>0x</code> hex (0–65535); coils/discrete use <code>0/1</code>. Unlisted addresses default to 0. The master's writes (05/06/0F/10) change the <b>runtime</b> registers; disconnect/reconnect/disabling Modbus resets to the values configured here.<br><br><b>Example</b>: Space Holding, Start <code>0</code>, Values <code>0x1234, 0x5678, 100</code> → regs 0/1/2 = 0x1234 / 0x5678 / 100. Master sends 'read holding, start 0, count 2' → auto-replies <code>01 03 04 12 34 56 78 …</code>.<br><b>Note</b>: with Modbus slave on, normal reply rules and the state machine don't participate (the whole engine acts as the slave); RTU has no header, so frames are split by function-code length + CRC, with cross-packet buffering and auto-resync on CRC error. In TCP server mode, each response is routed precisely to the requesting client.",
        "ar_frame_help_title": "Header + Length framing — help & examples",
        "ar_frame_help": "For binary protocols with a <b>fixed header + length field</b>: bytes are buffered across packets, located by header, and split at the real frame boundary computed from the length field — correctly handling serial/TCP <b>packet join/split</b> (more accurate than idle-timeout, no added delay). When off, framing falls back to per-received-block or idle-timeout.<br><br>Fields:<br>• <b>Header</b>: hex, e.g. <code>AA BB</code>; only frames starting with it<br>• <b>Len offset</b>: byte position of the length field in the frame (0-based)<br>• <b>Width</b>: bytes of the length field (1/2/4)<br>• <b>LE/BE</b>: endianness of the length field<br>• <b>frame = len +</b>: total length = length-field value + this fixed overhead (header/length/checksum bytes not counted by the length field)<br><br><b>Example</b>: protocol <code>AA BB │ len(1B) │ data… │ sum(1B)</code>, length = number of data bytes.<br>Set header <code>AA BB</code>, len offset <code>2</code>, width <code>1</code>, <code>LE</code>, frame=len+ <code>4</code> (= header 2 + len 1 + sum 1).<br>Receive <code>AA BB 03 11 22 33 7E</code> → len=3 → frame = 3+4 = 7 bytes, split as one frame; a following concatenated frame is split correctly too.",
        "ar_fault_help_title": "Fault injection — help & examples",
        "ar_fault_help": "Global switch that injects faults into <b>all auto-replies</b> by probability, to <b>stress-test the host</b>'s retransmit/tolerance. Rolled before each send:<br><br>• <b>Drop %</b>: <b>send nothing</b> (= no reply) → tests the host's retransmit logic<br>• <b>Bad CRC %</b>: <b>flip the last byte</b> (^0xFF) so the checksum fails → tests whether the host discards bad frames<br>• <b>Bad len %</b>: <b>drop the last byte</b> → tests the host's length/framing tolerance<br>Rolled independently; if Drop fires the others are skipped. Injected frames are marked <code>⚠ fault-inject · …</code> in the data area.<br><br><b>Example 1</b> (retransmit): your device 'resends 3× if no reply'. Set <b>Drop</b> = <code>30</code>, others <code>0</code> → ~1 in 3 replies dropped, so you can watch the host retransmit and verify it.<br><b>Example 2</b> (bad-frame handling): set <b>Bad CRC</b> = <code>20</code> → see whether the host discards checksum-failed frames and retries instead of mis-using them.",
        "ar_fault_note_corrupt": "⚠ fault-inject · {what}",
        "ar_test_matched": "Matched rule #{n}:",
        "ar_test_verify_fail": "(matched, but RX checksum fails -> would not reply)",
        "ar_test_no_reply": "(no reply content)",
        "ar_test_reply_bad": "(reply HEX parse failed)",
        "ar_cs_tip": "Inner / extra checksums: compute a checksum over a sub-range of the reply and write it at a given offset, applied in order BEFORE the row's tail checksum (for protocols with e.g. an outer Sum + an inner CRC).",
        "ar_cs_title": "Checksum segments (inner / extra)",
        "ar_cs_add": "Add segment",
        "ar_cs_algo": "Algorithm",
        "ar_cs_start": "Start",
        "ar_cs_end": "End",
        "ar_cs_at": "Write at",
        "ar_cs_help": "Each segment checksums reply bytes [start..end] (inclusive) and writes the result at \"Write at\".\n• Order: top to bottom (inner first); the row's tail checksum (outer) is then appended after these.\n• Write at empty = append at the tail; a number = overwrite the bytes at that offset (reserve placeholder bytes in the reply first, e.g. 00 00).\n• Start / End / Write at: 0-based, negative counts from the end (-1 = last byte); End empty = current last byte.\nExample: reply AA BB {r2} 06 12 34 00 00, add one ModbusCRC16 start=2 end=5 at=6 → overwrites those two 00 with the CRC; pick ADD8 as the row's tail checksum → sums the whole frame (incl. the inner CRC) and appends.",
        "ar_frame_tip": (
            "When checked, split frames by 'header + length field' (for protocols with a header + "
            "length like AA BB…), correctly handling serial packet join/split. Takes priority over "
            "the per-rule 'Frame gap' idle timeout.\n"
            "Header = hex (e.g. AA BB); Len offset = length field offset from the header's first "
            "byte; W = length field width in bytes (1/2/4); LE/BE = little/big endian; frame=len+N "
            "means total frame bytes = length value + N (fixed overhead: header/seq/checksum).\n"
            "Example (this device): header AA BB · len offset 4 · W 2 · LE · frame=len+7."),
        "ar_help": (
            "<b>How it works</b>: incoming data is matched against rules → auto-sends the reply. Rules checked in order, first match wins (at most one reply per frame). Active only when connected and master switch is on.<br>"
            "<b>Match</b>: HEX/text × contains/equals/<b>prefix</b>. In HEX, <code>??</code> is a single-byte wildcard (e.g. <code>54 ?? 03</code>). For finer granularity use <b>nibble</b> <code>A?</code>/<code>?5</code> (high/low 4 bits) and a <b>bit-mask</b> <code>b:1xxxxxx1</code> (8 of <code>0/1/x</code>, <code>x</code> = don't-care bit). To distinguish frame types by the first byte, <b>use prefix, not contains</b> (else that byte inside other frames' data causes false matches).<br>"
            "<b>Reply placeholders</b> (in the Reply field): "
            "<code>{rN}</code>=received byte N (0-based) &nbsp; "
            "<code>{rN-M}</code>=range &nbsp; "
            "<code>{rN+K}</code>=add K (mod256) &nbsp; "
            "<code>{rN^K}</code>=XOR K &nbsp; "
            "<code>{seq}</code>=auto-increment 1B &nbsp; "
            "<code>{ts}</code>=ms timestamp 4B BE. "
            "Use <code>|</code> for multi-frame (e.g. <code>06 | 04 03 02 01</code> sends 06, then 04 03 02 01 after Delay).<br>"
            "<b>Timing</b>: <b>Frame gap</b>=treat bytes as one frame after N ms idle (Modbus-style framing); <b>Delay</b>=wait N ms before replying (slave turnaround); <b>Cooldown</b>=same rule fires at most once per N ms (anti-storm).<br>"
            "<br><b>Example 1 (MOBUS device, echo received bytes + auto CRC):</b>"
            "<pre style='margin:2px 0 2px 16px'>Match = 54     HEX ✓  mode=prefix   RX checksum = MOBUS\n"
            "Reply = 03 {r2} {r1} 00   HEX ✓  Checksum = MOBUS\n"
            "RX: 54 03 01 02 ... CRC  →  TX: 03 01 03 00 ... CRC (CRC appended)</pre>"
            "<b>Example 2 (heartbeat reply with counter + timestamp):</b>"
            "<pre style='margin:2px 0 2px 16px'>Match = AA   HEX ✓  mode=equals\n"
            "Reply = 55 {ts} {seq}   HEX ✓\n"
            "RX: AA  →  TX: 55 F4 50 38 17 01 (4B ts + auto-inc seq)</pre>"
            "<b>Example 3 (HEX wildcard + multi-frame ACK+DATA):</b>"
            "<pre style='margin:2px 0 2px 16px'>Match = 54 ?? 03   mode=contains   Reply = 06 | 04 03 02 01   Delay = 10 ms\n"
            "Any 54 X 03 frame triggers: TX 06, then 04 03 02 01 after 10 ms</pre>"
            "<b>Example 4 (AT command — text mode):</b>"
            "<pre style='margin:2px 0 2px 16px'>Match = AT+VER?   text (HEX unchecked)   mode=equals\n"
            "Reply = +VER:1.2.3\\r\\nOK\\r\\n   text   Checksum = none\n"
            "RX: AT+VER?  →  TX: +VER:1.2.3&lt;CR&gt;&lt;LF&gt;OK&lt;CR&gt;&lt;LF&gt;</pre>"
            "<b>Example 5 (multi-rule dispatch by frame type — first match wins):</b>"
            "<pre style='margin:2px 0 2px 16px'>Device has multiple frame types; one rule per type, in order:\n"
            "  Rule 1: Match = 54   mode=prefix   →   Reply 03 {r2} {r1} 00   Checksum=MOBUS\n"
            "  Rule 2: Match = 02   mode=prefix   →   Reply 03 {r1} 00 00     Checksum=MOBUS\n"
            "  Rule 3: Match = 04   mode=prefix   →   Reply 03 {r1} {r2} {r3} Checksum=MOBUS\n"
            "First byte selects which rule; prefix mode is byte-aligned — no false match from 02 inside other frames' data</pre>"
            "<b>Example 6 (range echo + arithmetic + rate-limit; {r1-4} {r1+1} {r2^FF}):</b>"
            "<pre style='margin:2px 0 2px 16px'>Match = AA   HEX ✓   mode=equals   Cooldown = 200 ms\n"
            "Reply = {r1-4} {r1+1} {r2^FF}   HEX ✓\n"
            "RX: AA 10 20 30 40 50  →  TX: 10 20 30 40 50 11 DF\n"
            "  ({r1-4}=bytes 1..4   {r1+1}=10+1=11   {r2^FF}=20 XOR FF = DF)\n"
            "Even if device sends every 10 ms, reply only fires every 200 ms (cooldown drops the in-between)</pre>"
        ),
        "plot_open": "Plot",
        "plot_need_lib": "Plot requires the pyqtgraph package: {e}",
        "plot_title": "Data Plot",
        "plot_help_btn": "Help",
        "plot_help_title": "Data Plot — Help",
        "plot_help": (
            "<b>How it works</b>: parse numbers out of RX data and plot per-channel curves in real-time. Three parse modes — pick by protocol: text streams → delimiter/regex, binary HEX frames → HEX byte field.<br>"
            "<b>Delimiter mode</b>: split each line by the chosen separator; one column = one curve.<br>"
            "<b>Regex mode</b>: match each line; each <b>capture group</b> = one curve (use <code>(?:…)</code> for non-capturing).<br>"
            "<b>HEX byte field mode</b>: each received block = one frame (split by data area 'Packet Split'); fields use <code>name=offset:type</code>. Optional <b>Header</b> filter: fill hex header to only parse frames starting with it.<br>"
            "<br><b>Example 1 (Delimiter — CSV text stream):</b>"
            "<pre style='margin:2px 0 2px 16px'>Device output: <code>1.23,4.56,7.89\\n2.34,5.67,8.90\\n…</code>\n"
            "Mode = Delimiter   Sep = comma\n"
            "→ 3 curves (CH0/CH1/CH2), one sample per line</pre>"
            "<b>Example 2 (Regex — labelled text):</b>"
            "<pre style='margin:2px 0 2px 16px'>Device output: <code>T=23.4 H=56.7 P=1013\\n</code>\n"
            "Mode = Regex   Pattern = <code>T=([\\d.]+)\\s+H=([\\d.]+)\\s+P=([\\d.]+)</code>\n"
            "→ 3 curves (temp/humidity/pressure), one capture group each</pre>"
            "<b>Example 3 (HEX byte field — binary protocol):</b>"
            "<pre style='margin:2px 0 2px 16px'>Device frame: <code>54 00 0A 04 7F …</code> (i16le, then i16le)\n"
            "Mode = HEX byte field   Fields = <code>X=1:i16le, Y=3:i16le</code>\n"
            "RX: 54 00 0A 04 7F → X=0x0A00=2560 (le)  Y=0x047F=1151\n"
            "→ 2 curves (X/Y), one point per frame</pre>"
            "<b>Example 4 (HEX + header filter — pick one frame type):</b>"
            "<pre style='margin:2px 0 2px 16px'>Device emits multiple frame types (54/02/04); only plot 54-frames:\n"
            "Mode = HEX byte field   <b>Header = 54</b>   Fields = <code>X=1:i16le, Y=3:i16le</code>\n"
            "Other frames (02xx…/04xx…) are filtered out, only 54-prefixed frames are parsed</pre>"
            "<b>Example 5 (Floats — accelerometer/gyro):</b>"
            "<pre style='margin:2px 0 2px 16px'>12-byte frame: 3× f32le (X/Y/Z accel)\n"
            "Mode = HEX byte field   Fields = <code>aX=0:f32le, aY=4:f32le, aZ=8:f32le</code>\n"
            "→ 3 acceleration curves, one sample per frame</pre>"
            "<br><b>X axis</b> can switch to 'sample index' or 'time'; <b>Window</b> caps max points (older drops, prevents memory blow-up); <b>Pause/Clear/Export CSV</b> on the top-right.<br>"
            "<b>⚠️ HEX byte field mode splits per received block</b> (one block = one frame, no de-framing). For serial/TCP, pair with data area's <b>'Packet Split'</b>."
        ),
        "plot_mode": "Parse",
        "plot_mode_delim": "Delimiter",
        "plot_mode_regex": "Regex",
        "plot_mode_hex": "HEX bytes",
        "plot_fields_ph": "binary fields offset:type, e.g. 3:u8, 9:i16le (one frame per packet)",
        "plot_fields_bad": "Bad field spec; use offset:type, e.g. 3:u8,9:i16le",
        "plot_header_ph": "frame header hex, opt., e.g. 54",
        "plot_header_bad": "Frame header must be hex, e.g. 54 or 5400",
        "frame_open": "Frames",
        "mbm_open": "Modbus Master",
        "mbm_title": "Modbus Master Poll",
        "mbm_enable": "Enable polling",
        "mbm_variant": "Transport",
        "mbm_variant_auto": "Auto (by connection)",
        "mbm_echo": "Local echo",
        "mbm_echo_tip": "Tick this if your serial adapter echoes sent frames (common on RS-485 half-duplex). It strips one leading copy of the request before parsing the real response. Crucial for write functions 05/06, whose echo is identical to a success reply: without it the echo is taken as success and the slave's exception is lost.",
        "mbm_variant_rtu": "Modbus RTU",
        "mbm_variant_tcp": "Modbus TCP",
        "mbm_apply": "Apply",
        "mbm_apply_first": "Apply the pending polling rules first",
        "mbm_reconnect_first": "Connection settings changed or polling is unsupported; reconnect Serial or TCP Client first",
        "mbm_add": "Add",
        "mbm_help_btn": "Help",
        "mbm_hint": "Polls each row periodically: serial uses Modbus RTU and TCP Client uses Modbus TCP. Rule edits take effect only after Apply; editing a write rule never sends it automatically.",
        "mbm_col_name": "Name",
        "mbm_col_unit": "Unit",
        "mbm_col_func": "Function",
        "mbm_col_addr": "Address",
        "mbm_col_qty": "Qty/Value",
        "mbm_qty_tip": "Reads: quantity. Write single 05/06: one value. Write multi 0F/10: several values, comma- or space-separated, e.g. 100,200,300 (0F coils: 0/1).",
        "mbm_col_period": "Period ms",
        "mbm_col_value": "Value",
        "mbm_col_status": "Status",
        "mbm_f1": "01 Read Coils",
        "mbm_f2": "02 Read Discrete",
        "mbm_f3": "03 Read Holding",
        "mbm_f4": "04 Read Input",
        "mbm_f5": "05 Write Coil",
        "mbm_f6": "06 Write Register",
        "mbm_f7": "0F Write Coils",
        "mbm_f8": "10 Write Registers",
        "mbm_st_ok": "OK",
        "mbm_st_timeout": "Timeout",
        "mbm_st_senderr": "Send failed",
        "mbm_st_exc": "Exception {code}",
        "mbm_st_written": "Wrote [{addr}]={val}",
        "mbm_st_written_multi": "Wrote [{addr}] x{n}",
        "mbm_st_badresp": "Bad response",
        "mbm_st_noval": "No/invalid values",
        "mbm_st_badparam": "Invalid unit/address/quantity/period",
        "mbm_st_pending": "Pending Apply",
        "mbm_st_broadcast": "Broadcast sent (no response)",
        "mbm_st_broadcast_read": "Broadcast address cannot be used for reads",
        "mbm_help_title": "Modbus Master Poll — Help",
        "mbm_help": "Modbus Master Poll: act as a Modbus master, polling slaves at each row's period and showing results live.\n\n• Transport: Auto = serial->RTU, TCP Client->Modbus TCP; or force a variant.\n• Functions 01-04 are reads: 'Qty' is the number of registers/coils; results show decimal + hex.\n• Functions 05/06 are writes: the 'Qty/Value' cell is the value (05 coil: 0/1); it rewrites each period and shows the echo.\n• Functions 0F/10 are multi-writes: put several values in the 'Qty/Value' cell, comma- or space-separated, e.g. 100,200,300 (0F coils: 0/1); the count = number of values, and any invalid value prevents the whole row from being sent.\n• Half-duplex: only one request is in flight; the next is sent after a response or timeout. Serial timeout is calculated dynamically from frame length and baud rate.\n• Status: OK / Timeout / Exception (slave's exception code) / Send failed / Bad response.\n• Local echo: if your serial adapter echoes sent frames (common on RS-485 half-duplex), tick 'Local echo' — especially for writes 05/06 whose echo looks identical to a success reply; without it the echo is taken as success and the slave's exception is lost.\n\nUsage: connect first (serial or TCP Client), add rows, then tick 'Enable polling'.\nNote: do not also enable 'Auto-reply - Modbus Slave' - one receives requests, the other sends them; mixing interferes.",
        "frame_title": "Frame Parser",
        "frame_hdr": "Header",
        "frame_fld": "Fields",
        "frame_fields_ph": "name=offset:type, e.g. temp=9:i16le, st=15:u8 (hexN/strN ok)",
        "frame_col_time": "Time",
        "frame_col_raw": "Raw frame",
        "frame_col_rule": "Rule",
        "frame_col_fields": "Fields",
        "frame_rules": "Rules",
        "frame_add_rule": "Add rule",
        "frame_help_btn": "Help",
        "frame_help_title": "Frame Parser — Help",
        "frame_help": (
            "<b>How it works</b>: fill in 'Header + Fields' rules then click Apply. Each received block is matched against rule headers (prefix) — first match wins.<br>"
            "<b>Rule columns</b>:<br>"
            "&nbsp;&nbsp;<b>Header</b>: hex string like <code>02</code>; empty = catch-all for frames not matched by earlier rules<br>"
            "&nbsp;&nbsp;<b>Fields</b>: <code>name=offset:type</code> comma-separated; offset is 0-based<br>"
            "<b>Types</b>:<br>"
            "&nbsp;&nbsp;Numeric: <code>u8 i8 u16le u16be i16le i16be u32le u32be i32le i32be f32le f32be f64le f64be</code><br>"
            "&nbsp;&nbsp;Append <code>x</code> for HEX display (e.g. <code>u8x</code> shows 0x1F instead of 31)<br>"
            "&nbsp;&nbsp;<code>hexN</code> = N raw bytes as HEX; <code>strN</code> = N bytes as ASCII text<br>"
            "<br><b>Example 1 (simplest — single-byte fields):</b>"
            "<pre style='margin:2px 0 2px 16px'>Header = 02   Fields = seq=1:u8, len=2:u8, type=3:u8\n"
            "RX: 02 0A 04 7F → seq=10  len=4  type=127</pre>"
            "<b>Example 2 (multi-byte numerics + endianness):</b>"
            "<pre style='margin:2px 0 2px 16px'>Header = 54   Fields = ID=1:u16le, temp=3:i16le, time=5:u32be\n"
            "RX: 54 34 12 5C FF 00 00 04 D2 → ID=0x1234=4660  temp=-164  time=1234</pre>"
            "<b>Example 3 (HEX display + raw bytes + ASCII):</b>"
            "<pre style='margin:2px 0 2px 16px'>Header = AA   Fields = status=1:u8x, MAC=2:hex6, name=8:str8\n"
            "RX: AA 1F 00 11 22 33 44 55 CommTool → status=0x1F  MAC=00 11 22 33 44 55  name=CommTool</pre>"
            "<b>Example 4 (HEX numeric — bit-level register view):</b>"
            "<pre style='margin:2px 0 2px 16px'>Header = 06   Fields = status=1:u8x, fault=2:u16lex\n"
            "RX: 06 80 34 12 → status=0x80  fault=0x1234</pre>"
            "<b>Example 5 (multi-rule dispatch — first match wins):</b>"
            "<pre style='margin:2px 0 2px 16px'>Rule 1: Header=54  Fields=seq=1:u8, type=2:u8\n"
            "Rule 2: Header=02  Fields=ack=1:u8\n"
            "Rule 3: Header=(empty)  Fields=type=0:u8x      ← catch-all\n"
            "First byte routes to a rule; 54/02 have dedicated parsing, others go to the catch-all</pre>"
            "<br><b>⚠️ Per-block framing</b>: one received block = one frame; no cross-block de-framing — a half frame loses fields, concatenated frames parse only the first, and a frame whose header isn't at the block start is dropped. For serial/TCP, enable <b>'Packet Split'</b> in the data area so each frame arrives as its own block."
        ),
        "frame_rules_ph": "one rule per line: header | fields. e.g.  02 | seqL=1:u8, seqH=3:u8x",
        "frame_apply": "Apply",
        "frame_tab_all": "All",
        "frame_rule_bad": "Bad rule: {line}",
        "frame_export_title": "Export frames",
        "frame_hint": "One rule per line 'header | fields'; each frame matches the first rule by header prefix (empty header = catch-all). Click Apply after editing. The All tab shows the mixed stream by time; each rule also gets its own columnar tab. Numeric + x = hex; hexN/strN; Raw column for cross-check.",
        "plot_sep_comma": "Comma ,",
        "plot_sep_space": "Whitespace",
        "plot_sep_tab": "Tab",
        "plot_sep_semicolon": "Semicolon ;",
        "plot_sep_auto": "Auto",
        "plot_regex_ph": "Groups = channels, e.g. temp=(\\d+).*hum=(\\d+)",
        "plot_regex_bad": "Invalid regular expression",
        "plot_window": "Points",
        "plot_xaxis": "X axis",
        "plot_x_index": "Sample #",
        "plot_x_time": "Time (s)",
        "plot_pause": "Pause",
        "plot_resume": "Resume",
        "plot_clear": "Clear",
        "plot_export": "Export CSV",
        "plot_export_title": "Export plot data",
        "plot_no_data": "No data to export",
        "plot_hint": "Parses numbers from RX text line by line: delimiter mode = one curve per column, regex mode = one curve per capture group; redraws at ~30 FPS independent of packet rate.\n⚠️ HEX byte-field mode splits frames per received block (one block = one frame, no de-framing); for serial/TCP, pair it with 'Packet Split' in the data area.",
        "dlg_save_data": "Save received data",
        "dlg_log_path": "Choose log file path",
        "dlg_load_file": "Load file as send content",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== Log started {time} ==========\n",
        "log_footer": "\n========== Log ended {time} ==========\n",
        "log_started": "Logging started",
        "log_stopped": "Logging stopped",
        "saved_to": "Saved to {path}",
        "err_hex_odd": "HEX length must be even",
        "err_hex_bad": "HEX format error: {e}",
        "err_hex_invalid_chars": "invalid character(s) {chars}",
        "err_send_failed": "Send failed: {e}",
        "err_checksum": "Checksum failed: {e}",
        "err_save_failed": "Save failed: {e}",
        "err_read_failed": "Load failed: {e}",
        "err_period_bad": "Period error: {e}",
        "err_min_period": "Min period 10ms",
        "err_open_log": "Open failed: {e}",
        "err_log_write": "Log write failed: {e}",
        "err_rx": "RX error: {e}",
        "font_size_msg": "Font size: {size} pt",
        "close_prompt": "How do you want to close?",
        "close_minimize": "Minimize to Tray",
        "close_quit": "Quit",
        "close_cancel": "Cancel",
        "tray_show": "Show Window",
        "tray_quit": "Quit",
        "tray_minimized": "{app} minimized to system tray",
        # —— hover tooltips ——
        "hex_display_tip": "Display incoming bytes as hex.\nOff: show as text/ASCII",
        "encoding_tip": "Character encoding for RX decoding / TX encoding / file load.\nAuto: UTF-8 first, fall back to GBK on mojibake.\nOr pick UTF-8 / GBK / GB2312 / Big5 etc. for strict decoding.",
        "theme_tip": "Color scheme for the data area (terminal-style).\nSwitching also recolors existing history to the new theme.\nClear the data area to apply the new theme to everything.",
        "auto_wrap_tip": "Wrap long lines automatically.\nOff: scroll horizontally",
        "show_timestamp_tip": "Prefix each block with [YYYY/MM/DD HH:MM:SS ms] timestamp and ←/→ direction arrow",
        "packet_split_tip": "Start a new block when no data arrives for longer than the timeout below.\nMerges burst data on the same line",
        "timeout_tip": "Time-split threshold (ms).\nNew block when receive gap exceeds this",
        "line_split_tip": "Split on newline characters.\nAuto / CRLF / LF / CR",
        "real_time_log_tip": "Append both RX and TX data to a log file in real time.\nWYSIWYG: timestamp/arrow/HEX preserved. Off to stop writing.",
        "max_lines_tip": "Maximum lines kept in the data area.\nOldest are dropped (prevents memory bloat)",
        "hex_send_tip": "Send input as raw bytes parsed from a hex string (e.g. AA BB CC).\nOff: send as text",
        "append_newline_tip": "Append a newline after each send.\nCRLF / LF / CR",
        "period_tip": "Send the content periodically at the interval (ms) on the right",
        "checksum_tip": "Append a checksum at the end of each send.\nADD8 / XOR8 / CRC8 / MOBUS / CRC16 / CRC32 ...",
    },
    "zh_tw": {
        "app_title": "通訊調試工具",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "資料區",
        "legend_rx": "← 收",
        "legend_tx": "→ 發",
        "to_bottom": "↓ 最新",
        "hex_display": "HEX 顯示",
        "encoding": "字元編碼",
        "encoding_auto": "自動",
        "theme": "主題",
        "theme_default": "預設",
        "theme_dark": "暗色",
        "theme_one_half_lt": "One Half 淺色",
        "theme_one_half_dk": "One Half 深色",
        "theme_solar_lt": "Solarized 淺色",
        "theme_solar_dk": "Solarized 深色",
        "theme_tango_dk": "Tango 深色",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "自動換行",
        "show_timestamp": "顯示時間戳",
        "packet_split": "時間分包",
        "line_split": "換行分包",
        "nl_auto": "自動",
        "timeout": "超時",
        "real_time_log": "即時記錄",
        "log_split_none": "不分包",
        "log_path_idle": "（未記錄）",
        "log_split_tip": "即時記錄按檔案大小分包：寫到設定大小就切到新檔(原名加 _001/_002…)。\n可手填自訂，如 3M / 500K；選「不分包」則單檔不限。",
        "max_lines": "最大行數",
        "save": "儲存",
        "ctx_copy": "複製",
        "ctx_select_all": "全選",
        "clear": "清空",
        "font_dec": "字號減小",
        "font_inc": "字號增大",
        "conn_settings": "連線設定",
        "protocol_type": "類型",
        "port": "串口",
        "baud_rate": "鮑率",
        "data_bits": "資料位元",
        "parity": "校驗位元",
        "stop_bits": "停止位元",
        "btn_serial_open": "開啟串口",
        "btn_serial_close": "關閉串口",
        "no_ports": "無可用串口",
        "port_missing": "{port}（未偵測到）",
        "serial_removed": "串口 {port} 已移除，連線已斷開",
        "err_no_port": "請選擇串口",
        "err_bad_baud": "鮑率無效",
        "err_open_failed": "開啟串口失敗: {e}",
        "local_ip": "本地IP",
        "local_port": "本地埠",
        "remote_ip": "遠端IP",
        "remote_port": "遠端埠",
        "target_client": "目標",
        "client_all": "全部",
        "btn_listen": "開始監聽",
        "btn_listen_stop": "停止監聽",
        "btn_connect": "連線",
        "btn_disconnect": "中斷",
        "btn_udp_open": "開啟",
        "btn_udp_close": "關閉",
        "net_connecting": "● 連線中…",
        "net_listening": "● {proto} 監聽 {addr}",
        "net_connected": "● 已連線 {addr}",
        "net_udp_bound": "● UDP {addr}",
        "err_bad_port": "埠號無效 (1-65535)",
        "err_bad_ip": "IP 位址無效",
        "err_listen_failed": "監聽失敗: {e}",
        "err_connect_failed": "連線失敗: {e}",
        "err_bind_failed": "綁定失敗: {e}",
        "err_conn_timeout": "連線逾時",
        "err_serial_runtime": "串口連線已中斷: {e}",
        "updater_no_source": "所有更新來源都連不上",
        "updater_cancelled": "已取消",
        "updater_bad_installer": "下載內容不是有效安裝包（可能是錯誤頁面）",
        "updater_bad_url": "更新來源位址不安全（僅允許 https）",
        "net_peer_closed": "對端已中斷",
        "auto_reconnect_in": "將在 {sec}s 後自動重連…",
        "auto_reconnect_try": "嘗試重連 #{n}…",
        "cfg_export": "匯出設定…",
        "cfg_import": "匯入設定…",
        "cfg_exported": "✓ 設定已成功匯出到：{path}",
        "cfg_export_fail": "匯出失敗: {err}",
        "cfg_imported": "✓ 設定匯入成功（{n} 項），主題/語言/規則已即時生效；當前已開的連線需手動重連",
        "cfg_import_fail": "匯入失敗: {err}",
        "net_no_target": "無可發送目標",
        "net_not_open": "未連線",
        "net_send_failed": "發送失敗",
        "about": "關於",
        "help": "幫助",
        "about_desc": "iOS 風格的串口 / 網路偵錯工具（串口 + TCP/UDP）",
        "check_update": "檢查更新",
        "update_checking": "正在檢查…",
        "update_latest": "已是最新版本（v{ver}）",
        "update_found": "發現新版本 v{ver}",
        "update_download": "下載並更新",
        "update_downloading": "下載中 {pct}%",
        "update_failed": "檢查更新失敗：{e}",
        "update_dl_failed": "下載失敗：{e}",
        "update_installing": "正在啟動安裝程式，即將退出…",
        "update_open_page": "已在瀏覽器開啟下載頁",
        "update_badge": "● 可更新 v{ver}",
        "update_badge_tip": "發現新版本 v{ver}，點擊查看並更新",
        "auto_check_update": "自動檢查更新",
        "search": "搜尋",
        "search_ph": "搜尋資料區…",
        "search_prev": "上一個",
        "search_next": "下一個",
        "search_no_match": "無符合",
        "use_remote": "指定遠端",
        "use_remote_tip": "開 = 固定發往下方遠端位址；關 = 回覆最近發來資料的對端",
        "group_addr": "群播位址",
        "net_group_joined": "● 群播 {addr}",
        "err_not_multicast": "群播位址須在 224.0.0.0 ~ 239.255.255.255",
        "send_area": "發送區",
        "hex_send": "HEX 發送",
        "append_newline": "追加換行",
        "period": "定時",
        "checksum": "校驗",
        "ck_none": "無",
        "ck_sum": "和校驗",
        "ck_neg_sum": "累加和取反",
        "ck_xor": "異或",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "在這裡輸入要發送的內容...   HEX 範例: AA BB CC 01 02   動態欄位: {count} {ts} {randN}",
        "send_box_tip": (
            "動態欄位（發送時自動替換，HEX 模式輸出 2 位十六進位）：\n"
            "  {count}  序號自增 1 位元組，每次發 +1（0..FF 迴繞）\n"
            "  {ts}     當前毫秒時間戳 4 位元組（高位在前）\n"
            "  {rand}   隨機 1 位元組（= {rand1}）\n"
            "  {randN}  隨機 N 位元組，N=1..256（如 {rand4}、{rand16}）\n"
            "\n"
            "範例（HEX 模式）：在框裡輸入\n"
            "  54 {count} 00 03 FF\n"
            "第 1 次發實際發出：54 01 00 03 FF\n"
            "第 2 次：54 02 00 03 FF……\n"
            "\n"
            "發送命令歷史（↑↓）：\n"
            "  游標在首行按 ↑ 取上一條發過的命令\n"
            "  游標在末行按 ↓ 往後翻 / 回到當前草稿"
        ),
        "multi_send": "多條發送",
        "multi_send_title": "多條發送",
        "ms_add": "＋ 新增一條",
        "ms_cycle": "▶ 迴圈",
        "ms_cycle_stop": "■ 停止",
        "ms_send_one": "發送",
        "ms_nl_none": "無",
        "ms_placeholder": "資料（HEX 或文字）",
        "ms_none_checked": "請先勾選要迴圈發送的條目",
        "ms_hint": "左側管理分組；每行可獨立設 名稱 / 延時 / HEX / 換行 / 校驗。勾選多條 → 迴圈發送：發完每條等其「延時」再發下一條，到底再從頭。",
        "ms_name_ph": "名稱",
        "ms_select_all": "全選",
        "ms_delay_tip": "延時(ms)：發完本條後等這麼久再發下一條",
        "kw_highlight": "關鍵字高亮",
        "kw_title": "關鍵字高亮",
        "kw_add": "＋ 新增關鍵字",
        "kw_mode_bg": "背景",
        "kw_mode_fg": "文字",
        "kw_color": "選擇高亮顏色",
        "kw_placeholder": "關鍵字（區分大小寫）",
        "kw_hint": "資料區匹配到關鍵字就按設定顏色高亮（區分大小寫）。每條可限定 收 / 發 / 收發。",
        "kw_scope_both": "收發",
        "kw_scope_rx": "收",
        "kw_scope_tx": "發",
        "filter_highlight": "只顯高亮行",
        "kw_default_group": "預設",
        "kw_group_off": "（關閉）",
        "kw_group_label": "分組",
        "kw_new_group": "新增",
        "kw_rename_group": "重新命名",
        "kw_del_group": "刪除",
        "kw_group_name_prompt": "分組名稱：",
        "kw_group_min": "至少保留一個分組",
        "kw_new_group_default": "新分組",
        "kw_group_tip": "雙擊分組名可改名",
        "read_file": "讀取檔案",
        "send_btn": "發  送",
        "state_closed": "● 未連線",
        "stat_pkt_unit": "包",
        "stat_reset": "重置統計",
        "stat_tip_rx": "接收 RX",
        "stat_tip_tx": "發送 TX",
        "stat_total": "總量",
        "stat_packets": "封包數",
        "stat_rate": "目前速率",
        "stat_peak": "峰值速率",
        "stat_errors": "錯誤數",
        "ar_open": "自動應答",
        "ar_title": "自動應答",
        "ar_enable": "啟用自動應答",
        "ar_add": "新增規則",
        "ar_help_btn": "使用說明",
        "ar_help_title": "自動應答 — 使用說明",
        "ar_match": "收到",
        "ar_reply": "回覆",
        "ar_mode_contains": "包含",
        "ar_mode_equals": "相等",
        "ar_mode_prefix": "前綴",
        "ar_cooldown": "冷卻",
        "ar_delay": "延時",
        "ar_gap": "整包逾時",
        "ar_gap_tip": "整包：累積收到的位元組、靜默這麼久(ms)視作一整幀再匹配(Modbus 等分幀)；0=每包即時。注意分幀在匹配前進行、整條串口共用，實際取所有啟用規則中的最大值。",
        "ar_verify": "收包校驗",
        "ar_verify_tip": "對收到的整幀做校驗：尾部按所選演算法校驗通過才應答，不通過(壞幀)不回。選「無」=不校驗。本裝置=MOBUS。",
        "ar_match_ph": "匹配（HEX：?? 整位元組、A?/?5 半位元組、b:1xxxxxx1 位元遮罩 通配，如 54 ?? 03）",
        "ar_script_err": "⚠ 腳本錯誤：{e}",
        "ar_script_btn": "腳本",
        "ar_script_tip": "腳本應答：寫一段 Python（def reply(frame, ctx)）動態生成應答，替代靜態模板。空=不啟用。",
        "ar_script_mode_tip": "腳本模式：此列由腳本生成應答，靜態「回覆 / 校驗 / 校驗段」已忽略",
        "ar_script_enable": "啟用腳本",
        "ar_script_timeout": "腳本執行逾時（>{s}s），疑似死迴圈或阻塞",
        "ar_script_title": "腳本應答 — 編輯",
        "ar_script_import_title": "匯入設定 — 含腳本",
        "ar_script_import_warn": "此設定含 {n} 段腳本，匯入後它們會在規則命中時執行 Python 程式碼。\n信任來源並匯入腳本？（選「否」= 匯入設定但清空腳本）",
        "ar_script_test_ph": "測試幀 HEX（如 AA 11 22 33）→ 跑腳本看應答",
        "ar_script_none": "（腳本返回不應答）",
        "ar_script_tmpl": "def reply(frame, ctx):\n    # frame: bytes（命中幀）；ctx: state/seq/hits + crc/crc16/sum8/xor8/hexbytes/tohex\n    # 返回 bytes / list[bytes] / str / None\n    return bytes([0x06]) + frame[1:3]\n",
        "ar_script_help": "<b>腳本應答</b>：定義 <code>reply(frame, ctx)</code>，命中時動態生成應答（替代靜態回覆模板；腳本擁有整幀、<b>不自動疊校驗</b>，自己用 ctx 算）。返回 <code>bytes</code>=一幀 / <code>list[bytes]</code>=多幀 / <code>str</code>=文字 / <code>None</code>=不回。<br><b>ctx</b>：<code>.state</code> 目前狀態 · <code>.seq</code> 自增序號 · <code>.hits</code> 命中數；<code>.crc(data, width=16, poly=0x1021, init=0, refin=False, refout=False, xorout=0, byteorder='big')</code> 通用可定制 CRC；便捷 <code>.crc16</code>(Modbus) / <code>.crc8</code> / <code>.sum8</code> / <code>.xor8</code>；<code>.hexbytes('AA BB')</code>→bytes · <code>.tohex(b)</code>→'AA BB'。<br>故障注入 + 延時仍生效。⚠ 腳本在本機執行 Python；匯入他人設定中的腳本會先徵求同意。",
        "ar_mask_help": "<b>匹配語法</b>（HEX 模式）<br>• <code>AB</code> 整位元組精確　<code>??</code>/<code>XX</code> 整位元組通配<br>• <code>A?</code> / <code>?5</code> 半位元組通配（高 / 低 4 位，<code>X</code> 同 <code>?</code>）<br>• <code>b:1xxxxxx1</code> 位元遮罩（8 位 <code>0/1/x</code>，<code>x</code>=該位不關心）<br>• 混寫：<code>AA b:1001xxxx ?5</code><br>• 欄位級：<code>?? ?? ?? b:xxxxxxx1</code> + 模式「前綴」= 第 4 位元組 bit0 須為 1",
        "ar_reply_ph": "應答（{r3}=第3位元組 {r1+1}=加1 {r1^FF}=異或 {seq}=自增 {ts}=時間戳 | 分多幀）",
        "ar_btn_tip": "單擊=開啟配置，雙擊=切換開關",
        "ar_toast_on": "自動應答已開啟",
        "ar_toast_off": "自動應答已關閉",
        "ar_cooldown_tip": "冷卻(ms)：同一規則在此視窗內只響一次，防止匹配幀連續高頻到達造成應答風暴。延時是 turnaround、冷卻是限流，是兩回事。",
        "ar_frame_on": "幀頭+長度組幀",
        "ar_frame_hdr": "幀頭",
        "ar_frame_off": "長度偏移",
        "ar_frame_width": "寬",
        "ar_frame_extra": "整幀=長度+",
        "ar_cs_btn": "校驗段",
        "ar_hits": "命中 {n}",
        "ar_hits_tip": "命中次數（本次執行）：匹配 + 收包校驗通過即 +1（含被冷卻抑制的）。點「重置統計」清零。",
        "ar_test": "測試",
        "ar_reset_stats": "重置統計",
        "ar_test_title": "規則測試器（離線）",
        "ar_test_hint": "輸入一幀 HEX，點「測試」→ 看命中哪條規則、會回什麼（含佔位符替換 + 校驗段/尾部校驗計算結果）。只預覽、不傳送、不計數。",
        "ar_test_ph": "輸入一幀 HEX，如 01 06 12 34 56 78",
        "ar_test_run": "測試",
        "ar_test_bad_hex": "HEX 格式錯誤（需偶數個十六進位字元）。",
        "ar_test_no_match": "無規則命中。",
        "ar_delay_tip": "回覆延時(ms)：固定如 100，或範圍 100-300（每次隨機抖動，模擬裝置 turnaround）。",
        "ar_fault_on": "故障注入",
        "ar_fault_tip": "全域壓測主機：對所有自動應答按機率製造故障（丟包=逾時不回測重傳、錯CRC=末位元組翻轉測校驗、錯長度=砍末位元組測分幀）。被注入的幀在資料區有標記。",
        "ar_fault_drop": "丟包",
        "ar_fault_badcrc": "錯CRC",
        "ar_fault_badlen": "錯長度",
        "ar_fault_badcrc_short": "錯CRC",
        "ar_fault_badlen_short": "錯長度",
        "ar_fault_note_drop": "⚠ 故障注入·丟包（未傳送）",
        "ar_frame_desc": "有幀頭+長度欄位時勾選 → 按真實幀邊界分幀，正確處理黏包/拆包",
        "ar_fault_desc": "勾選後按機率搞壞應答 → 壓測主機的重傳與容錯",
        # C8 多步狀態機
        "ar_sm_on": "狀態機",
        "ar_sm_tip": "多步狀態機：每條規則可設「僅在某狀態應答」與「應答後跳轉」，把多條規則串成按幀序列推進的握手/會話。關閉=忽略 狀態/跳轉（等於普通模式）。",
        "ar_sm_init": "初始狀態",
        "ar_sm_init_ph": "如 S0，留空=空",
        "ar_sm_cur": "目前",
        "ar_sm_reset": "重置狀態",
        "ar_sm_desc": "按收到的幀序列推進狀態：規則可限「僅某狀態」並「應答後跳轉」",
        "ar_sm_empty": "(空)",
        "ar_when_ph": "僅狀態",
        "ar_when_tip": "僅當『目前狀態』等於這裡(可逗號分隔多個，如 S1,S2)時，此規則才會命中應答。留空=任意狀態(通配)。僅狀態機開啟時生效。",
        "ar_goto_ph": "→狀態",
        "ar_goto_tip": "此規則應答發出後，把『目前狀態』切到這裡。留空=狀態不變。僅狀態機開啟時生效。",
        "ar_test_state": "目前狀態：{s}",
        "ar_test_goto": "應答後狀態 → {s}",
        "ar_test_state_skip": "（狀態機開：目前狀態「{s}」下，此規則的「僅狀態」不匹配 → 實際不會應答）",
        "ar_sm_help_title": "多步狀態機 — 說明與例子",
        "ar_sm_help": "把多條規則串成<b>按幀序列推進</b>的狀態機，用於握手/會話流程。<br>每條規則兩個可選欄位：<br>• <b>僅狀態</b>：只有當『目前狀態』等於它（可逗號分隔多個，如 <code>S1,S2</code>）時，這條規則才有資格命中。留空=任意狀態（通配）。<br>• <b>跳轉</b>：這條規則應答發出後，把『目前狀態』切到它。留空=不變。<br><br><b>初始狀態</b>：連接 / 重置時的狀態（留空=空狀態）。<b>目前狀態</b>即時顯示，可隨時<b>重置</b>。規則仍是<b>首條命中即停</b>：同一狀態下按從上到下第一條命中的來。<br><br><b>例（三步握手）</b>，初始 <code>S0</code>：<br>規則1 僅狀態 <code>S0</code>、匹配 <code>AA 01</code> → 應答…、跳轉 <code>S1</code><br>規則2 僅狀態 <code>S1</code>、匹配 <code>AA 02</code> → 應答…、跳轉 <code>S2</code><br>規則3 僅狀態 <code>S2</code>、匹配 <code>AA 03</code> → 應答…、跳轉 <code>S0</code><br>主機必須按 01→02→03 順序握手，亂序幀不會命中。<br><b>通配技巧</b>：一條「僅狀態留空、匹配 <code>RESET</code>、跳轉 <code>S0</code>」的規則，可在任意狀態把會話拉回起點。",
        # B4 Modbus RTU 從機
        "ar_modbus": "Modbus 從機",
        "ar_modbus_tip": "把程式當成一個 Modbus RTU 從機：位址匹配 + CRC 正確就按功能碼(讀 01/02/03/04、寫 05/06/0F/10)從暫存器表自動應答主機。開啟後規則/狀態機讓位。",
        "ar_modbus_title": "Modbus RTU 從機",
        "ar_modbus_hint": "開啟後程式作為 Modbus RTU 從機：從機位址匹配 + CRC 正確就按功能碼自動應答（讀 線圈/離散/保持/輸入，寫 單個/多個，非法請求自動回例外）。下表設定各暫存器初值（未列位址預設 0）；主機的寫會改執行態，斷線/重連復位回初值。暫存器值可十進位或 0x 十六進位、逗號分隔連續填入；線圈/離散用 0/1。",
        "ar_modbus_on": "啟用 Modbus 從機",
        "ar_modbus_active": "● Modbus 從機模式開啟：下方規則 / 狀態機 / 幀頭組幀不參與（故障注入仍作用於 Modbus 回應）。點上方「Modbus 從機」可關閉。",
        "ar_modbus_addr": "從機位址",
        "ar_modbus_space": "空間",
        "ar_modbus_start": "起始位址",
        "ar_modbus_values": "值（逗號分隔，連續填入）",
        "ar_modbus_add": "新增列",
        "ar_mb_holding": "保持暫存器 4x",
        "ar_mb_input": "輸入暫存器 3x",
        "ar_mb_coil": "線圈 0x",
        "ar_mb_discrete": "離散輸入 1x",
        "ar_modbus_help_title": "Modbus 從機 — 說明與例子",
        "ar_modbus_help": "讓程式模擬一個 <b>Modbus RTU 從機</b>裝置。開啟後，收到的幀按 Modbus RTU 解析，<b>從機位址匹配且 CRC 正確</b>就按功能碼自動組裝標準回應回發：<br>• 讀：<code>01</code> 線圈 / <code>02</code> 離散輸入 / <code>03</code> 保持暫存器 / <code>04</code> 輸入暫存器<br>• 寫：<code>05</code> 單線圈 / <code>06</code> 單暫存器 / <code>0F</code> 多線圈 / <code>10</code> 多暫存器<br>• 非法功能碼 / 位址 / 資料 自動回<b>例外回應</b>（0x80|功能碼 + 例外碼）<br><br><b>暫存器表</b>：每列選「空間 + 起始位址 + 值」，值從起始位址起<b>連續填入</b>（逗號分隔）。暫存器值十進位或 <code>0x</code> 十六進位（0~65535）；線圈 / 離散用 <code>0/1</code>。未設定的位址預設 0。主機的寫（05/06/0F/10）改<b>執行態</b>暫存器，斷線 / 重連 / 關 Modbus 復位回這裡的初值。<br><br><b>例</b>：空間「保持暫存器」、起始 <code>0</code>、值 <code>0x1234, 0x5678, 100</code> → 暫存器 0/1/2 = 0x1234 / 0x5678 / 100。主機發「讀保持暫存器、起始 0、數量 2」→ 自動回 <code>01 03 04 12 34 56 78 …</code>。<br><b>注意</b>：開啟 Modbus 從機後，普通應答規則與狀態機不參與（整條引擎作為 Modbus 從機）；RTU 無幀頭，本程式按「功能碼長度 + CRC」切幀、跨包緩衝、CRC 錯自動重同步。TCP 伺服器模式會把回應精確發回請求客戶端。",
        "ar_frame_help_title": "幀頭+長度組幀 — 說明與例子",
        "ar_frame_help": "用於<b>有固定幀頭 + 長度欄位</b>的二進位協定：程式跨包緩衝收到的位元組，按幀頭定位、讀長度欄位算出整幀邊界來切分，正確處理串口/TCP 的<b>黏包/拆包</b>（比「整包靜默逾時」更準、不引入延遲）。不勾選時按「每個接收區塊=一幀」或「靜默逾時」分幀。<br><br>各項：<br>• <b>幀頭</b>：hex，如 <code>AA BB</code>，只認以它開頭的幀<br>• <b>長度偏移</b>：長度欄位在幀內的位元組位置（0 基）<br>• <b>寬</b>：長度欄位佔幾位元組（1/2/4）<br>• <b>LE/BE</b>：長度欄位的位元組序（小端/大端）<br>• <b>整幀=長度+</b>：整幀總長 = 長度欄位的值 + 這個固定開銷（幀頭/長度/校驗等沒算進長度欄位的位元組數）<br><br><b>例</b>：協定 <code>AA BB │ 長度(1B) │ 資料… │ 校驗(1B)</code>，長度欄位 = 資料位元組數。<br>設：幀頭 <code>AA BB</code>、長度偏移 <code>2</code>、寬 <code>1</code>、<code>LE</code>、整幀=長度+ <code>4</code>（=幀頭2 + 長度1 + 校驗1）。<br>收到 <code>AA BB 03 11 22 33 7E</code> → 長度=3 → 整幀=3+4=7 位元組，正好切一幀；黏了下一幀也能正確切開。",
        "ar_fault_help_title": "故障注入 — 說明與例子",
        "ar_fault_help": "全域開關，<b>對所有自動應答</b>按機率製造故障，專門<b>壓測主機</b>的重傳與容錯。每次傳送前擲骰：<br><br>• <b>丟包%</b>：整條<b>不傳</b>（=逾時不回）→ 測主機的重傳/補發邏輯<br>• <b>錯CRC%</b>：把應答<b>末位元組翻轉</b>（^0xFF），校驗必然不符 → 測主機是否丟棄壞幀<br>• <b>錯長度%</b>：<b>砍掉末位元組</b> → 測主機的長度/分幀容錯<br>三者獨立擲骰；丟包命中就不再判其餘。被注入的幀在資料區有 <code>⚠ 故障注入·…</code> 標記。<br><br><b>例 1</b>（測重傳）：你的裝置「主機沒收到應答會補發 3 次」。把<b>丟包</b>設 <code>30</code>、其餘 <code>0</code> → 平均每 3 條丟 1 條，就能看到主機觸發補發，驗證重傳是否正確。<br><b>例 2</b>（測壞幀處理）：<b>錯CRC</b> 設 <code>20</code> → 看主機收到校驗錯的幀會不會丟棄並重試。",
        "ar_fault_note_corrupt": "⚠ 故障注入·{what}",
        "ar_test_matched": "命中規則 #{n}：",
        "ar_test_verify_fail": "（命中，但收包校驗不通過 → 實際不會應答）",
        "ar_test_no_reply": "（無應答內容）",
        "ar_test_reply_bad": "（應答 HEX 解析失敗）",
        "ar_cs_tip": "內層 / 額外校驗：對應答幀的子段算校驗、寫到指定位置，在行尾「校驗」之前按順序計算（用於外層 Sum + 內層 CRC 這類兩層校驗）。",
        "ar_cs_title": "校驗段（內層 / 額外校驗）",
        "ar_cs_add": "新增段",
        "ar_cs_algo": "演算法",
        "ar_cs_start": "起始",
        "ar_cs_end": "結束",
        "ar_cs_at": "填入位置",
        "ar_cs_help": "每段對應答幀 [起始..結束]（含端點）位元組算校驗、寫到「填入位置」。\n• 順序：從上到下（內層在前）；之後再加應答行尾的「校驗」（外層）。\n• 填入位置留空 = 追加到幀尾；填數字 = 覆蓋該偏移處的位元組（應答裡需先留好佔位位元組，如 00 00）。\n• 起始 / 結束 / 位置：0 基，負數從末尾（-1 = 最後一位元組）；結束留空 = 到目前幀尾。\n例：應答 AA BB {r2} 06 12 34 00 00，加一段 ModbusCRC16 起始=2 結束=5 位置=6 → 把 CRC 覆蓋到那兩個 00；行尾「校驗」選 ADD8 → 對整幀（含內層 CRC）求和追加。",
        "ar_frame_tip": (
            "勾選後按「幀頭+長度欄位」組幀（適合 AA BB… 這類帶幀頭+長度的協定），正確處理串口"
            "黏包/拆包；優先級高於各規則的「整包」靜默逾時。\n"
            "幀頭=十六進位(如 AA BB)；長度偏移=長度欄位相對幀頭首位元組的偏移；寬=長度欄位位元組數"
            "(1/2/4)；LE/BE=長度欄位小端/大端；整幀=長度+N 表示整幀位元組數=長度欄位值+N(幀頭/序號/"
            "校驗等固定開銷)。\n例(本設備)：幀頭 AA BB · 長度偏移 4 · 寬 2 · LE · 整幀=長度+7。"),
        "ar_help": (
            "<b>用法</b>：收到資料按規則匹配 → 自動發應答。多條規則按順序，命中第一條即停（一幀最多回一條）。僅在已連線 + 總開關開啟時生效。<br>"
            "<b>匹配</b>：HEX/文字 × 包含/相等/<b>前綴</b>。HEX 模式 <code>??</code> 通配單位元組（如 <code>54 ?? 03</code>）；更細粒度可用 <b>半位元組</b> <code>A?</code>/<code>?5</code>（高/低 4 位）和 <b>位元遮罩</b> <code>b:1xxxxxx1</code>（8 位 <code>0/1/x</code>，<code>x</code>=該位不關心）。按幀首位元組區分類型 <b>請用「前綴」別用「包含」</b>。<br>"
            "<b>應答佔位符</b>（在「回覆」框寫）："
            "<code>{rN}</code>=收到幀第 N 位元組(0基) &nbsp; "
            "<code>{rN-M}</code>=第 N..M 位元組 &nbsp; "
            "<code>{rN+K}</code>=加 K(mod256) &nbsp; "
            "<code>{rN^K}</code>=XOR K &nbsp; "
            "<code>{seq}</code>=自增 1B &nbsp; "
            "<code>{ts}</code>=毫秒時間戳 4B BE。"
            "用 <code>|</code> 分多幀。<br>"
            "<b>時序</b>：<b>整包逾時</b>=靜默 N ms 視作整幀再匹配；<b>延時</b>=匹配後等待 N ms 再回；<b>冷卻</b>=同一規則 N ms 內只響一次（防風暴）。<br>"
            "<br><b>例 1（MOBUS 裝置）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = 54     HEX ✓  模式=前綴   收校驗 = MOBUS\n"
            "回覆 = 03 {r2} {r1} 00   HEX ✓  校驗 = MOBUS\n"
            "收: 54 03 01 02 ... CRC  →  回: 03 01 03 00 ... CRC（CRC 自動補）</pre>"
            "<b>例 2（心跳應答帶序號 + 時間戳）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AA   HEX ✓  模式=相等\n"
            "回覆 = 55 {ts} {seq}   HEX ✓\n"
            "收: AA  →  回: 55 F4 50 38 17 01</pre>"
            "<b>例 3（HEX 通配 + 多幀 ACK+DATA）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = 54 ?? 03   模式=包含    回覆 = 06 | 04 03 02 01    延時 = 10 ms\n"
            "任何形如 54 X 03 的幀都觸發：先回 06，10ms 後再回 04 03 02 01</pre>"
            "<b>例 4（AT 命令 — 文字模式）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AT+VER?   文字（HEX 不勾）   模式=相等\n"
            "回覆 = +VER:1.2.3\\r\\nOK\\r\\n   文字   校驗=無\n"
            "收: AT+VER?  →  回: +VER:1.2.3&lt;CR&gt;&lt;LF&gt;OK&lt;CR&gt;&lt;LF&gt;</pre>"
            "<b>例 5（多規則按幀類型分流 — 命中即停）：</b>"
            "<pre style='margin:2px 0 2px 16px'>裝置協議多種幀類型，每種一條規則按順序排：\n"
            "  規則 1: 匹配 = 54   模式=前綴   →   回 03 {r2} {r1} 00   校驗=MOBUS\n"
            "  規則 2: 匹配 = 02   模式=前綴   →   回 03 {r1} 00 00     校驗=MOBUS\n"
            "  規則 3: 匹配 = 04   模式=前綴   →   回 03 {r1} {r2} {r3} 校驗=MOBUS\n"
            "首位元組決定走哪條；前綴模式按位元組對齊，絕不會因別幀資料裡含 02 誤觸發</pre>"
            "<b>例 6（位元組範圍 + 算術 + 限流，{r1-4} {r1+1} {r2^FF}）：</b>"
            "<pre style='margin:2px 0 2px 16px'>匹配 = AA   HEX ✓   模式=相等   冷卻 = 200 ms\n"
            "回覆 = {r1-4} {r1+1} {r2^FF}   HEX ✓\n"
            "收: AA 10 20 30 40 50  →  回: 10 20 30 40 50 11 DF\n"
            "  ({r1-4}=回填第1..4位元組  {r1+1}=10+1=11  {r2^FF}=20 XOR FF = DF)\n"
            "即使裝置 10ms 發一幀，每 200ms 才回一次（冷卻把中間的吃掉）</pre>"
        ),
        "plot_open": "波形圖",
        "plot_need_lib": "波形圖需要 pyqtgraph 套件：{e}",
        "plot_title": "數據波形圖",
        "plot_help_btn": "使用說明",
        "plot_help_title": "數據波形圖 — 使用說明",
        "plot_help": (
            "<b>用法</b>：從 RX 資料裡解析數值，按通道即時繪曲線。三種解析模式按裝置協議選——文字流走「分隔符/正則」，二進位 HEX 幀走「HEX 位元組欄位」。<br>"
            "<b>分隔符模式</b>：逐行按選定分隔符切，每列 = 一條曲線。<br>"
            "<b>正則模式</b>：每行用正則匹配，每個 <b>捕獲組</b> = 一條曲線（非捕獲組用 <code>(?:…)</code>）。<br>"
            "<b>HEX 位元組欄位模式</b>：把每個收到包視作一幀（按資料區「時間分包」切），按「<code>名稱=偏移:類型</code>」從指定偏移取數。可選「幀頭」過濾：填 hex 幀頭只解析以它開頭的幀。<br>"
            "<br><b>例 1（分隔符模式 — CSV 文字流）：</b>"
            "<pre style='margin:2px 0 2px 16px'>裝置輸出：<code>1.23,4.56,7.89\\n2.34,5.67,8.90\\n…</code>\n"
            "模式 = 分隔符   分隔符 = 逗號\n"
            "→ 3 條曲線（CH0/CH1/CH2），每行一組取樣</pre>"
            "<b>例 2（正則模式 — 帶標籤的文字）：</b>"
            "<pre style='margin:2px 0 2px 16px'>裝置輸出：<code>T=23.4 H=56.7 P=1013\\n</code>\n"
            "模式 = 正則   正則 = <code>T=([\\d.]+)\\s+H=([\\d.]+)\\s+P=([\\d.]+)</code>\n"
            "→ 3 條曲線（溫度/濕度/氣壓），分別取 3 個捕獲組的數</pre>"
            "<b>例 3（HEX 位元組欄位 — 二進位協議）：</b>"
            "<pre style='margin:2px 0 2px 16px'>裝置每幀：<code>54 00 0A 04 7F …</code>（4 位元組 i16le 後跟 i16le）\n"
            "模式 = HEX 位元組欄位   欄位 = <code>X=1:i16le, Y=3:i16le</code>\n"
            "收: 54 00 0A 04 7F → X=0x0A00=2560 (le)  Y=0x047F=1151\n"
            "→ 2 條曲線（X/Y），按幀繪點</pre>"
            "<b>例 4（HEX 模式 + 幀頭過濾 — 多幀類型只畫一類）：</b>"
            "<pre style='margin:2px 0 2px 16px'>裝置混發多種幀（54 類、02 類、04 類），只想看 54 類：\n"
            "模式 = HEX 位元組欄位   <b>幀頭 = 54</b>   欄位 = <code>X=1:i16le, Y=3:i16le</code>\n"
            "其它幀（02xx…/04xx…）被過濾掉，只解析 54 開頭的</pre>"
            "<b>例 5（浮點資料 — 加速度計/陀螺儀等）：</b>"
            "<pre style='margin:2px 0 2px 16px'>每幀 12 位元組：3 個 f32le 浮點（X/Y/Z 加速度）\n"
            "模式 = HEX 位元組欄位   欄位 = <code>aX=0:f32le, aY=4:f32le, aZ=8:f32le</code>\n"
            "→ 3 條加速度曲線，每幀一個取樣點</pre>"
            "<br><b>X 軸</b>可切「樣本序號」或「時間」；<b>視窗</b>下拉控制最多保留點數（超出捲動丟棄，長跑不爆記憶體）；右上角<b>暫停/清空/匯出 CSV</b>。<br>"
            "<b>⚠️ HEX 位元組欄位模式按接收區塊分幀</b>（一塊=一幀，不拆黏包）。串口/TCP 請配合資料區<b>「時間分包」</b>讓每幀單獨成塊。"
        ),
        "plot_mode": "解析",
        "plot_mode_delim": "分隔符",
        "plot_mode_regex": "正則",
        "plot_mode_hex": "HEX 位元組",
        "plot_fields_ph": "二進制欄位 偏移:類型，如 3:u8, 9:i16le（每包當一幀）",
        "plot_fields_bad": "欄位格式錯誤，應為 偏移:類型，如 3:u8,9:i16le",
        "plot_header_ph": "幀頭 hex 可空，如 54",
        "plot_header_bad": "幀頭需為 hex，如 54 或 5400",
        "frame_open": "幀解析",
        "mbm_open": "Modbus 主機",
        "mbm_title": "Modbus 主機輪詢",
        "mbm_enable": "啟用輪詢",
        "mbm_variant": "傳輸",
        "mbm_variant_auto": "自動(依連線)",
        "mbm_echo": "本地回顯",
        "mbm_echo_tip": "序列埠介面卡會回顯發出的訊框時勾選（RS-485 半雙工常見）。開啟後先剝掉一份與請求相同的回顯再解析真實回應——尤其寫功能碼 05/06 的回顯與「寫成功」同形，不開會把回顯當成功、丟掉從機的異常。",
        "mbm_variant_rtu": "Modbus RTU",
        "mbm_variant_tcp": "Modbus TCP",
        "mbm_apply": "套用",
        "mbm_apply_first": "請先套用待生效的輪詢規則",
        "mbm_reconnect_first": "連線參數已變更或目前連線不支援輪詢，請先重連序列埠或 TCP Client",
        "mbm_add": "新增",
        "mbm_help_btn": "使用說明",
        "mbm_hint": "依每行週期輪詢從機：序列埠走 Modbus RTU、TCP Client 走 Modbus TCP。編輯規則後必須點「套用」才會生效；寫功能不會因編輯自動發送。",
        "mbm_col_name": "名稱",
        "mbm_col_unit": "從機ID",
        "mbm_col_func": "功能碼",
        "mbm_col_addr": "起始位址",
        "mbm_col_qty": "數量/寫值",
        "mbm_qty_tip": "讀類填數量；寫單 05/06 填一個值；寫多 0F/10 填多個值，逗號或空格分隔，如 100,200,300（0F 線圈填 0/1）。",
        "mbm_col_period": "週期ms",
        "mbm_col_value": "值",
        "mbm_col_status": "狀態",
        "mbm_f1": "01 讀線圈",
        "mbm_f2": "02 讀離散輸入",
        "mbm_f3": "03 讀保持暫存器",
        "mbm_f4": "04 讀輸入暫存器",
        "mbm_f5": "05 寫單線圈",
        "mbm_f6": "06 寫單暫存器",
        "mbm_f7": "0F 寫多線圈",
        "mbm_f8": "10 寫多暫存器",
        "mbm_st_ok": "OK",
        "mbm_st_timeout": "逾時",
        "mbm_st_senderr": "發送失敗",
        "mbm_st_exc": "異常 {code}",
        "mbm_st_written": "已寫 [{addr}]={val}",
        "mbm_st_written_multi": "已寫 [{addr}] ×{n}",
        "mbm_st_badresp": "回應無效",
        "mbm_st_noval": "寫值為空/非法",
        "mbm_st_badparam": "從機ID/位址/數量/週期無效",
        "mbm_st_pending": "待套用",
        "mbm_st_broadcast": "廣播已發送（無回應）",
        "mbm_st_broadcast_read": "廣播位址不支援讀取操作",
        "mbm_help_title": "Modbus 主機輪詢 — 說明",
        "mbm_help": "Modbus 主機輪詢：把本工具當 Modbus 主機，依每行設定的週期輪詢從機並即時顯示結果。\n\n• 傳輸：自動=序列埠→RTU、TCP Client→Modbus TCP；亦可強制選擇。\n• 功能碼 01-04 為讀：「數量」是暫存器/線圈個數，結果顯示十進制+十六進制。\n• 功能碼 05/06 為寫：「數量/寫值」格填寫入值（05 寫線圈填 0/1），週期到點重複寫並顯示回顯。\n• 功能碼 0F/10 為寫多：「數量/寫值」格填多個值，逗號或空格分隔，如 100,200,300（0F 線圈填 0/1）；數量由值的個數決定，任一值非法則整行不發送。\n• 半雙工：一次只在途一條請求，收到響應或逾時後再發下一條；序列埠逾時依訊框長度和鮑率動態計算。\n• 狀態：OK / 逾時 / 異常(從機回傳的異常碼) / 發送失敗 / 回應無效。\n• 本地回顯：序列埠介面卡若回顯發出的訊框(RS-485 半雙工常見)，勾選「本地回顯」——尤其寫 05/06 的回顯與「寫成功」同形，不開會把回顯當成功、丟掉從機異常。\n\n用法：先在主介面連線(序列埠或 TCP Client)，新增規則，勾選上方「啟用輪詢」即開始。\n注意：不要同時開啟「自動應答 · Modbus 從機」——一個收請求、一個發請求，混用會互相干擾。",
        "frame_title": "協議幀解析",
        "frame_hdr": "幀頭",
        "frame_fld": "欄位",
        "frame_fields_ph": "名稱=偏移:類型，如 溫度=9:i16le, 狀態=15:u8（支援 hexN/strN）",
        "frame_col_time": "時間",
        "frame_col_raw": "原始幀",
        "frame_col_rule": "規則",
        "frame_col_fields": "欄位",
        "frame_rules": "解析規則",
        "frame_add_rule": "新增規則",
        "frame_help_btn": "使用說明",
        "frame_help_title": "協議幀解析 — 使用說明",
        "frame_help": (
            "<b>用法</b>：填好「幀頭 + 欄位」規則後點「套用」。收到的每個資料區塊按幀頭前綴匹配規則解析，命中第一條即停。<br>"
            "<b>規則欄位</b>：<br>"
            "&nbsp;&nbsp;<b>幀頭</b>：hex 串如 <code>02</code>；留空 = 兜底匹配前面規則未命中的幀<br>"
            "&nbsp;&nbsp;<b>欄位定義</b>：<code>名稱=偏移:類型</code> 多個用逗號分隔，偏移從 0 數起<br>"
            "<b>類型表</b>：<br>"
            "&nbsp;&nbsp;數值：<code>u8 i8 u16le u16be i16le i16be u32le u32be i32le i32be f32le f32be f64le f64be</code><br>"
            "&nbsp;&nbsp;數值後加 <code>x</code> = HEX 顯示（如 <code>u8x</code> 顯示 0x1F 而不是 31）<br>"
            "&nbsp;&nbsp;<code>hexN</code> = N 位元組原始 HEX 串；<code>strN</code> = N 位元組 ASCII 文字<br>"
            "<br><b>例 1（最簡單 — 單位元組欄位）：</b>"
            "<pre style='margin:2px 0 2px 16px'>幀頭 = 02   欄位 = 序號=1:u8, 長度=2:u8, 類型=3:u8\n"
            "收: 02 0A 04 7F → 序號=10  長度=4  類型=127</pre>"
            "<b>例 2（多位元組數值，含端序）：</b>"
            "<pre style='margin:2px 0 2px 16px'>幀頭 = 54   欄位 = ID=1:u16le, 溫度=3:i16le, 時間=5:u32be\n"
            "收: 54 34 12 5C FF 00 00 04 D2 → ID=0x1234=4660  溫度=-164  時間=1234</pre>"
            "<b>例 3（HEX 顯示 + 原始位元組）：</b>"
            "<pre style='margin:2px 0 2px 16px'>幀頭 = AA   欄位 = 狀態=1:u8x, MAC=2:hex6, 名稱=8:str8\n"
            "收: AA 1F 00 11 22 33 44 55 CommTool → 狀態=0x1F  MAC=00 11 22 33 44 55  名稱=CommTool</pre>"
            "<b>例 4（HEX 數值，便於按位看暫存器）：</b>"
            "<pre style='margin:2px 0 2px 16px'>幀頭 = 06   欄位 = 狀態=1:u8x, 故障=2:u16lex\n"
            "收: 06 80 34 12 → 狀態=0x80  故障=0x1234</pre>"
            "<b>例 5（多規則按幀頭分流 — 命中即停）：</b>"
            "<pre style='margin:2px 0 2px 16px'>規則 1: 幀頭=54  欄位=序號=1:u8, 類型=2:u8\n"
            "規則 2: 幀頭=02  欄位=應答=1:u8\n"
            "規則 3: 幀頭=（空） 欄位=類型=0:u8x          ← 兜底\n"
            "首位元組決定走哪條；54/02 分別有專屬解析，其它幀走兜底規則</pre>"
            "<br><b>⚠️ 按接收區塊分幀</b>：一個資料區塊 = 一幀，不做跨區塊黏包拆分（半幀會缺欄位、黏連幀只解析第一幀、幀頭不在塊首則整幀丟棄）。串口/TCP 請在<b>資料區開啟「時間分包」</b>，讓每幀單獨成塊。"
        ),
        "frame_rules_ph": "每行一條：幀頭 | 欄位。例： 02 | 序號L=1:u8, 序號H=3:u8x",
        "frame_apply": "套用",
        "frame_tab_all": "全部",
        "frame_rule_bad": "規則格式錯誤：{line}",
        "frame_export_title": "匯出幀數據",
        "frame_hint": "每行一條規則「幀頭 | 欄位」，每幀按幀頭前綴匹配第一條規則解析（幀頭可空=兜底）。改完點「套用」。「全部」標籤按時間看混合幀流，其餘每規則一個分列表。數值後加 x=十六進制；支援 hexN/strN；原始幀欄便於核實。",
        "plot_sep_comma": "逗號 ,",
        "plot_sep_space": "空白",
        "plot_sep_tab": "Tab",
        "plot_sep_semicolon": "分號 ;",
        "plot_sep_auto": "自動",
        "plot_regex_ph": "擷取群組=通道，如 temp=(\\d+).*hum=(\\d+)",
        "plot_regex_bad": "正則表達式無效",
        "plot_window": "視窗點數",
        "plot_xaxis": "X 軸",
        "plot_x_index": "樣本序號",
        "plot_x_time": "時間(s)",
        "plot_pause": "暫停",
        "plot_resume": "繼續",
        "plot_clear": "清空",
        "plot_export": "匯出 CSV",
        "plot_export_title": "匯出波形數據",
        "plot_no_data": "暫無數據可匯出",
        "plot_hint": "逐行解析 RX 文字裡的數值：分隔符模式每列一條曲線，正則模式每個擷取群組一條曲線；繪圖 ~30FPS 刷新，不隨收包頻率。\n⚠️ HEX 位元組欄位模式按接收區塊分幀（一塊=一幀，不拆黏包），串口/TCP 請配合資料區「時間分包」。",
        "dlg_save_data": "儲存接收資料",
        "dlg_log_path": "選擇日誌儲存路徑",
        "dlg_load_file": "讀取發送內容",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== 日誌開始 {time} ==========\n",
        "log_footer": "\n========== 日誌結束 {time} ==========\n",
        "log_started": "即時記錄已開啟",
        "log_stopped": "即時記錄已停止",
        "saved_to": "已儲存到 {path}",
        "err_hex_odd": "HEX 長度必須為偶數",
        "err_hex_bad": "HEX 格式錯誤: {e}",
        "err_hex_invalid_chars": "非法字元 {chars}",
        "err_send_failed": "發送失敗: {e}",
        "err_checksum": "校驗計算失敗: {e}",
        "err_save_failed": "儲存失敗: {e}",
        "err_read_failed": "讀取失敗: {e}",
        "err_period_bad": "週期錯誤: {e}",
        "err_min_period": "週期最小 10ms",
        "err_open_log": "開啟失敗: {e}",
        "err_log_write": "寫日誌失敗: {e}",
        "err_rx": "接收處理出錯: {e}",
        "font_size_msg": "字號: {size} pt",
        "close_prompt": "你想怎麼關閉程式？",
        "close_minimize": "最小化到托盤",
        "close_quit": "退出程式",
        "close_cancel": "取消",
        "tray_show": "顯示視窗",
        "tray_quit": "退出",
        "tray_minimized": "{app} 已最小化到系統托盤",
        # —— 滑鼠懸停說明 ——
        "hex_display_tip": "勾選後資料按 16 進位顯示\n關閉：按文字/ASCII 顯示",
        "encoding_tip": "字元編碼（影響 RX 解碼 / TX 編碼 / 檔案載入）\n自動：UTF-8 優先，亂碼自動回退 GBK\n指定 UTF-8/GBK/GB2312/Big5 等則嚴格按選定編碼",
        "theme_tip": "資料區配色方案（終端風格）\n切換後歷史也會一併重塗為新主題色\n想全部重新整理點「清空」即可",
        "auto_wrap_tip": "行太長自動換行\n關閉：超出寬度需橫向捲動檢視",
        "show_timestamp_tip": "每個資料區塊前顯示 [年/月/日 時:分:秒 毫秒] 時間戳和 ←/→ 收發方向箭頭",
        "packet_split_tip": "收到資料後超過下方「超時」時間無新資料就開新行\n用於把短時間到達的連續資料合併顯示",
        "timeout_tip": "時間分包的間隔閾值（毫秒）\n兩次接收間隔超過此值就開新行",
        "line_split_tip": "按換行符自動分行顯示\n可選自動識別 / CRLF / LF / CR",
        "real_time_log_tip": "收發資料即時追加儲存到日誌檔案\n顯示什麼就記什麼(含時間戳/箭頭/HEX)，關閉後停止寫入",
        "max_lines_tip": "資料區最多保留的行數\n超出會丟棄最早的（防止記憶體漲爆）",
        "hex_send_tip": "把輸入框的 16 進位字串按位元組發送（如 AA BB CC）\n關閉：按文字原樣發送",
        "append_newline_tip": "每次發送後自動追加換行符\n可選 CRLF / LF / CR",
        "period_tip": "按右側間隔（毫秒）週期性自動發送目前內容",
        "checksum_tip": "發送前在末尾追加校驗位元組\n支援 和校驗/CRC8/MOBUS/CRC16/CRC32 等多種演算法",
    },
}
CHECKSUM_KEYS = ["ck_none", "ck_sum", "ck_neg_sum", "ck_xor", "ck_crc8",
                 "ck_modbus", "ck_ccitt", "ck_crc32", "ck_add16", "ck_mobus"]
