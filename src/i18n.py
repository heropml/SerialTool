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
        "hexdump_view": "HEX 转储",
        "hexdump_width_tip": "每行字节数（HEX 转储 每行显示多少字节：8 / 16 / 32 / 64）",
        "proto_highlight": "协议高亮",
        "proto_hl_tip": "按「帧解析」里定义的规则，给收到的帧各字段上色，鼠标悬浮显示字段解析（仅 HEX 显示模式生效）。\n每个收包按一帧解析（同「帧解析」）：一个收包正好一帧时最准，粘包/拆包时字段高亮可能不完整。",
        "proto_hl_no_rules": "协议高亮已开，但「帧解析」里还没有规则——请先在 功能→帧解析 中定义帧头与字段",
        "proto_hl_need_hex": "协议高亮仅在 HEX 显示模式下生效，请先开启「HEX 显示」",
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
        "flow_control": "流控",
        "dlg_close": "关闭",
        "btn_serial_open": "打开串口",
        "btn_serial_close": "关闭串口",
        "ctrl_line": "控制线",
        "ctrl_reset": "复位",
        "ctrl_reset_tip": "DTR 拉低约 120ms 再拉高，触发多数 Arduino / ESP 的自动复位；不同板子复位方式或异，可用上面 DTR / RTS 手动控制。",
        "ctrl_dtr_tip": "DTR 输出线（Data Terminal Ready）：主机拉高 / 拉低。常用于复位 MCU、控制外设使能。",
        "ctrl_rts_tip": "RTS 输出线（Request To Send）：主机拉高 / 拉低。用于硬件流控或复位 / 引脚控制。",
        "ctrl_break": "中断",
        "ctrl_break_tip": "发送中断（Break）信号（TX 线拉低约 250ms）：常用于唤醒设备、触发进入 bootloader / 命令模式等。",
        # ---- 文件传输（XMODEM / XMODEM-1K / YMODEM 收发 / 原始字节流发送）----
        "xfer_title": "文件传输",
        "xfer_hint": "XMODEM / XMODEM-1K / YMODEM 收发，或原始字节流发送文件（常用于向 bootloader 上传固件）。需先打开串口 / 连接；传输期间数据区暂停显示。",
        "xfer_help_btn": "用法说明",
        "xfer_dir": "方向",
        "xfer_dir_send": "发送（本机 → 设备）",
        "xfer_dir_recv": "接收（设备 → 本机）",
        "xfer_proto": "协议",
        "xfer_proto_xmodem": "XMODEM（128 字节 · 校验和）",
        "xfer_proto_xmodem_crc": "XMODEM（128 字节 · CRC）",
        "xfer_proto_1k": "XMODEM-1K（1024 字节 · CRC）",
        "xfer_proto_ymodem": "YMODEM（带文件名 / 大小）",
        "xfer_proto_raw": "原始字节流（直接发送）",
        "xfer_chunk": "分块大小",
        "xfer_delay": "块间延时",
        "xfer_file": "文件",
        "xfer_save": "保存",
        "xfer_browse": "浏览…",
        "xfer_start": "开始",
        "xfer_cancel": "取消",
        "xfer_pick_send": "选择要发送的文件",
        "xfer_pick_recv": "选择保存位置",
        "xfer_need_conn": "请先打开串口 / 连接",
        "xfer_need_seq_off": "请先停止自动化序列再开始文件传输",
        "xfer_need_file": "请先选择要发送的文件",
        "xfer_need_save": "请先选择保存位置",
        "xfer_read_err": "读取文件失败：{msg}",
        "xfer_write_err": "写入文件失败：{msg}",
        "xfer_log_send": "发送 {name}（{n} 字节）· {proto}",
        "xfer_log_recv": "等待发送方开始…· {proto}",
        "xfer_log_meta": "对方文件名：{name}（{n} 字节）",
        "xfer_cancelling": "正在取消…",
        "xfer_done_send": "发送完成。",
        "xfer_toast_send": "文件已发送",
        "xfer_done_recv": "已保存：{path}（{n} 字节）",
        "xfer_toast_recv": "已接收 {n} 字节",
        "xfer_cancelled": "已取消。",
        "xfer_failed": "传输失败：{msg}",
        "xfer_help_title": "文件传输 · 用法",
        "xfer_help": "<html><body><b>XMODEM / YMODEM</b> 是串口逐块传文件的经典协议，常用于给 bootloader / 单片机上传固件，或从设备取回数据。<br><br>"
                     "<b>发送（本机 → 设备）：</b><br>1) 选「发送」，点「浏览…」选文件；<br>2) 选与设备一致的协议；<br>"
                     "3) 让设备进入接收等待（如 bootloader 菜单选 XMODEM 接收），再点「开始」。<br><br>"
                     "<b>接收（设备 → 本机）：</b><br>1) 选「接收」，点「浏览…」选保存位置；<br>"
                     "2) 选协议后点「开始」；本工具会不断发起始字符等待设备开始发送。<br><br>"
                     "<b>协议怎么选（要和设备一致）：</b><br>· XMODEM（校验和）：最老，128 字节块、1 字节累加校验；<br>"
                     "· XMODEM（CRC）：128 字节块 + CRC-16，更可靠；<br>· XMODEM-1K：1024 字节块 + CRC，大文件更快；<br>"
                     "· YMODEM：在 1K 基础上先传文件名 / 大小，可自动定长。<br>"
                     "· 原始字节流：不走协议，把文件字节按「分块大小」直接发出、块间可加「间隔」延时（对端不回 ACK，纯单向）。<br><br>"
                     "<b>说明：</b>传输期间数据区暂停显示、自动应答 / 序列 / Modbus 主机暂停；中途断开连接会取消传输。</body></html>",
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
        "func_menu": "功能",
        "new_window": "新建窗口",
        "err_new_window": "打开新窗口失败：{e}",
        "profile_main": "主配置",
        "profile_n": "配置 {n}",
        "profile_busy": "{name}（使用中）",
        "profile_current": "{name}（当前窗口）",
        "new_window_auto": "新建窗口（自动分配空闲配置）",
        "open_profile": "打开配置",
        "profile_switch_busy": "该配置已在另一个窗口打开，无法切换",
        "profile_switched": "已切换到 {name}",
        "delete_profile": "删除配置",
        "delete": "删除",
        "profile_delete_title": "删除配置",
        "profile_delete_body": "确定删除 {name}？此操作不可撤销。",
        "profile_delete_busy": "该配置正被另一个窗口使用，无法删除。",
        "profile_deleted": "已删除 {name}",
        "profile_delete_fail": "删除 {name} 失败",
        "max_windows": "最多同时打开 8 个窗口，请先关闭一个再新建。",
        "seq_open": "序列",
        "seq_btn_tip": "自动化测试序列：顺序发送 → 等回包匹配 → 通过/失败",
        "seq_title": "自动化序列",
        "seq_run": "运行",
        "seq_stop": "停止",
        "seq_add": "添加步骤",
        "seq_del": "删除",
        "seq_help_btn": "使用说明 / 举例",
        "seq_help_title": "自动化序列 · 使用说明",
        "seq_help": (
            "<h3>这是什么</h3>"
            "<p>把一组「发送 → 等回包」按顺序自动跑一遍，逐步判定<b>通过 / 失败</b>，"
            "最后出汇总。适合出厂测试、设备自检、批量验机、协议联调等重复动作。</p>"
            "<h3>怎么用</h3>"
            "<p>先<b>建立连接</b>（串口 / TCP / UDP），再「添加步骤」逐条填写，点<b>运行</b>。"
            "运行期间会<b>暂停自动应答 / Modbus 主机</b>（三者共用收流，序列是主动驱动方），结束后自动恢复。"
            "连接断开会中止序列，已跑结果保留。</p>"
            "<h3>每列含义</h3>"
            "<ul>"
            "<li><b>启用</b>：取消勾选则该步跳过。</li>"
            "<li><b>名称</b>：给这步起个名，仅方便识别，可留空。</li>"
            "<li><b>发送</b>：要发出去的内容；勾右侧 <b>HEX</b> 则按十六进制解析（如 <code>01 03 00 00 00 02</code>）。留空=这步不发、只等回包。</li>"
            "<li><b>校验</b>：给发送内容自动追加校验（如 CRC16 / 累加和），与主界面一致。</li>"
            "<li><b>期望回包</b>：期望收到的内容；勾 <b>HEX</b> 则按十六进制比对。<b>留空 = 纯发送、不等回包</b>，发完即算这步完成。</li>"
            "<li><b>模式</b>：<b>包含</b>=回包里含有期望片段即通过；<b>相等</b>=整包完全一致；<b>前缀</b>=回包以期望开头。</li>"
            "<li><b>超时ms</b>：等回包的最长时间，超过还没匹配到就算这步<b>超时</b>。</li>"
            "<li><b>超时</b>（动作）：<b>停止</b>=该步超时即整体失败并结束；<b>继续</b>=记为失败但继续往下跑（最终只要有失败步，汇总仍为失败）。</li>"
            "<li><b>延时ms</b>：这步完成后、进入下一步前等待的时间（给设备处理留间隔）。</li>"
            "<li><b>结果</b>：运行时实时显示 待运行 / 等回包 / ✓用时 / ✗超时 / 已停止 / —(跳过)。</li>"
            "</ul>"
            "<h3>举例</h3>"
            "<p><b>例 1 · AT 指令自检（文本）</b></p>"
            "<ul>"
            "<li>发送 <code>AT</code>，期望 <code>OK</code>，模式=包含，超时 1000，超时动作=停止</li>"
            "<li>发送 <code>AT+CGMR</code>，期望 <code>OK</code>，模式=包含，超时 1000</li>"
            "<li>发送 <code>AT+RST</code>，期望留空（纯发送复位，不等回包），延时 2000</li>"
            "</ul>"
            "<p><b>例 2 · Modbus 读保持寄存器（HEX + CRC）</b></p>"
            "<ul>"
            "<li>发送 <code>01 03 00 00 00 02</code>（勾 HEX，校验选 CRC16 自动补两字节），"
            "期望 <code>01 03 04</code>（勾 HEX），模式=前缀，超时 500</li>"
            "</ul>"
            "<p><b>例 3 · 只发不等（初始化流程）</b></p>"
            "<ul>"
            "<li>发送 <code>init</code>，期望留空，延时 500</li>"
            "<li>发送 <code>start</code>，期望 <code>running</code>，模式=包含，超时 800</li>"
            "</ul>"
            "<h3>小贴士</h3>"
            "<ul>"
            "<li>拿不准回包完整格式时，用<b>模式=包含</b>更稳（只要含关键字即可）。</li>"
            "<li>设备回包慢就把<b>超时</b>调大；连着发多条给点<b>延时</b>避免丢包。</li>"
            "<li>某步允许失败继续测后面，就把该步<b>超时动作</b>设为<b>继续</b>。</li>"
            "<li>步骤会自动保存，下次打开还在。</li>"
            "</ul>"
        ),
        "seq_hint": "顺序执行每步：发送 → 等回包匹配（期望留空 = 纯发送不等）→ 超时按动作走。运行时暂停自动应答 / Modbus 主机。",
        "seq_col_name": "名称",
        "seq_col_send": "发送",
        "seq_col_cs": "校验",
        "seq_col_expect": "期望回包",
        "seq_col_mode": "模式",
        "seq_col_timeout": "超时ms",
        "seq_col_onfail": "超时",
        "seq_col_delay": "延时ms",
        "seq_col_result": "结果",
        "seq_send_ph": "HEX 或文本",
        "seq_expect_ph": "留空=不等回包",
        "seq_mode_contains": "包含",
        "seq_mode_equals": "相等",
        "seq_mode_prefix": "前缀",
        "seq_onfail_stop": "停止",
        "seq_onfail_continue": "继续",
        "seq_st_pending": "待运行",
        "seq_st_sent": "已发送",
        "seq_st_waiting": "等回包…",
        "seq_st_pass": "通过",
        "seq_st_fail": "超时",
        "seq_st_send_fail": "发送失败",
        "seq_st_skip": "—",
        "seq_st_stopped": "已停止",
        "seq_summary": "通过 {ok}/{total} · 用时 {ms}ms · {verdict}",
        "seq_pass": "通过 ✓",
        "seq_fail": "失败 ✗",
        "seq_running_toast": "序列开始运行…",
        "seq_running_at": "运行中 · 第 {i}/{n} 步",
        "seq_done_pass": "序列完成：通过 ✓",
        "seq_done_fail": "序列结束：失败 ✗",
        "seq_stopped": "序列已停止",
        "seq_aborted_disc": "连接断开，序列已中止",
        "seq_no_steps": "没有可运行的步骤（发送和期望都空）",
        "seq_need_conn": "请先建立连接再运行序列",
        "seq_export": "导出报告",
        "seq_export_none": "没有可导出的结果，请先运行一次序列",
        "seq_export_ok": "报告已导出：{path}",
        "seq_export_fail": "导出失败：{e}",
        "seq_report_title": "自动化序列测试报告",
        "seq_report_time": "测试时间",
        "seq_report_elapsed": "耗时",
        "seq_report_detail": "详情",
        "seq_report_skip": "跳过",
        "seq_report_fail": "失败",
        "seq_loops": "循环",
        "seq_loops_tip": "循环次数：整条序列顺序跑几轮（≥1）；配合右侧「失败即停」可某轮失败就停。",
        "seq_loops_invalid": "循环次数需为 ≥1 的整数，已按 1 处理",
        "seq_col_retry": "重试",
        "seq_retry_tip": "失败重试次数（0=不重试）；等本步「延时ms」且连续静默 50ms 后重发，任一次通过即过。",
        "seq_st_retry": "↻ 第{n}次…",
        "seq_attempt": "(第{n}次)",
        "seq_steps_menu": "步骤 ▾",
        "seq_steps_export": "导出步骤(JSON)",
        "seq_steps_import": "导入步骤(JSON)",
        "seq_steps_export_ok": "步骤已导出：{path}",
        "seq_steps_export_fail": "导出失败：{e}",
        "seq_steps_import_fail": "导入失败：{e}",
        "seq_steps_import_bad": "文件格式或字段类型不对（应为 1–500 个步骤，重试次数 0–999）",
        "seq_steps_import_large": "文件过大（最大 5MB）",
        "seq_steps_import_confirm": "将用文件中的 {n} 个步骤替换当前所有步骤，继续？",
        "seq_steps_imported": "已导入 {n} 个步骤",
        "fb_title": "帧构造器",
        "fb_template": "模板",
        "fb_add": "加字段",
        "fb_fill": "填入发送框",
        "fb_send": "发送",
        "fb_help_btn": "使用说明 / 举例",
        "fb_hint": "按字段拼帧：数值(大小端) / ascii / hex，校验·长度自动算，底部实时出 HEX。可填入发送框或直接发送。",
        "fb_out": "HEX 输出：",
        "fb_bytes": "{n} 字节",
        "fb_err": "字段错误：{e}",
        "fb_auto": "(自动)",
        "fb_col_name": "名称",
        "fb_col_type": "类型",
        "fb_col_value": "值",
        "fb_type_checksum": "校验",
        "fb_type_length": "长度",
        "fb_filled": "已填入发送框（按 HEX 发送）",
        "fb_sent": "已发送",
        "fb_send_fail": "发送失败（未连接？）",
        "fb_tmpl_custom": "自定义",
        "fb_tmpl_modbus_read": "Modbus 读",
        "fb_tmpl_modbus_write": "Modbus 写单",
        "fb_tmpl_at": "AT 命令",
        "fb_tmpl_apply": "套用模板",
        "fb_tmpl_apply_confirm": "套用「{name}」模板会覆盖当前所有字段，继续？",
        "fb_fields_limit": "字段数量最多 {n} 条，超出部分未加载",
        "fb_config_too_large": "帧构造器配置过大，已拒绝加载",
        "tb_title": "工具箱",
        "tb_tab_convert": "进制 / 编码转换",
        "tb_tab_checksum": "校验计算",
        "tb_seq_title": "字节序列",
        "tb_seq_hex": "HEX",
        "tb_seq_text": "文本",
        "tb_seq_dec": "十进制",
        "tb_seq_bin": "二进制",
        "tb_interp_title": "字节解释",
        "tb_endian": "字节序",
        "tb_interp_ascii": "ASCII",
        "tb_interp_u16": "u16",
        "tb_interp_i16": "i16",
        "tb_interp_u32": "u32",
        "tb_interp_i32": "i32",
        "tb_interp_f32": "f32",
        "tb_val_title": "单值进制",
        "tb_width": "位宽",
        "tb_signed": "有符号",
        "tb_val_dec": "十进制",
        "tb_val_hex": "HEX",
        "tb_val_bin": "二进制",
        "tb_val_oct": "八进制",
        "tb_bits": "置位 bit",
        "tb_conv_hint": "改任一框，其余实时同步；文本里无法解码的字节显示为 \\xNN。",
        "tb_ck_input": "输入数据",
        "tb_ck_text": "文本",
        "tb_ck_result": "校验结果（全算法）",
        "tb_ck_custom": "自定义 CRC",
        "tb_crc_width": "宽度",
        "tb_crc_poly": "多项式 Poly",
        "tb_crc_init": "初值 Init",
        "tb_crc_xor": "异或 XorOut",
        "tb_crc_refin": "输入反转 RefIn",
        "tb_crc_refout": "输出反转 RefOut",
        "tb_crc_order": "输出字节序",
        "tb_crc_result": "结果",
        "tb_crc_width_tip": "CRC 位宽（8/16/32/64 位），决定多项式和结果的位数。",
        "tb_crc_poly_tip": "生成多项式（不含最高位系数），十六进制填。CRC-16 常用 0x8005 或 0x1021。",
        "tb_crc_init_tip": "寄存器初值，十六进制。如 0xFFFF 或 0x0000。",
        "tb_crc_xor_tip": "最终对结果整体异或的值，十六进制。如 0x0000 或 0xFFFF。",
        "tb_crc_refin_tip": "输入反转：每个输入字节先按位镜像（bit0↔bit7）再参与运算，多数 LSB 优先的设备要开。",
        "tb_crc_refout_tip": "输出反转：最终 CRC 整体按位镜像后再输出。",
        "tb_crc_order_tip": "结果字节序：LE = 低字节在前（Modbus 常用），BE = 高字节在前。",
        "tb_ck_hint": "把数据段贴进来，看哪一行结果 == 帧尾的校验字节，即可反推设备用的校验算法。",
        "tb_help_btn": "使用说明",
        "tb_help_title": "工具箱 · 使用说明",
        "tb_help": (
            "<h3>字节序列转换</h3>"
            "<p>同一串字节的四种表示，改任意一框、其余三框实时同步：</p>"
            "<ul>"
            "<li><b>HEX</b>：十六进制字节，空格 / 逗号可省（如 <code>01 41 FF</code>）。</li>"
            "<li><b>文本</b>：按 UTF-8 解码显示；无法解码的字节显示为 <code>\\xNN</code>。</li>"
            "<li><b>十进制 / 二进制</b>：每字节一个数（0..255 / 8 位）。</li>"
            "</ul>"
            "<p>下方会按当前字节序即时解读前几个字节为 ASCII / 整数 / f32，方便看寄存器值和浮点值。</p>"
            "<p>任一框非法（奇数长度 HEX、越界十进制…）会标红，不影响其它框。</p>"
            "<h3>单值进制转换</h3>"
            "<p>一个整数在 十进制 / HEX / 二进制 / 八进制 间转，算寄存器值、地址、位掩码用：</p>"
            "<ul>"
            "<li><b>位宽</b> 8/16/32/64：HEX、二进制按位宽补零。</li>"
            "<li><b>有符号</b>：勾选后十进制按补码解读（8 位 <code>FF</code>=<code>-1</code>）；负数输入也按补码落进位宽。</li>"
            "<li><b>置位 bit</b>：可输入 <code>0, 3, 7</code> 生成位掩码，也会随数值反显当前置位。</li>"
            "</ul>"
            "<h3>校验计算</h3>"
            "<p>输入一段数据（HEX；勾「文本」则按文本编码），下方一次性列出<b>全部校验算法</b>的结果。</p>"
            "<p><b>自定义 CRC</b> 可填宽度、多项式、初值、异或值、反射和输出字节序；参数按十六进制填写。</p>"
            "<p>不知道设备用哪种校验？把帧里<b>参与校验的数据段</b>贴进来，看哪一行 == 帧里的校验字节，就反推出它用的算法。</p>"
        ),
        "fb_help_title": "帧构造器 · 使用说明",
        "fb_help": (
            "<h3>这是什么</h3>"
            "<p>按<b>字段</b>拼一帧、实时出 HEX，省得手敲十六进制。支持数值(带大小端) / 文本 / HEX，"
            "外加<b>自动字段</b>（校验、长度），并内置常见协议模板一键填充。拼好可<b>填入发送框</b>或<b>直接发送</b>。</p>"
            "<h3>字段类型</h3>"
            "<ul>"
            "<li><b>数值</b>：u8/i8/u16le/u16be/i16../u32../i32../f32le/f32be —— 类型名里的 le/be 是小端/大端；"
            "值可填十进制或 <code>0x</code> 十六进制。</li>"
            "<li><b>ascii</b>：把文本按 ASCII 编码（如 <code>AT</code>）。</li>"
            "<li><b>hex</b>：直接填十六进制字节串（如 <code>01 03</code>）。</li>"
            "<li><b>校验:算法</b>（自动）：对<b>它前面所有字节</b>算校验并追加（ModbusCRC16 / XOR8 / CRC8… 复用主程序校验）。</li>"
            "<li><b>长度:u8 / u16be</b>（自动）：值 = <b>它后面所有字节</b>的个数，按所选宽度编码。</li>"
            "</ul>"
            "<h3>模板</h3>"
            "<ul>"
            "<li><b>Modbus 读</b>：从机 / 功能(03) / 起始地址(u16be) / 数量(u16be) / CRC16。改地址数量即可。</li>"
            "<li><b>Modbus 写单</b>：从机 / 06 / 地址 / 值 / CRC16。</li>"
            "<li><b>AT 命令</b>：ascii <code>AT</code> + <code>0D 0A</code>(CR LF)。</li>"
            "</ul>"
            "<h3>小贴士</h3>"
            "<ul>"
            "<li>校验放在最后一个字段，它会覆盖前面全部；长度放在载荷前面，它数后面的字节。</li>"
            "<li>「填入发送框」会自动打开主界面的 HEX 发送开关。</li>"
            "<li>拖动每行左侧 ☰ 手柄可调整字段顺序（顺序 = 拼帧字节序）。</li>"
            "<li>拖名称/类型/值 之间的分隔条可调列宽，所有行一起变。</li>"
            "<li>字段会自动保存，下次打开还在。</li>"
            "</ul>"
        ),
        "seq_stop_on_fail": "失败即停",
        "seq_running_round": "运行中 · 第 {r}/{n_loops} 轮 · 第 {i}/{n} 步",
        "seq_summary_loops": "{rounds} · 累计 {ok}/{total} 步 · 用时 {ms}ms · {verdict}",
        "seq_rounds_frac": "通过轮 {rp}/{rt}",
        "seq_rounds_partial": "通过轮 {rp}/{rt}（计划 {loops} 轮）",
        "seq_report_round": "轮次",
        "seq_report_round_steps": "通过步",
        "seq_report_verdict": "结论",
        "about_desc": "iOS 风格的串口 / 网络调试工具（串口 + TCP/UDP）",
        "term_open": "终端",
        "term_mode": "终端模式",
        "term_btn_tip": "终端模式：发送框逐字符即时发送、数据区纯文本流显示（轻量串口终端，不解析 ANSI 颜色/全屏）",
        "term_echo": "本地回显",
        "term_enter": "回车",
        "term_mode_tip": "把发送框变成轻量串口终端：逐字符即时发送（回车 / 退格 / Tab / Ctrl+C / 方向键透传给设备），数据区按终端语义显示回显。适合登录 Linux 串口控制台敲命令；不解析全屏 TUI（vi / top）。",
        "term_echo_tip": "本地回显：把你敲的字符也显示到数据区。设备自己会回显时保持关闭（否则每个字符显示两遍）；只有设备不回显时才开。",
        "term_enter_tip": "终端模式下按回车键发送的字符：CR（\\r，多数 Linux 控制台）/ LF（\\n）/ CRLF（\\r\\n）。",
        "term_send_ph": "终端模式：直接键入即时发送（回车 / Backspace / Tab / Ctrl+C / 方向键等透传给设备）",
        "term_on": "已开启终端模式：发送框逐字符即时发送",
        "term_off": "已关闭终端模式",
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
        "update_open_dmg": "已下载并打开安装镜像，拖入「应用程序」后重启即可（首次打开见「关于」说明）",
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
        "sc_title": "脚本控制台",
        "sc_script": "脚本",
        "sc_new": "新建",
        "sc_rename": "重命名",
        "sc_delete": "删除",
        "sc_import": "导入",
        "sc_export": "导出",
        "sc_rec": "● 录制",
        "sc_rec_stop": "■ 停止录制",
        "sc_rec_name": "录制脚本",
        "sc_rec_started": "开始录制 —— 回主界面正常收发，完成后回来点「停止录制」（自动应答的回复、终端模式的按键不录）",
        "sc_rec_running": "录制中…（回主界面手动收发，操作会被翻译成脚本；期间不能运行脚本）",
        "sc_rec_full": "脚本库已满（上限 {n}），录制内容已保留 —— 删掉一个脚本后再点一次「停止录制」即可保存",
        "sc_rec_empty": "没有录到任何收发",
        "sc_rec_done": "已生成「{name}」：{tx} 次发送 / {rx} 次接收",
        "io_exclusive_busy": "另一项收发任务正在运行，请先停止后再开始",
        "sc_run": "运行",
        "sc_stop": "停止",
        "sc_clear_out": "清空输出",
        "sc_default_name": "新脚本",
        "sc_name_prompt": "脚本名称：",
        "sc_max": "脚本库最多 {n} 个",
        "sc_keep_one": "至少保留一个脚本",
        "sc_delete_warn": "确定删除脚本「{name}」？此操作不可撤销。",
        "sc_import_partial": "脚本库已满（上限 {max}），只导入了 {n} 个，跳过 {skipped} 个",
        "sc_code_too_long": "脚本超过 {n} 字符，超出部分不会被保存",
        "sc_import_bad": "文件里没有可用的脚本",
        "sc_import_title": "导入脚本",
        "sc_import_warn": "导入内容包含 {n} 个脚本，它们会在本机以本程序的权限运行。\n只在信任来源时选「是」。要导入这些脚本吗？",
        "sc_code_empty": "脚本内容为空，无法运行",
        "sc_started": "▶ 开始运行…",
        "sc_running": "运行中…（脚本独占收发流，自动应答 / Modbus 主机已暂停）",
        "sc_hint": "用 send / recv / expect / sleep / log / check 编排收发；点「?」看 API 与示例。运行时脚本独占收发流。",
        "sc_done_ok": "■ 完成：通过 {ok} / 失败 {fail}",
        "sc_done_fail": "■ 结束（有失败）：通过 {ok} / 失败 {fail}",
        "sc_done_stopped": "■ 已停止：通过 {ok} / 失败 {fail}",
        "sc_done_error": "■ 出错中断：通过 {ok} / 失败 {fail}",
        "sc_help_btn": "使用说明",
        "sc_help_title": "脚本控制台 · 使用说明",
        "sc_help": '<b>脚本控制台</b> 用 Python 脚本驱动当前连接的真实收发，适合自检、老化、批量配置、协议联调等 GUI 配置表达不了的流程。<br><br><b>API</b><br>• <code>send(data, hex=False)</code> — 发送。<code>bytes</code> 原样发；<code>hex=True</code> 时按 HEX 串解析；否则按 UTF-8 编码。<br>• <code>expect(pattern, timeout=1000, hex=False)</code> — 等到收到的数据里出现 <code>pattern</code>，返回<b>含匹配</b>的那段 bytes；超时返回 <code>None</code>。未消费的尾部留给下次。<br>• <code>recv(timeout=1000)</code> — 等任意数据，返回 bytes。<br>• <code>sleep(ms)</code> — 延时，可被「停止」打断。<br>• <code>log(*args)</code> — 输出一行到下方日志。<br>• <code>check(cond, msg)</code> — 断言：真计通过、假计失败，结束时给出「通过/失败」汇总；返回 bool 可用于分支。<br>• <code>hexs("AA BB")</code> — HEX 串转 bytes，方便手搞帧。<br><br><b>示例：AT 自检</b><pre style=\'margin:2px 0 2px 16px\'>send("AT\\r\\n")\nr = expect("OK", timeout=1000)\ncheck(r is not None, "AT 应答 OK")</pre><b>示例：Modbus 轮询 10 次</b><pre style=\'margin:2px 0 2px 16px\'>for i in range(10):\n    send(hexs("01 03 00 00 00 01 84 0A"))\n    r = expect(hexs("01 03"), timeout=500)\n    check(r is not None, "第 %d 次有响应" % (i + 1))\n    sleep(200)</pre><br><b>脚本库</b>：可保存多个命名脚本、下拉切换，随会话配置持久化；「导入 / 导出」用 JSON 分享。导入的脚本会先征求同意。<br><br><b>注意</b><br>• 运行期间脚本<b>独占收发流</b>，自动应答 / Modbus 主机自动暂停，结束后恢复（不改它们的开关）。<br>• 「停止」是<b>协作式</b>的：在 send / expect / recv / sleep 处生效。纯计算死循环（如 <code>while True: pass</code>）无法中断。<br>• 脚本以本程序权限运行，可访问文件系统等——请勿运行来源不明的脚本。',
        "dash_open": "数值仪表盘",
        "dash_title": "数值仪表盘",
        "dash_thresh": "阈值",
        "dash_thresh_ph": "阈值告警：名称:下限~上限:单位，逗号分隔，如 温度:10~40:℃, CH1:0~100:%（超限卡片变红闪烁；上/下限可留空）",
        "dash_hint": "把 RX 流解析成命名数值，每通道一张大字号卡片显示当前值；解析同波形图三模式（分隔符/正则每列 CH1/CH2…、HEX 字节按字段名）。阈值行给通道配上下限，超限卡片变红闪烁。配置与波形图相互独立。",
        "dash_help_title": "数值仪表盘 · 使用说明",
        "dash_help": "<b>数值仪表盘</b> 把 RX 流解析成命名数值通道，每通道一张大字号卡片显示<b>当前值</b>，超阈值变红闪烁。适合 IoT 传感器/电源等实时读数监看。<br><br><b>解析模式（与波形图相互独立）</b><br>• <b>分隔符</b>：每行按 逗号/空白/Tab/分号/自动 拆，每列一个通道，命名 CH1、CH2…（如 <code>36.5,72,3.30</code>）<br>• <b>正则</b>：每行用正则，每个捕获组一个通道 CH1、CH2…（如 <code>t=(\\d+).*h=(\\d+)</code>）<br>• <b>HEX 字节</b>：按「帧头 + 名称=偏移:类型」从字节取数值，字段名即通道名（如 <code>温度=0:i16be, 电压=2:u16be</code>）<br><br><b>阈值告警</b><br>阈值行填 <code>名称:下限~上限:单位</code>，逗号分隔：<br>&nbsp;&nbsp;<code>温度:10~40:℃, 电压:3.0~3.6:V, CH1:0~100:%</code><br>值 &lt; 下限 或 &gt; 上限 → 卡片变红闪烁。上限/下限可留空表示该侧不限（如 <code>温度:10~:℃</code> 只管下限）。<br><br>⚠️ HEX 模式把每个底层接收块视为一帧，不处理粘包/拆包；请确保设备或连接层按完整帧交付。",
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
        "mbm_open": "Modbus主机",
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
        # ── 串口↔网络桥接 ──
        "bg_title": "桥接转发",
        "bg_help": "在 A/B 两端之间双向透明转发数据。两端可以是串口/TCP客户端/TCP服务器/UDP任意组合。\n常用于：\n• 串口转网络（软件DTU）\n• 双串口监听/嗅探\n• TCP↔UDP 协议转换\n• 远程调试串口设备",
        "bg_type": "类型",
        "bg_port": "端口",
        "bg_baud": "波特率",
        "bg_databits": "数据位",
        "bg_parity": "校验位",
        "bg_stopbits": "停止位",
        "bg_remote_ip": "远程 IP",
        "bg_remote_port": "远程端口",
        "bg_local_ip": "本地 IP",
        "bg_local_port": "本地端口",
        "bg_spec_remote": "指定远程",
        "bg_open": "打开",
        "bg_close": "关闭",
        "bg_cancel": "取消",
        "bg_connected": "● 已连接",
        "bg_connecting": "◌ 连接中...",
        "bg_disconnected": "○ 未连接",
        "bg_start": "开始桥接",
        "bg_stop": "停止桥接",
        "bg_bridging": "● 桥接中...",
        "bg_stopped_status": "○ 已停止",
        "bg_log_title": "转发日志",
        "bg_log_enable": "记录流量",
        "bg_log_hex": "HEX",
        "bg_log_clear": "清空",
        "bg_max_lines": "最大行数:",
        "bg_recv": "RX",
        "bg_sent": "TX",
        "bg_need_both": "请先打开两侧连接",
        "bg_wait_target": "Side {side} 尚无可发送目标（TCP 客户端或 UDP 对端）",
        "bg_same_port": "两端不能使用同一个串口",
        "bg_stopped_reason": "桥接已停止: {reason}",
        "bg_need_port": "请选择串口",
        "bg_bad_addr": "请填写有效的 IP 地址和端口",
        "bg_bad_port": "请填写有效的端口号",
        "bg_refresh_ports": "刷新串口列表",
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
        "hexdump_view": "HEX dump",
        "hexdump_width_tip": "Bytes per row in the HEX dump (8 / 16 / 32 / 64)",
        "proto_highlight": "Protocol Highlight",
        "proto_hl_tip": "Color each field of incoming frames per the rules defined in Frame Parse; hover a field for its decoded value (HEX view only).\nEach received packet is parsed as one frame (like Frame Parse): most accurate when one packet is exactly one frame; highlighting may be incomplete when packets stick or fragment.",
        "proto_hl_no_rules": "Protocol highlight is on, but no rules exist in Frame Parse — define header & fields in Functions → Frame Parse first",
        "proto_hl_need_hex": "Protocol highlight works in HEX view only — enable \"HEX View\" first",
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
        "flow_control": "Flow Ctrl",
        "dlg_close": "Close",
        "btn_serial_open": "Open",
        "btn_serial_close": "Close",
        "ctrl_line": "Control lines",
        "ctrl_reset": "Reset",
        "ctrl_reset_tip": "Pulses DTR low for ~120ms then high — resets most Arduino / ESP boards; reset wiring varies, use the DTR / RTS switches above for manual control.",
        "ctrl_dtr_tip": "DTR output line (Data Terminal Ready): drive high / low. Often used to reset an MCU or enable a peripheral.",
        "ctrl_rts_tip": "RTS output line (Request To Send): drive high / low. For hardware flow control or reset / pin control.",
        "ctrl_break": "Break",
        "ctrl_break_tip": "Send a break condition (TX held low ~250ms): often used to wake a device or trigger bootloader / command mode.",
        # ---- File transfer (XMODEM / XMODEM-1K / YMODEM / raw bytes) ----
        "xfer_title": "File Transfer",
        "xfer_hint": "Send / receive files over XMODEM / XMODEM-1K / YMODEM, or send raw byte streams (often used to upload firmware to a bootloader). Open a connection first; the data view pauses during transfer.",
        "xfer_help_btn": "How to use",
        "xfer_dir": "Direction",
        "xfer_dir_send": "Send (PC → device)",
        "xfer_dir_recv": "Receive (device → PC)",
        "xfer_proto": "Protocol",
        "xfer_proto_xmodem": "XMODEM (128 B · checksum)",
        "xfer_proto_xmodem_crc": "XMODEM (128 B · CRC)",
        "xfer_proto_1k": "XMODEM-1K (1024 B · CRC)",
        "xfer_proto_ymodem": "YMODEM (with filename / size)",
        "xfer_proto_raw": "Raw bytes (direct send)",
        "xfer_chunk": "Chunk size",
        "xfer_delay": "Gap",
        "xfer_file": "File",
        "xfer_save": "Save",
        "xfer_browse": "Browse…",
        "xfer_start": "Start",
        "xfer_cancel": "Cancel",
        "xfer_pick_send": "Choose a file to send",
        "xfer_pick_recv": "Choose where to save",
        "xfer_need_conn": "Open a serial / network connection first",
        "xfer_need_seq_off": "Stop the automation sequence before starting file transfer",
        "xfer_need_file": "Pick a file to send first",
        "xfer_need_save": "Pick a save location first",
        "xfer_read_err": "Failed to read file: {msg}",
        "xfer_write_err": "Failed to write file: {msg}",
        "xfer_log_send": "Sending {name} ({n} bytes) · {proto}",
        "xfer_log_recv": "Waiting for sender… · {proto}",
        "xfer_log_meta": "Remote filename: {name} ({n} bytes)",
        "xfer_cancelling": "Cancelling…",
        "xfer_done_send": "Send complete.",
        "xfer_toast_send": "File sent",
        "xfer_done_recv": "Saved: {path} ({n} bytes)",
        "xfer_toast_recv": "Received {n} bytes",
        "xfer_cancelled": "Cancelled.",
        "xfer_failed": "Transfer failed: {msg}",
        "xfer_help_title": "File Transfer · Help",
        "xfer_help": "<html><body><b>XMODEM / YMODEM</b> are classic block-oriented serial file-transfer protocols, commonly used to upload firmware to bootloaders / MCUs or pull data back from a device.<br><br>"
                     "<b>Send (PC → device):</b><br>1) Pick \"Send\", click \"Browse…\" to choose a file;<br>2) Choose the protocol your device expects;<br>"
                     "3) Put the device into receive-wait (e.g. select XMODEM receive in its bootloader menu), then click \"Start\".<br><br>"
                     "<b>Receive (device → PC):</b><br>1) Pick \"Receive\", click \"Browse…\" to choose a save path;<br>"
                     "2) Choose the protocol and click \"Start\"; the tool repeatedly sends the start character and waits for the device to begin.<br><br>"
                     "<b>Which protocol (must match the device):</b><br>· XMODEM (checksum): oldest, 128-byte blocks, 1-byte additive checksum;<br>"
                     "· XMODEM (CRC): 128-byte blocks + CRC-16, more reliable;<br>· XMODEM-1K: 1024-byte blocks + CRC, faster for large files;<br>"
                     "· YMODEM: sends filename / size first (auto length) on top of 1K.<br>"
                     "· Raw bytes: no protocol — dumps the file's bytes directly in \"chunk size\" pieces with an optional inter-chunk \"gap\" (no ACKs, one-way).<br><br>"
                     "<b>Note:</b> during transfer the data view, auto-reply, sequence and Modbus master are paused; disconnecting cancels the transfer.</body></html>",
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
        "func_menu": "Features",
        "new_window": "New Window",
        "err_new_window": "Failed to open a new window: {e}",
        "profile_main": "Main config",
        "profile_n": "Config {n}",
        "profile_busy": "{name} (in use)",
        "profile_current": "{name} (current window)",
        "new_window_auto": "New Window (auto-assign free config)",
        "open_profile": "Open Config",
        "profile_switch_busy": "That config is open in another window; can't switch to it.",
        "profile_switched": "Switched to {name}",
        "delete_profile": "Delete Config",
        "delete": "Delete",
        "profile_delete_title": "Delete config",
        "profile_delete_body": "Delete {name}? This cannot be undone.",
        "profile_delete_busy": "That config is in use by another window; can't delete it.",
        "profile_deleted": "Deleted {name}",
        "profile_delete_fail": "Failed to delete {name}",
        "max_windows": "Up to 8 windows can be open at once. Close one before opening another.",
        "seq_open": "Sequence",
        "seq_btn_tip": "Automated test sequence: send → wait for response → pass/fail",
        "seq_title": "Automated Sequence",
        "seq_run": "Run",
        "seq_stop": "Stop",
        "seq_add": "Add Step",
        "seq_del": "Delete",
        "seq_help_btn": "How to use / examples",
        "seq_help_title": "Automated Sequence · Guide",
        "seq_help": (
            "<h3>What it is</h3>"
            "<p>Runs a list of «send → wait for response» steps in order, judging each one "
            "<b>PASS / FAIL</b> and printing a summary. Great for factory tests, device self-checks, "
            "batch verification and protocol bring-up — any repetitive sequence.</p>"
            "<h3>How to use</h3>"
            "<p>First <b>open a connection</b> (serial / TCP / UDP), then «Add Step», fill each row, and hit <b>Run</b>. "
            "While running, <b>Auto-reply / Modbus master are paused</b> (they share the same receive stream; the "
            "sequence is the active driver) and resume when it ends. Disconnecting aborts the run; results are kept.</p>"
            "<h3>Columns</h3>"
            "<ul>"
            "<li><b>Enable</b>: unchecked → step is skipped.</li>"
            "<li><b>Name</b>: a label for the step, optional.</li>"
            "<li><b>Send</b>: what to transmit; tick <b>HEX</b> to parse as hex (e.g. <code>01 03 00 00 00 02</code>). Empty = don't send, only wait.</li>"
            "<li><b>Checksum</b>: auto-append a checksum (CRC16 / sum, etc.) to the sent bytes, same as the main window.</li>"
            "<li><b>Expect</b>: the response to look for; tick <b>HEX</b> to compare as hex. <b>Empty = send only, no wait</b> — the step completes once sent.</li>"
            "<li><b>Mode</b>: <b>Contains</b> = response includes the expected fragment; <b>Equals</b> = whole frame matches; <b>Prefix</b> = response starts with expected.</li>"
            "<li><b>Timeout ms</b>: max time to wait for a match; exceeding it marks the step <b>timed out</b>.</li>"
            "<li><b>On timeout</b>: <b>Stop</b> = fail the whole run and end; <b>Continue</b> = mark failed but keep going (any failed step still makes the summary FAIL).</li>"
            "<li><b>Delay ms</b>: wait after this step before the next one (gives the device time).</li>"
            "<li><b>Result</b>: live status — pending / waiting / ✓time / ✗timeout / stopped / —(skipped).</li>"
            "</ul>"
            "<h3>Examples</h3>"
            "<p><b>Ex 1 · AT self-check (text)</b></p>"
            "<ul>"
            "<li>Send <code>AT</code>, expect <code>OK</code>, mode Contains, timeout 1000, on-timeout Stop</li>"
            "<li>Send <code>AT+CGMR</code>, expect <code>OK</code>, mode Contains, timeout 1000</li>"
            "<li>Send <code>AT+RST</code>, expect empty (send-only reset), delay 2000</li>"
            "</ul>"
            "<p><b>Ex 2 · Modbus read holding registers (HEX + CRC)</b></p>"
            "<ul>"
            "<li>Send <code>01 03 00 00 00 02</code> (tick HEX, Checksum = CRC16 auto-appends 2 bytes), "
            "expect <code>01 03 04</code> (tick HEX), mode Prefix, timeout 500</li>"
            "</ul>"
            "<p><b>Ex 3 · Send-only init flow</b></p>"
            "<ul>"
            "<li>Send <code>init</code>, expect empty, delay 500</li>"
            "<li>Send <code>start</code>, expect <code>running</code>, mode Contains, timeout 800</li>"
            "</ul>"
            "<h3>Tips</h3>"
            "<ul>"
            "<li>Unsure of the exact frame? <b>Contains</b> is safest (just needs the keyword).</li>"
            "<li>Slow device → raise <b>Timeout</b>; back-to-back sends → add <b>Delay</b> to avoid drops.</li>"
            "<li>Want to keep testing past a failure? Set that step's on-timeout to <b>Continue</b>.</li>"
            "<li>Steps are saved automatically and restored next time.</li>"
            "</ul>"
        ),
        "seq_hint": "Runs each step in order: send → wait for a matching response (leave Expect empty = send only) → on timeout act. Auto-reply / Modbus master are paused while running.",
        "seq_col_name": "Name",
        "seq_col_send": "Send",
        "seq_col_cs": "Checksum",
        "seq_col_expect": "Expect",
        "seq_col_mode": "Mode",
        "seq_col_timeout": "Timeout ms",
        "seq_col_onfail": "On timeout",
        "seq_col_delay": "Delay ms",
        "seq_col_result": "Result",
        "seq_send_ph": "HEX or text",
        "seq_expect_ph": "empty = no wait",
        "seq_mode_contains": "Contains",
        "seq_mode_equals": "Equals",
        "seq_mode_prefix": "Prefix",
        "seq_onfail_stop": "Stop",
        "seq_onfail_continue": "Continue",
        "seq_st_pending": "pending",
        "seq_st_sent": "sent",
        "seq_st_waiting": "waiting…",
        "seq_st_pass": "pass",
        "seq_st_fail": "timeout",
        "seq_st_send_fail": "send failed",
        "seq_st_skip": "—",
        "seq_st_stopped": "stopped",
        "seq_summary": "Passed {ok}/{total} · {ms}ms · {verdict}",
        "seq_pass": "PASS ✓",
        "seq_fail": "FAIL ✗",
        "seq_running_toast": "Sequence started…",
        "seq_running_at": "Running · step {i}/{n}",
        "seq_done_pass": "Sequence done: PASS ✓",
        "seq_done_fail": "Sequence ended: FAIL ✗",
        "seq_stopped": "Sequence stopped",
        "seq_aborted_disc": "Connection lost, sequence aborted",
        "seq_no_steps": "No runnable steps (send and expect both empty)",
        "seq_need_conn": "Connect first before running the sequence",
        "seq_export": "Export Report",
        "seq_export_none": "No results to export — run the sequence first",
        "seq_export_ok": "Report exported: {path}",
        "seq_export_fail": "Export failed: {e}",
        "seq_report_title": "Automated Sequence Test Report",
        "seq_report_time": "Test time",
        "seq_report_elapsed": "Elapsed",
        "seq_report_detail": "Detail",
        "seq_report_skip": "Skipped",
        "seq_report_fail": "Failed",
        "seq_loops": "Loops",
        "seq_loops_tip": "Loop count: how many times the whole sequence runs (>=1); pair with Stop-on-fail on the right.",
        "seq_loops_invalid": "Loop count must be an integer >=1; using 1",
        "seq_col_retry": "Retry",
        "seq_retry_tip": "Retries on failure (0 = none); resends after this step's Delay and 50 ms of line silence.",
        "seq_st_retry": "↻ try {n}…",
        "seq_attempt": "(try {n})",
        "seq_steps_menu": "Steps ▾",
        "seq_steps_export": "Export steps (JSON)",
        "seq_steps_import": "Import steps (JSON)",
        "seq_steps_export_ok": "Steps exported: {path}",
        "seq_steps_export_fail": "Export failed: {e}",
        "seq_steps_import_fail": "Import failed: {e}",
        "seq_steps_import_bad": "Bad format or field types (expected 1–500 steps; retries 0–999)",
        "seq_steps_import_large": "File is too large (maximum 5 MB)",
        "seq_steps_import_confirm": "Replace all current steps with {n} step(s) from the file?",
        "seq_steps_imported": "Imported {n} step(s)",
        "fb_title": "Frame Builder",
        "fb_template": "Template",
        "fb_add": "Add field",
        "fb_fill": "To send box",
        "fb_send": "Send",
        "fb_help_btn": "How to use / examples",
        "fb_hint": "Build a frame field by field: numbers (endian) / ascii / hex, with auto checksum & length; live HEX below. Fill the send box or send directly.",
        "fb_out": "HEX output:",
        "fb_bytes": "{n} bytes",
        "fb_err": "Field error: {e}",
        "fb_auto": "(auto)",
        "fb_col_name": "Name",
        "fb_col_type": "Type",
        "fb_col_value": "Value",
        "fb_type_checksum": "Checksum",
        "fb_type_length": "Length",
        "fb_filled": "Filled into send box (HEX mode)",
        "fb_sent": "Sent",
        "fb_send_fail": "Send failed (not connected?)",
        "fb_tmpl_custom": "Custom",
        "fb_tmpl_modbus_read": "Modbus read",
        "fb_tmpl_modbus_write": "Modbus write",
        "fb_tmpl_at": "AT command",
        "fb_tmpl_apply": "Apply template",
        "fb_tmpl_apply_confirm": "Applying the \"{name}\" template overwrites all current fields. Continue?",
        "fb_fields_limit": "Up to {n} fields are allowed; extra fields were not loaded",
        "fb_config_too_large": "Frame Builder configuration is too large and was not loaded",
        "tb_title": "Toolbox",
        "tb_tab_convert": "Convert",
        "tb_tab_checksum": "Checksum",
        "tb_seq_title": "Byte sequence",
        "tb_seq_hex": "HEX",
        "tb_seq_text": "Text",
        "tb_seq_dec": "Decimal",
        "tb_seq_bin": "Binary",
        "tb_interp_title": "Byte decode",
        "tb_endian": "Endian",
        "tb_interp_ascii": "ASCII",
        "tb_interp_u16": "u16",
        "tb_interp_i16": "i16",
        "tb_interp_u32": "u32",
        "tb_interp_i32": "i32",
        "tb_interp_f32": "f32",
        "tb_val_title": "Single value",
        "tb_width": "Width",
        "tb_signed": "Signed",
        "tb_val_dec": "Decimal",
        "tb_val_hex": "HEX",
        "tb_val_bin": "Binary",
        "tb_val_oct": "Octal",
        "tb_bits": "Set bits",
        "tb_conv_hint": "Edit any field and the rest sync live; bytes that can't be decoded as text show as \\xNN.",
        "tb_ck_input": "Input",
        "tb_ck_text": "Text",
        "tb_ck_result": "Checksums (all algorithms)",
        "tb_ck_custom": "Custom CRC",
        "tb_crc_width": "Width",
        "tb_crc_poly": "Poly",
        "tb_crc_init": "Init",
        "tb_crc_xor": "XorOut",
        "tb_crc_refin": "RefIn",
        "tb_crc_refout": "RefOut",
        "tb_crc_order": "Byte order",
        "tb_crc_result": "Result",
        "tb_crc_width_tip": "CRC width (8/16/32/64 bits) — sets the size of the polynomial and result.",
        "tb_crc_poly_tip": "Generator polynomial (top bit omitted), in hex. Common CRC-16: 0x8005 or 0x1021.",
        "tb_crc_init_tip": "Register initial value, in hex. E.g. 0xFFFF or 0x0000.",
        "tb_crc_xor_tip": "Final value XORed with the whole result, in hex. E.g. 0x0000 or 0xFFFF.",
        "tb_crc_refin_tip": "Reflect input: each input byte is bit-mirrored (bit0↔bit7) before processing; needed for most LSB-first devices.",
        "tb_crc_refout_tip": "Reflect output: the final CRC is bit-mirrored before output.",
        "tb_crc_order_tip": "Result byte order: LE = low byte first (common for Modbus), BE = high byte first.",
        "tb_ck_hint": "Paste a data section; whichever row equals the frame's trailing checksum byte(s) tells you which algorithm the device uses.",
        "tb_help_btn": "Guide",
        "tb_help_title": "Toolbox · Guide",
        "tb_help": (
            "<h3>Byte-sequence conversion</h3>"
            "<p>Four representations of the same bytes; edit any field and the other three sync live:</p>"
            "<ul>"
            "<li><b>HEX</b>: hex bytes, spaces / commas optional (e.g. <code>01 41 FF</code>).</li>"
            "<li><b>Text</b>: decoded as UTF-8; bytes that can't be decoded show as <code>\\xNN</code>.</li>"
            "<li><b>Decimal / Binary</b>: one number per byte (0..255 / 8 bits).</li>"
            "</ul>"
            "<p>The decode area interprets the leading bytes as ASCII / integers / f32 with the selected endianness.</p>"
            "<p>An invalid field (odd-length HEX, out-of-range decimal…) turns red and doesn't affect the others.</p>"
            "<h3>Single-value conversion</h3>"
            "<p>One integer across Decimal / HEX / Binary / Octal — for register values, addresses, bit masks:</p>"
            "<ul>"
            "<li><b>Width</b> 8/16/32/64: HEX and binary are zero-padded to the width.</li>"
            "<li><b>Signed</b>: decimal is read as two's complement (8-bit <code>FF</code>=<code>-1</code>); negative input also wraps into the width.</li>"
            "<li><b>Set bits</b>: type <code>0, 3, 7</code> to build a mask; it also reflects the current value.</li>"
            "</ul>"
            "<h3>Checksum</h3>"
            "<p>Enter data (HEX, or tick «Text» to encode as text); all checksum algorithms are listed below at once.</p>"
            "<p><b>Custom CRC</b> accepts width, polynomial, init, xorout, reflection and output byte order; parameters are hexadecimal.</p>"
            "<p>Not sure which checksum a device uses? Paste the <b>data covered by the checksum</b> and see which row equals the frame's checksum byte(s) — that's the algorithm.</p>"
        ),
        "fb_help_title": "Frame Builder · Guide",
        "fb_help": (
            "<h3>What it is</h3>"
            "<p>Assemble a frame by <b>fields</b> and get live HEX — no hand-typing hex. Supports numbers "
            "(with endianness) / text / hex, plus <b>auto fields</b> (checksum, length), and built-in protocol "
            "templates. Then <b>fill the send box</b> or <b>send directly</b>.</p>"
            "<h3>Field types</h3>"
            "<ul>"
            "<li><b>Numeric</b>: u8/i8/u16le/u16be/i16../u32../i32../f32le/f32be — le/be in the type name = "
            "little/big endian; value as decimal or <code>0x</code> hex.</li>"
            "<li><b>ascii</b>: encode text as ASCII (e.g. <code>AT</code>).</li>"
            "<li><b>hex</b>: raw hex bytes (e.g. <code>01 03</code>).</li>"
            "<li><b>Checksum:algo</b> (auto): over <b>all bytes before it</b> (ModbusCRC16 / XOR8 / CRC8…).</li>"
            "<li><b>Length:u8 / u16be</b> (auto): value = count of <b>all bytes after it</b>, at the chosen width.</li>"
            "</ul>"
            "<h3>Templates</h3>"
            "<ul>"
            "<li><b>Modbus read</b>: unit / func(03) / addr(u16be) / qty(u16be) / CRC16.</li>"
            "<li><b>Modbus write</b>: unit / 06 / addr / value / CRC16.</li>"
            "<li><b>AT command</b>: ascii <code>AT</code> + <code>0D 0A</code> (CR LF).</li>"
            "</ul>"
            "<h3>Tips</h3>"
            "<ul>"
            "<li>Put checksum last (covers all preceding); put length before the payload (counts what follows).</li>"
            "<li>«To send box» turns on the main HEX-send switch automatically.</li>"
            "<li>Drag the ☰ handle on the left of a row to reorder fields (order = byte order).</li>"
            "<li>Drag the dividers between Name/Type/Value to resize columns; all rows follow.</li>"
            "<li>Fields are saved automatically and restored next time.</li>"
            "</ul>"
        ),
        "seq_stop_on_fail": "Stop on fail",
        "seq_running_round": "Running · round {r}/{n_loops} · step {i}/{n}",
        "seq_summary_loops": "{rounds} · {ok}/{total} steps · {ms}ms · {verdict}",
        "seq_rounds_frac": "Passed rounds {rp}/{rt}",
        "seq_rounds_partial": "Passed rounds {rp}/{rt} (of {loops} planned)",
        "seq_report_round": "Round",
        "seq_report_round_steps": "Passed steps",
        "seq_report_verdict": "Verdict",
        "about_desc": "An iOS-style serial & network debugging tool (Serial + TCP/UDP)",
        "term_open": "Terminal",
        "term_mode": "Terminal mode",
        "term_btn_tip": "Terminal mode: send keystrokes instantly, show raw text stream (lightweight serial terminal; no ANSI color/full-screen)",
        "term_echo": "Local echo",
        "term_enter": "Enter",
        "term_mode_tip": "Turn the send box into a lightweight serial terminal: keystrokes are sent instantly (Enter / Backspace / Tab / Ctrl+C / arrows pass through) and the data area renders the echo like a terminal. Great for a Linux serial console; full-screen TUIs (vi / top) aren't emulated.",
        "term_echo_tip": "Local echo: also show your keystrokes in the data area. Keep it OFF when the device echoes (otherwise every character shows twice); turn it ON only for devices that don't echo.",
        "term_enter_tip": "What the Enter key sends in terminal mode: CR (\\r, most Linux consoles) / LF (\\n) / CRLF (\\r\\n).",
        "term_send_ph": "Terminal mode: type to send instantly (Enter / Backspace / Tab / Ctrl+C / arrow keys passed to the device)",
        "term_on": "Terminal mode on: keystrokes sent instantly",
        "term_off": "Terminal mode off",
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
        "update_open_dmg": "Downloaded and opened the disk image — drag into Applications and relaunch (first open: see About)",
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
        "sc_title": "Script Console",
        "sc_script": "Script",
        "sc_new": "New",
        "sc_rename": "Rename",
        "sc_delete": "Delete",
        "sc_import": "Import",
        "sc_export": "Export",
        "sc_rec": "● Record",
        "sc_rec_stop": "■ Stop Recording",
        "sc_rec_name": "Recorded",
        "sc_rec_started": "Recording — go to the main window and work as usual, then come back and click Stop Recording (auto-reply responses and terminal-mode keystrokes are not recorded)",
        "sc_rec_running": "Recording… (send/receive in the main window; your actions become a script. Running a script is disabled meanwhile)",
        "sc_rec_full": "Script library is full (max {n}); the recording is kept — delete a script and click Record again to save it",
        "sc_rec_empty": "Nothing was recorded",
        "sc_rec_done": "Created \u300c{name}\u300d: {tx} sent / {rx} received",
        "io_exclusive_busy": "Another RX/TX task is running; stop it before starting this one",
        "sc_run": "Run",
        "sc_stop": "Stop",
        "sc_clear_out": "Clear Output",
        "sc_default_name": "New Script",
        "sc_name_prompt": "Script name:",
        "sc_max": "At most {n} scripts in the library",
        "sc_keep_one": "Keep at least one script",
        "sc_delete_warn": "Delete script \u300c{name}\u300d? This cannot be undone.",
        "sc_import_partial": "Script library is full (max {max}): imported {n}, skipped {skipped}",
        "sc_code_too_long": "Script exceeds {n} characters; the excess will not be saved",
        "sc_import_bad": "No usable scripts in that file",
        "sc_import_title": "Import Scripts",
        "sc_import_warn": "The import contains {n} script(s); they will run locally with this app's privileges.\nChoose Yes only if you trust the source. Import them?",
        "sc_code_empty": "The script is empty and cannot be run",
        "sc_started": "▶ Running…",
        "sc_running": "Running… (the script owns the RX/TX stream; auto-reply / Modbus master are paused)",
        "sc_hint": "Drive the link with send / recv / expect / sleep / log / check — click 「?」 for the API and examples. While running, the script owns the stream.",
        "sc_done_ok": "■ Done: {ok} passed / {fail} failed",
        "sc_done_fail": "■ Finished with failures: {ok} passed / {fail} failed",
        "sc_done_stopped": "■ Stopped: {ok} passed / {fail} failed",
        "sc_done_error": "■ Aborted on error: {ok} passed / {fail} failed",
        "sc_help_btn": "Help",
        "sc_help_title": "Script Console · Help",
        "sc_help": '<b>Script Console</b> drives real traffic on the current connection with a Python script — for self-tests, burn-in, bulk provisioning and protocol bring-up that a GUI form cannot express.<br><br><b>API</b><br>• <code>send(data, hex=False)</code> — send. <code>bytes</code> go out as-is; with <code>hex=True</code> the string is parsed as HEX; otherwise it is UTF-8 encoded.<br>• <code>expect(pattern, timeout=1000, hex=False)</code> — wait until <code>pattern</code> appears and return everything up to and <b>including</b> the match; <code>None</code> on timeout. Whatever follows is kept for the next call.<br>• <code>recv(timeout=1000)</code> — wait for any data, returns bytes.<br>• <code>sleep(ms)</code> — delay; interruptible by Stop.<br>• <code>log(*args)</code> — print a line to the output pane.<br>• <code>check(cond, msg)</code> — assertion: counts pass/fail and reports a summary at the end; returns a bool you can branch on.<br>• <code>hexs("AA BB")</code> — HEX string to bytes.<br><br><b>Example: AT self-test</b><pre style=\'margin:2px 0 2px 16px\'>send("AT\\r\\n")\nr = expect("OK", timeout=1000)\ncheck(r is not None, "AT answered OK")</pre><b>Example: poll Modbus 10 times</b><pre style=\'margin:2px 0 2px 16px\'>for i in range(10):\n    send(hexs("01 03 00 00 00 01 84 0A"))\n    r = expect(hexs("01 03"), timeout=500)\n    check(r is not None, "reply %d" % (i + 1))\n    sleep(200)</pre><br><b>Script library</b>: keep several named scripts and switch with the dropdown; they persist with the session config. Import / Export share them as JSON — imports ask for confirmation first.<br><br><b>Notes</b><br>• While running the script <b>owns the stream</b>; auto-reply / Modbus master pause automatically and resume afterwards.<br>• Stop is <b>cooperative</b>: it takes effect inside send / expect / recv / sleep. A pure compute loop (<code>while True: pass</code>) cannot be interrupted.<br>• Scripts run with this app\'s privileges and can reach the file system — never run scripts from an untrusted source.',
        "dash_open": "Dashboard",
        "dash_title": "Numeric Dashboard",
        "dash_thresh": "Thresholds",
        "dash_thresh_ph": "Alerts: name:lo~hi:unit, comma-separated, e.g. Temp:10~40:℃, CH1:0~100:% (out-of-range tiles blink red; lo/hi optional)",
        "dash_hint": "Parses the RX stream into named numeric channels; each shows its current value as a large tile. Same three modes as Plot (delimiter/regex → CH1/CH2…, HEX bytes → by field name). The thresholds line sets per-channel limits; out-of-range tiles blink red. Config is independent from Plot.",
        "dash_help_title": "Numeric Dashboard · Help",
        "dash_help": "<b>Numeric Dashboard</b> parses the RX stream into named numeric channels and shows each channel's <b>current value</b> as a large tile, turning red when out of range. Great for live sensor / power readings.<br><br><b>Parse modes (independent from Plot)</b><br>• <b>Delimiter</b>: split each line by comma/space/Tab/semicolon/auto, one channel per column, named CH1, CH2… (e.g. <code>36.5,72,3.30</code>)<br>• <b>Regex</b>: one channel per capture group, CH1, CH2… (e.g. <code>t=(\\d+).*h=(\\d+)</code>)<br>• <b>HEX bytes</b>: read numbers by 'header + name=offset:type', field name = channel name (e.g. <code>Temp=0:i16be, Volt=2:u16be</code>)<br><br><b>Threshold alerts</b><br>Fill the thresholds line with <code>name:lo~hi:unit</code>, comma-separated:<br>&nbsp;&nbsp;<code>Temp:10~40:℃, Volt:3.0~3.6:V, CH1:0~100:%</code><br>value &lt; lo or &gt; hi → tile blinks red. Leave lo or hi empty for one-sided (e.g. <code>Temp:10~:℃</code> lower bound only).<br><br>⚠️ HEX mode treats each low-level receive block as one frame and does not de-frame sticky or fragmented packets; ensure the device or transport delivers complete frames.",
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
        # ── Serial↔Network Bridge ──
        "bg_title": "Bridge / Forward",
        "bg_help": "Bidirectionally forward data between Side A and Side B.\nBoth sides can be Serial, TCP Client, TCP Server, or UDP in any combination.\nCommon use cases:\n• Serial-to-Network (software DTU)\n• Dual-serial monitoring/sniffing\n• TCP↔UDP protocol conversion\n• Remote debugging of serial devices",
        "bg_type": "Type",
        "bg_port": "Port",
        "bg_baud": "Baud Rate",
        "bg_databits": "Data Bits",
        "bg_parity": "Parity",
        "bg_stopbits": "Stop Bits",
        "bg_remote_ip": "Remote IP",
        "bg_remote_port": "Remote Port",
        "bg_local_ip": "Local IP",
        "bg_local_port": "Local Port",
        "bg_spec_remote": "Specify Remote",
        "bg_open": "Open",
        "bg_close": "Close",
        "bg_cancel": "Cancel",
        "bg_connected": "● Connected",
        "bg_connecting": "◌ Connecting...",
        "bg_disconnected": "○ Disconnected",
        "bg_start": "Start Bridge",
        "bg_stop": "Stop Bridge",
        "bg_bridging": "● Bridging...",
        "bg_stopped_status": "○ Stopped",
        "bg_log_title": "Forwarding Log",
        "bg_log_enable": "Log Traffic",
        "bg_log_hex": "HEX",
        "bg_log_clear": "Clear",
        "bg_max_lines": "Max lines:",
        "bg_recv": "RX",
        "bg_sent": "TX",
        "bg_need_both": "Please connect both sides first",
        "bg_wait_target": "Side {side} has no send target yet (TCP client or UDP peer)",
        "bg_same_port": "Cannot use the same serial port on both sides",
        "bg_stopped_reason": "Bridge stopped: {reason}",
        "bg_need_port": "Please select a serial port",
        "bg_bad_addr": "Please enter a valid IP address and port",
        "bg_bad_port": "Please enter a valid port number",
        "bg_refresh_ports": "Refresh serial port list",
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
        "hexdump_view": "HEX 轉儲",
        "hexdump_width_tip": "每行位元組數（HEX 轉儲 每行顯示多少位元組：8 / 16 / 32 / 64）",
        "proto_highlight": "協定高亮",
        "proto_hl_tip": "按「幀解析」裡定義的規則，給收到的幀各欄位上色，滑鼠懸浮顯示欄位解析（僅 HEX 顯示模式生效）。\n每個收包按一幀解析（同「幀解析」）：一個收包正好一幀時最準，粘包/拆包時欄位高亮可能不完整。",
        "proto_hl_no_rules": "協定高亮已開，但「幀解析」裡還沒有規則——請先在 功能→幀解析 中定義幀頭與欄位",
        "proto_hl_need_hex": "協定高亮僅在 HEX 顯示模式下生效，請先開啟「HEX 顯示」",
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
        "flow_control": "流控",
        "dlg_close": "關閉",
        "btn_serial_open": "開啟串口",
        "btn_serial_close": "關閉串口",
        "ctrl_line": "控制線",
        "ctrl_reset": "復位",
        "ctrl_reset_tip": "DTR 拉低約 120ms 再拉高，觸發多數 Arduino / ESP 的自動復位；不同板子復位方式或異，可用上方 DTR / RTS 手動控制。",
        "ctrl_dtr_tip": "DTR 輸出線（Data Terminal Ready）：主機拉高 / 拉低。常用於復位 MCU、控制外設致能。",
        "ctrl_rts_tip": "RTS 輸出線（Request To Send）：主機拉高 / 拉低。用於硬體流控或復位 / 腳位控制。",
        "ctrl_break": "中斷",
        "ctrl_break_tip": "發送中斷（Break）訊號（TX 線拉低約 250ms）：常用於喚醒裝置、觸發進入 bootloader / 命令模式等。",
        # ---- 檔案傳輸（XMODEM / XMODEM-1K / YMODEM 收發 / 原始位元組流傳送）----
        "xfer_title": "檔案傳輸",
        "xfer_hint": "XMODEM / XMODEM-1K / YMODEM 收發，或原始位元組流傳送檔案（常用於向 bootloader 上傳韌體）。需先開啟串口 / 連線；傳輸期間資料區暫停顯示。",
        "xfer_help_btn": "使用說明",
        "xfer_dir": "方向",
        "xfer_dir_send": "傳送（本機 → 裝置）",
        "xfer_dir_recv": "接收（裝置 → 本機）",
        "xfer_proto": "協定",
        "xfer_proto_xmodem": "XMODEM（128 位元組 · 校驗和）",
        "xfer_proto_xmodem_crc": "XMODEM（128 位元組 · CRC）",
        "xfer_proto_1k": "XMODEM-1K（1024 位元組 · CRC）",
        "xfer_proto_ymodem": "YMODEM（帶檔名 / 大小）",
        "xfer_proto_raw": "原始位元組（直接傳送）",
        "xfer_chunk": "分塊大小",
        "xfer_delay": "塊間延時",
        "xfer_file": "檔案",
        "xfer_save": "儲存",
        "xfer_browse": "瀏覽…",
        "xfer_start": "開始",
        "xfer_cancel": "取消",
        "xfer_pick_send": "選擇要傳送的檔案",
        "xfer_pick_recv": "選擇儲存位置",
        "xfer_need_conn": "請先開啟串口 / 連線",
        "xfer_need_seq_off": "請先停止自動化序列再開始檔案傳輸",
        "xfer_need_file": "請先選擇要傳送的檔案",
        "xfer_need_save": "請先選擇儲存位置",
        "xfer_read_err": "讀取檔案失敗：{msg}",
        "xfer_write_err": "寫入檔案失敗：{msg}",
        "xfer_log_send": "傳送 {name}（{n} 位元組）· {proto}",
        "xfer_log_recv": "等待傳送方開始…· {proto}",
        "xfer_log_meta": "對方檔名：{name}（{n} 位元組）",
        "xfer_cancelling": "正在取消…",
        "xfer_done_send": "傳送完成。",
        "xfer_toast_send": "檔案已傳送",
        "xfer_done_recv": "已儲存：{path}（{n} 位元組）",
        "xfer_toast_recv": "已接收 {n} 位元組",
        "xfer_cancelled": "已取消。",
        "xfer_failed": "傳輸失敗：{msg}",
        "xfer_help_title": "檔案傳輸 · 使用說明",
        "xfer_help": "<html><body><b>XMODEM / YMODEM</b> 是串口逐塊傳檔的經典協定，常用於為 bootloader / 單晶片上傳韌體，或從裝置取回資料。<br><br>"
                     "<b>傳送（本機 → 裝置）：</b><br>1) 選「傳送」，點「瀏覽…」選檔案；<br>2) 選與裝置一致的協定；<br>"
                     "3) 讓裝置進入接收等待（如 bootloader 選單選 XMODEM 接收），再點「開始」。<br><br>"
                     "<b>接收（裝置 → 本機）：</b><br>1) 選「接收」，點「瀏覽…」選儲存位置；<br>"
                     "2) 選協定後點「開始」；本工具會不斷發起始字元等待裝置開始傳送。<br><br>"
                     "<b>協定怎麼選（要和裝置一致）：</b><br>· XMODEM（校驗和）：最舊，128 位元組塊、1 位元組累加校驗；<br>"
                     "· XMODEM（CRC）：128 位元組塊 + CRC-16，更可靠；<br>· XMODEM-1K：1024 位元組塊 + CRC，大檔更快；<br>"
                     "· YMODEM：在 1K 基礎上先傳檔名 / 大小，可自動定長。<br>"
                     "· 原始位元組：不走協定，把檔案位元組按「分塊大小」直接發出、塊間可加「間隔」延時（對端不回 ACK，純單向）。<br><br>"
                     "<b>說明：</b>傳輸期間資料區暫停顯示、自動應答 / 序列 / Modbus 主機暫停；中途斷開連線會取消傳輸。</body></html>",
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
        "func_menu": "功能",
        "new_window": "新建視窗",
        "err_new_window": "開啟新視窗失敗：{e}",
        "profile_main": "主設定",
        "profile_n": "設定 {n}",
        "profile_busy": "{name}（使用中）",
        "profile_current": "{name}（目前視窗）",
        "new_window_auto": "新建視窗（自動分配空閒設定）",
        "open_profile": "開啟設定",
        "profile_switch_busy": "該設定已在另一個視窗開啟，無法切換",
        "profile_switched": "已切換到 {name}",
        "delete_profile": "刪除設定",
        "delete": "刪除",
        "profile_delete_title": "刪除設定",
        "profile_delete_body": "確定刪除 {name}？此操作無法復原。",
        "profile_delete_busy": "該設定正被另一個視窗使用，無法刪除。",
        "profile_deleted": "已刪除 {name}",
        "profile_delete_fail": "刪除 {name} 失敗",
        "max_windows": "最多同時開啟 8 個視窗，請先關閉一個再新增。",
        "seq_open": "序列",
        "seq_btn_tip": "自動化測試序列：順序發送 → 等回包匹配 → 通過/失敗",
        "seq_title": "自動化序列",
        "seq_run": "執行",
        "seq_stop": "停止",
        "seq_add": "新增步驟",
        "seq_del": "刪除",
        "seq_help_btn": "使用說明 / 舉例",
        "seq_help_title": "自動化序列 · 使用說明",
        "seq_help": (
            "<h3>這是什麼</h3>"
            "<p>把一組「發送 → 等回包」按順序自動跑一遍，逐步判定<b>通過 / 失敗</b>，"
            "最後出彙總。適合出廠測試、裝置自檢、批量驗機、協定聯調等重複動作。</p>"
            "<h3>怎麼用</h3>"
            "<p>先<b>建立連線</b>（串口 / TCP / UDP），再「新增步驟」逐條填寫，點<b>執行</b>。"
            "執行期間會<b>暫停自動應答 / Modbus 主機</b>（三者共用收流，序列是主動驅動方），結束後自動恢復。"
            "連線中斷會中止序列，已跑結果保留。</p>"
            "<h3>每列含義</h3>"
            "<ul>"
            "<li><b>啟用</b>：取消勾選則該步跳過。</li>"
            "<li><b>名稱</b>：給這步起個名，僅方便識別，可留空。</li>"
            "<li><b>發送</b>：要發出去的內容；勾右側 <b>HEX</b> 則按十六進位解析（如 <code>01 03 00 00 00 02</code>）。留空=這步不發、只等回包。</li>"
            "<li><b>校驗</b>：給發送內容自動追加校驗（如 CRC16 / 累加和），與主介面一致。</li>"
            "<li><b>期望回包</b>：期望收到的內容；勾 <b>HEX</b> 則按十六進位比對。<b>留空 = 純發送、不等回包</b>，發完即算這步完成。</li>"
            "<li><b>模式</b>：<b>包含</b>=回包裡含有期望片段即通過；<b>相等</b>=整包完全一致；<b>前綴</b>=回包以期望開頭。</li>"
            "<li><b>逾時ms</b>：等回包的最長時間，超過還沒匹配到就算這步<b>逾時</b>。</li>"
            "<li><b>逾時</b>（動作）：<b>停止</b>=該步逾時即整體失敗並結束；<b>繼續</b>=記為失敗但繼續往下跑（最終只要有失敗步，彙總仍為失敗）。</li>"
            "<li><b>延時ms</b>：這步完成後、進入下一步前等待的時間（給裝置處理留間隔）。</li>"
            "<li><b>結果</b>：執行時即時顯示 待執行 / 等回包 / ✓用時 / ✗逾時 / 已停止 / —(跳過)。</li>"
            "</ul>"
            "<h3>舉例</h3>"
            "<p><b>例 1 · AT 指令自檢（文字）</b></p>"
            "<ul>"
            "<li>發送 <code>AT</code>，期望 <code>OK</code>，模式=包含，逾時 1000，逾時動作=停止</li>"
            "<li>發送 <code>AT+CGMR</code>，期望 <code>OK</code>，模式=包含，逾時 1000</li>"
            "<li>發送 <code>AT+RST</code>，期望留空（純發送復位，不等回包），延時 2000</li>"
            "</ul>"
            "<p><b>例 2 · Modbus 讀保持暫存器（HEX + CRC）</b></p>"
            "<ul>"
            "<li>發送 <code>01 03 00 00 00 02</code>（勾 HEX，校驗選 CRC16 自動補兩位元組），"
            "期望 <code>01 03 04</code>（勾 HEX），模式=前綴，逾時 500</li>"
            "</ul>"
            "<p><b>例 3 · 只發不等（初始化流程）</b></p>"
            "<ul>"
            "<li>發送 <code>init</code>，期望留空，延時 500</li>"
            "<li>發送 <code>start</code>，期望 <code>running</code>，模式=包含，逾時 800</li>"
            "</ul>"
            "<h3>小提示</h3>"
            "<ul>"
            "<li>拿不準回包完整格式時，用<b>模式=包含</b>更穩（只要含關鍵字即可）。</li>"
            "<li>裝置回包慢就把<b>逾時</b>調大；連著發多條給點<b>延時</b>避免丟包。</li>"
            "<li>某步允許失敗繼續測後面，就把該步<b>逾時動作</b>設為<b>繼續</b>。</li>"
            "<li>步驟會自動儲存，下次打開還在。</li>"
            "</ul>"
        ),
        "seq_hint": "順序執行每步：發送 → 等回包匹配（期望留空 = 純發送不等）→ 逾時按動作走。執行時暫停自動應答 / Modbus 主機。",
        "seq_col_name": "名稱",
        "seq_col_send": "發送",
        "seq_col_cs": "校驗",
        "seq_col_expect": "期望回包",
        "seq_col_mode": "模式",
        "seq_col_timeout": "逾時ms",
        "seq_col_onfail": "逾時",
        "seq_col_delay": "延時ms",
        "seq_col_result": "結果",
        "seq_send_ph": "HEX 或文字",
        "seq_expect_ph": "留空=不等回包",
        "seq_mode_contains": "包含",
        "seq_mode_equals": "相等",
        "seq_mode_prefix": "前綴",
        "seq_onfail_stop": "停止",
        "seq_onfail_continue": "繼續",
        "seq_st_pending": "待執行",
        "seq_st_sent": "已發送",
        "seq_st_waiting": "等回包…",
        "seq_st_pass": "通過",
        "seq_st_fail": "逾時",
        "seq_st_send_fail": "發送失敗",
        "seq_st_skip": "—",
        "seq_st_stopped": "已停止",
        "seq_summary": "通過 {ok}/{total} · 用時 {ms}ms · {verdict}",
        "seq_pass": "通過 ✓",
        "seq_fail": "失敗 ✗",
        "seq_running_toast": "序列開始執行…",
        "seq_running_at": "執行中 · 第 {i}/{n} 步",
        "seq_done_pass": "序列完成：通過 ✓",
        "seq_done_fail": "序列結束：失敗 ✗",
        "seq_stopped": "序列已停止",
        "seq_aborted_disc": "連線中斷，序列已中止",
        "seq_no_steps": "沒有可執行的步驟（發送和期望都空）",
        "seq_need_conn": "請先建立連線再執行序列",
        "seq_export": "匯出報告",
        "seq_export_none": "沒有可匯出的結果，請先執行一次序列",
        "seq_export_ok": "報告已匯出：{path}",
        "seq_export_fail": "匯出失敗：{e}",
        "seq_report_title": "自動化序列測試報告",
        "seq_report_time": "測試時間",
        "seq_report_elapsed": "耗時",
        "seq_report_detail": "詳情",
        "seq_report_skip": "跳過",
        "seq_report_fail": "失敗",
        "seq_loops": "迴圈",
        "seq_loops_tip": "迴圈次數：整條序列順序跑幾輪（≥1）；搭配右側「失敗即停」可某輪失敗就停。",
        "seq_loops_invalid": "迴圈次數需為 ≥1 的整數，已按 1 處理",
        "seq_col_retry": "重試",
        "seq_retry_tip": "失敗重試次數（0=不重試）；等本步「延時ms」且連續靜默 50ms 後重發。",
        "seq_st_retry": "↻ 第{n}次…",
        "seq_attempt": "(第{n}次)",
        "seq_steps_menu": "步驟 ▾",
        "seq_steps_export": "匯出步驟(JSON)",
        "seq_steps_import": "匯入步驟(JSON)",
        "seq_steps_export_ok": "步驟已匯出：{path}",
        "seq_steps_export_fail": "匯出失敗：{e}",
        "seq_steps_import_fail": "匯入失敗：{e}",
        "seq_steps_import_bad": "檔案格式或欄位類型不對（應為 1–500 個步驟，重試次數 0–999）",
        "seq_steps_import_large": "檔案過大（最大 5MB）",
        "seq_steps_import_confirm": "將用檔案中的 {n} 個步驟替換目前所有步驟，繼續？",
        "seq_steps_imported": "已匯入 {n} 個步驟",
        "fb_title": "幀構造器",
        "fb_template": "範本",
        "fb_add": "加欄位",
        "fb_fill": "填入發送框",
        "fb_send": "發送",
        "fb_help_btn": "使用說明 / 舉例",
        "fb_hint": "按欄位拼一幀：數值(大小端) / ascii / hex，校驗·長度自動算，底部即時出 HEX。可填入發送框或直接發送。",
        "fb_out": "HEX 輸出：",
        "fb_bytes": "{n} 位元組",
        "fb_err": "欄位錯誤：{e}",
        "fb_auto": "(自動)",
        "fb_col_name": "名稱",
        "fb_col_type": "型別",
        "fb_col_value": "值",
        "fb_type_checksum": "校驗",
        "fb_type_length": "長度",
        "fb_filled": "已填入發送框（按 HEX 發送）",
        "fb_sent": "已發送",
        "fb_send_fail": "發送失敗（未連線？）",
        "fb_tmpl_custom": "自訂",
        "fb_tmpl_modbus_read": "Modbus 讀",
        "fb_tmpl_modbus_write": "Modbus 寫單",
        "fb_tmpl_at": "AT 命令",
        "fb_tmpl_apply": "套用範本",
        "fb_tmpl_apply_confirm": "套用「{name}」範本會覆蓋目前所有欄位，繼續？",
        "fb_fields_limit": "欄位數量最多 {n} 筆，超出部分未載入",
        "fb_config_too_large": "幀構造器設定過大，已拒絕載入",
        "tb_title": "工具箱",
        "tb_tab_convert": "進制 / 編碼轉換",
        "tb_tab_checksum": "校驗計算",
        "tb_seq_title": "位元組序列",
        "tb_seq_hex": "HEX",
        "tb_seq_text": "文字",
        "tb_seq_dec": "十進制",
        "tb_seq_bin": "二進制",
        "tb_interp_title": "位元組解讀",
        "tb_endian": "位元組序",
        "tb_interp_ascii": "ASCII",
        "tb_interp_u16": "u16",
        "tb_interp_i16": "i16",
        "tb_interp_u32": "u32",
        "tb_interp_i32": "i32",
        "tb_interp_f32": "f32",
        "tb_val_title": "單值進制",
        "tb_width": "位寬",
        "tb_signed": "有符號",
        "tb_val_dec": "十進制",
        "tb_val_hex": "HEX",
        "tb_val_bin": "二進制",
        "tb_val_oct": "八進制",
        "tb_bits": "置位 bit",
        "tb_conv_hint": "改任一欄，其餘即時同步；文字裡無法解碼的位元組顯示為 \\xNN。",
        "tb_ck_input": "輸入資料",
        "tb_ck_text": "文字",
        "tb_ck_result": "校驗結果（全演算法）",
        "tb_ck_custom": "自訂 CRC",
        "tb_crc_width": "寬度",
        "tb_crc_poly": "多項式 Poly",
        "tb_crc_init": "初值 Init",
        "tb_crc_xor": "互斥或 XorOut",
        "tb_crc_refin": "輸入反轉 RefIn",
        "tb_crc_refout": "輸出反轉 RefOut",
        "tb_crc_order": "輸出位元組序",
        "tb_crc_result": "結果",
        "tb_crc_width_tip": "CRC 位寬（8/16/32/64 位），決定多項式和結果的位數。",
        "tb_crc_poly_tip": "生成多項式（不含最高位係數），十六進制填。CRC-16 常用 0x8005 或 0x1021。",
        "tb_crc_init_tip": "暫存器初值，十六進制。如 0xFFFF 或 0x0000。",
        "tb_crc_xor_tip": "最終對結果整體互斥或的值，十六進制。如 0x0000 或 0xFFFF。",
        "tb_crc_refin_tip": "輸入反轉：每個輸入位元組先按位鏡像（bit0↔bit7）再參與運算，多數 LSB 優先的裝置要開。",
        "tb_crc_refout_tip": "輸出反轉：最終 CRC 整體按位鏡像後再輸出。",
        "tb_crc_order_tip": "結果位元組序：LE = 低位元組在前（Modbus 常用），BE = 高位元組在前。",
        "tb_ck_hint": "把資料段貼進來，看哪一列結果 == 幀尾的校驗位元組，即可反推裝置用的校驗演算法。",
        "tb_help_btn": "使用說明",
        "tb_help_title": "工具箱 · 使用說明",
        "tb_help": (
            "<h3>位元組序列轉換</h3>"
            "<p>同一串位元組的四種表示，改任一欄、其餘三欄即時同步：</p>"
            "<ul>"
            "<li><b>HEX</b>：十六進制位元組，空格 / 逗號可省（如 <code>01 41 FF</code>）。</li>"
            "<li><b>文字</b>：按 UTF-8 解碼顯示；無法解碼的位元組顯示為 <code>\\xNN</code>。</li>"
            "<li><b>十進制 / 二進制</b>：每位元組一個數（0..255 / 8 位）。</li>"
            "</ul>"
            "<p>下方會按目前位元組序即時解讀前幾個位元組為 ASCII / 整數 / f32，方便看暫存器值和浮點值。</p>"
            "<p>任一欄非法（奇數長度 HEX、越界十進制…）會標紅，不影響其它欄。</p>"
            "<h3>單值進制轉換</h3>"
            "<p>一個整數在 十進制 / HEX / 二進制 / 八進制 間轉，算暫存器值、位址、位元遮罩用：</p>"
            "<ul>"
            "<li><b>位寬</b> 8/16/32/64：HEX、二進制按位寬補零。</li>"
            "<li><b>有符號</b>：勾選後十進制按補碼解讀（8 位 <code>FF</code>=<code>-1</code>）；負數輸入也按補碼落進位寬。</li>"
            "<li><b>置位 bit</b>：可輸入 <code>0, 3, 7</code> 生成位元遮罩，也會隨數值反顯目前置位。</li>"
            "</ul>"
            "<h3>校驗計算</h3>"
            "<p>輸入一段資料（HEX；勾「文字」則按文字編碼），下方一次性列出<b>全部校驗演算法</b>的結果。</p>"
            "<p><b>自訂 CRC</b> 可填寬度、多項式、初值、異或值、反射和輸出位元組序；參數按十六進制填寫。</p>"
            "<p>不知道裝置用哪種校驗？把幀裡<b>參與校驗的資料段</b>貼進來，看哪一列 == 幀裡的校驗位元組，就反推出它用的演算法。</p>"
        ),
        "fb_help_title": "幀構造器 · 使用說明",
        "fb_help": (
            "<h3>這是什麼</h3>"
            "<p>按<b>欄位</b>拼一幀、即時出 HEX，省得手敲十六進位。支援數值(帶大小端) / 文字 / HEX，"
            "外加<b>自動欄位</b>（校驗、長度），並內建常見協定範本一鍵填充。拼好可<b>填入發送框</b>或<b>直接發送</b>。</p>"
            "<h3>欄位型別</h3>"
            "<ul>"
            "<li><b>數值</b>：u8/i8/u16le/u16be/i16../u32../i32../f32le/f32be —— 型別名裡的 le/be 是小端/大端；"
            "值可填十進位或 <code>0x</code> 十六進位。</li>"
            "<li><b>ascii</b>：把文字按 ASCII 編碼（如 <code>AT</code>）。</li>"
            "<li><b>hex</b>：直接填十六進位位元組串（如 <code>01 03</code>）。</li>"
            "<li><b>校驗:演算法</b>（自動）：對<b>它前面所有位元組</b>算校驗並追加（ModbusCRC16 / XOR8 / CRC8…）。</li>"
            "<li><b>長度:u8 / u16be</b>（自動）：值 = <b>它後面所有位元組</b>的個數，按所選寬度編碼。</li>"
            "</ul>"
            "<h3>範本</h3>"
            "<ul>"
            "<li><b>Modbus 讀</b>：從機 / 功能(03) / 起始位址(u16be) / 數量(u16be) / CRC16。</li>"
            "<li><b>Modbus 寫單</b>：從機 / 06 / 位址 / 值 / CRC16。</li>"
            "<li><b>AT 命令</b>：ascii <code>AT</code> + <code>0D 0A</code>(CR LF)。</li>"
            "</ul>"
            "<h3>小提示</h3>"
            "<ul>"
            "<li>校驗放在最後一個欄位，它會涵蓋前面全部；長度放在載荷前面，它數後面的位元組。</li>"
            "<li>「填入發送框」會自動打開主介面的 HEX 發送開關。</li>"
            "<li>拖動每行左側 ☰ 手柄可調整欄位順序（順序 = 拼幀位元組序）。</li>"
            "<li>拖名稱/類型/值 之間的分隔條可調欄寬，所有列一起變。</li>"
            "<li>欄位會自動儲存，下次打開還在。</li>"
            "</ul>"
        ),
        "seq_stop_on_fail": "失敗即停",
        "seq_running_round": "執行中 · 第 {r}/{n_loops} 輪 · 第 {i}/{n} 步",
        "seq_summary_loops": "{rounds} · 累計 {ok}/{total} 步 · 用時 {ms}ms · {verdict}",
        "seq_rounds_frac": "通過輪 {rp}/{rt}",
        "seq_rounds_partial": "通過輪 {rp}/{rt}（計劃 {loops} 輪）",
        "seq_report_round": "輪次",
        "seq_report_round_steps": "通過步",
        "seq_report_verdict": "結論",
        "about_desc": "iOS 風格的串口 / 網路偵錯工具（串口 + TCP/UDP）",
        "term_open": "終端",
        "term_mode": "終端模式",
        "term_btn_tip": "終端模式：發送框逐字元即時發送、資料區純文字流顯示（輕量串口終端，不解析 ANSI 顏色/全螢幕）",
        "term_echo": "本地回顯",
        "term_enter": "Enter",
        "term_mode_tip": "把發送框變成輕量串口終端：逐字元即時發送（Enter / Backspace / Tab / Ctrl+C / 方向鍵透傳給裝置），資料區按終端語意顯示回顯。適合登入 Linux 串口控制台敲命令；不解析全螢幕 TUI（vi / top）。",
        "term_echo_tip": "本地回顯：把你鍵入的字元也顯示到資料區。裝置自己會回顯時保持關閉（否則每個字元顯示兩遍）；只有裝置不回顯時才開。",
        "term_enter_tip": "終端模式下按 Enter 鍵發送的字元：CR（\\r，多數 Linux 控制台）/ LF（\\n）/ CRLF（\\r\\n）。",
        "term_send_ph": "終端模式：直接鍵入即時發送（Enter / Backspace / Tab / Ctrl+C / 方向鍵等透傳給裝置）",
        "term_on": "已開啟終端模式：發送框逐字元即時發送",
        "term_off": "已關閉終端模式",
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
        "update_open_dmg": "已下載並開啟安裝映像，拖入「應用程式」後重啟即可（首次開啟見「關於」說明）",
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
        "sc_title": "腳本主控台",
        "sc_script": "腳本",
        "sc_new": "新增",
        "sc_rename": "重新命名",
        "sc_delete": "刪除",
        "sc_import": "匯入",
        "sc_export": "匯出",
        "sc_rec": "● 錄製",
        "sc_rec_stop": "■ 停止錄製",
        "sc_rec_name": "錄製腳本",
        "sc_rec_started": "開始錄製 —— 回主介面正常收發，完成後回來點「停止錄製」（自動應答的回覆、終端模式的按鍵不錄）",
        "sc_rec_running": "錄製中…（回主介面手動收發，操作會被翻譯成腳本；期間不能執行腳本）",
        "sc_rec_full": "腳本庫已滿（上限 {n}），錄製內容已保留 —— 刪掉一個腳本後再點一次「停止錄製」即可儲存",
        "sc_rec_empty": "沒有錄到任何收發",
        "sc_rec_done": "已產生「{name}」：{tx} 次傳送 / {rx} 次接收",
        "io_exclusive_busy": "另一項收發工作正在執行，請先停止後再開始",
        "sc_run": "執行",
        "sc_stop": "停止",
        "sc_clear_out": "清空輸出",
        "sc_default_name": "新腳本",
        "sc_name_prompt": "腳本名稱：",
        "sc_max": "腳本庫最多 {n} 個",
        "sc_keep_one": "至少保留一個腳本",
        "sc_delete_warn": "確定刪除腳本「{name}」？此操作無法復原。",
        "sc_import_partial": "腳本庫已滿（上限 {max}），只匯入了 {n} 個，跳過 {skipped} 個",
        "sc_code_too_long": "腳本超過 {n} 個字元，超出部分不會被儲存",
        "sc_import_bad": "檔案裡沒有可用的腳本",
        "sc_import_title": "匯入腳本",
        "sc_import_warn": "匯入內容包含 {n} 個腳本，它們會在本機以本程式的權限執行。\n只在信任來源時選「是」。要匯入這些腳本嗎？",
        "sc_code_empty": "腳本內容為空，無法執行",
        "sc_started": "▶ 開始執行…",
        "sc_running": "執行中…（腳本獨佔收發流，自動應答 / Modbus 主機已暫停）",
        "sc_hint": "用 send / recv / expect / sleep / log / check 編排收發；點「?」看 API 與範例。執行時腳本獨佔收發流。",
        "sc_done_ok": "■ 完成：通過 {ok} / 失敗 {fail}",
        "sc_done_fail": "■ 結束（有失敗）：通過 {ok} / 失敗 {fail}",
        "sc_done_stopped": "■ 已停止：通過 {ok} / 失敗 {fail}",
        "sc_done_error": "■ 出錯中斷：通過 {ok} / 失敗 {fail}",
        "sc_help_btn": "使用說明",
        "sc_help_title": "腳本主控台 · 使用說明",
        "sc_help": '<b>腳本主控台</b> 用 Python 腳本驅動目前連線的真實收發，適合自檢、老化、批次設定、協定聯調等 GUI 設定表達不了的流程。<br><br><b>API</b><br>• <code>send(data, hex=False)</code> — 傳送。<code>bytes</code> 原樣送出；<code>hex=True</code> 時按 HEX 字串解析；否則按 UTF-8 編碼。<br>• <code>expect(pattern, timeout=1000, hex=False)</code> — 等到收到的資料裡出現 <code>pattern</code>，回傳<b>含匹配</b>的那段 bytes；逾時回傳 <code>None</code>。<br>• <code>recv(timeout=1000)</code> — 等任意資料，回傳 bytes。<br>• <code>sleep(ms)</code> — 延時，可被「停止」打斷。<br>• <code>log(*args)</code> — 輸出一列到下方日誌。<br>• <code>check(cond, msg)</code> — 斷言：真計通過、假計失敗，結束時給出彙總；回傳 bool 可用於分支。<br>• <code>hexs("AA BB")</code> — HEX 字串轉 bytes。<br><br><b>範例：AT 自檢</b><pre style=\'margin:2px 0 2px 16px\'>send("AT\\r\\n")\nr = expect("OK", timeout=1000)\ncheck(r is not None, "AT 應答 OK")</pre><b>範例：Modbus 輪詢 10 次</b><pre style=\'margin:2px 0 2px 16px\'>for i in range(10):\n    send(hexs("01 03 00 00 00 01 84 0A"))\n    r = expect(hexs("01 03"), timeout=500)\n    check(r is not None, "第 %d 次有回應" % (i + 1))\n    sleep(200)</pre><br><b>腳本庫</b>：可儲存多個命名腳本、下拉切換，隨工作階段設定持久化；「匯入 / 匯出」用 JSON 分享。匯入的腳本會先徵求同意。<br><br><b>注意</b><br>• 執行期間腳本<b>獨佔收發流</b>，自動應答 / Modbus 主機自動暫停，結束後恢復。<br>• 「停止」是<b>協作式</b>的：在 send / expect / recv / sleep 處生效。純計算無窮迴圈無法中斷。<br>• 腳本以本程式權限執行，可存取檔案系統等——請勿執行來源不明的腳本。',
        "dash_open": "數值儀表板",
        "dash_title": "數值儀表板",
        "dash_thresh": "閾值",
        "dash_thresh_ph": "閾值告警：名稱:下限~上限:單位，逗號分隔，如 溫度:10~40:℃, CH1:0~100:%（超限卡片變紅閃爍；上/下限可留空）",
        "dash_hint": "把 RX 流解析成命名數值，每通道一張大字號卡片顯示當前值；解析同波形圖三模式（分隔符/正則每列 CH1/CH2…、HEX 位元組按欄位名）。閾值列給通道配上下限，超限卡片變紅閃爍。配置與波形圖相互獨立。",
        "dash_help_title": "數值儀表板 · 使用說明",
        "dash_help": "<b>數值儀表板</b> 把 RX 流解析成命名數值通道，每通道一張大字號卡片顯示<b>當前值</b>，超閾值變紅閃爍。適合 IoT 感測器/電源等即時讀數監看。<br><br><b>解析模式（與波形圖相互獨立）</b><br>• <b>分隔符</b>：每行按 逗號/空白/Tab/分號/自動 拆，每列一個通道，命名 CH1、CH2…（如 <code>36.5,72,3.30</code>）<br>• <b>正則</b>：每行用正則，每個擷取群組一個通道 CH1、CH2…（如 <code>t=(\\d+).*h=(\\d+)</code>）<br>• <b>HEX 位元組</b>：按「幀頭 + 名稱=偏移:類型」從位元組取數值，欄位名即通道名（如 <code>溫度=0:i16be, 電壓=2:u16be</code>）<br><br><b>閾值告警</b><br>閾值列填 <code>名稱:下限~上限:單位</code>，逗號分隔：<br>&nbsp;&nbsp;<code>溫度:10~40:℃, 電壓:3.0~3.6:V, CH1:0~100:%</code><br>值 &lt; 下限 或 &gt; 上限 → 卡片變紅閃爍。上限/下限可留空表示該側不限（如 <code>溫度:10~:℃</code> 只管下限）。<br><br>⚠️ HEX 模式把每個底層接收區塊視為一幀，不處理黏包/拆包；請確保裝置或連線層按完整幀交付。",
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
        "mbm_open": "Modbus主機",
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
        # ── 串口↔網路橋接 ──
        "bg_title": "橋接轉發",
        "bg_help": "在 A/B 兩端之間雙向透明轉發資料。兩端可以是串口/TCP客戶端/TCP伺服器/UDP任意組合。\n常用於：\n• 串口轉網路（軟體DTU）\n• 雙串口監聽/嗅探\n• TCP↔UDP 協定轉換\n• 遠端除錯串口裝置",
        "bg_type": "類型",
        "bg_port": "埠",
        "bg_baud": "鮑率",
        "bg_databits": "資料位",
        "bg_parity": "校驗位",
        "bg_stopbits": "停止位",
        "bg_remote_ip": "遠端 IP",
        "bg_remote_port": "遠端埠",
        "bg_local_ip": "本地 IP",
        "bg_local_port": "本地埠",
        "bg_spec_remote": "指定遠端",
        "bg_open": "開啟",
        "bg_close": "關閉",
        "bg_cancel": "取消",
        "bg_connected": "● 已連接",
        "bg_connecting": "◌ 連接中...",
        "bg_disconnected": "○ 未連接",
        "bg_start": "開始橋接",
        "bg_stop": "停止橋接",
        "bg_bridging": "● 橋接中...",
        "bg_stopped_status": "○ 已停止",
        "bg_log_title": "轉發日誌",
        "bg_log_enable": "記錄流量",
        "bg_log_hex": "HEX",
        "bg_log_clear": "清空",
        "bg_max_lines": "最大行數:",
        "bg_recv": "RX",
        "bg_sent": "TX",
        "bg_need_both": "請先開啟兩側連接",
        "bg_wait_target": "Side {side} 尚無可傳送目標（TCP 用戶端或 UDP 對端）",
        "bg_same_port": "兩端不能使用同一個串口",
        "bg_stopped_reason": "橋接已停止: {reason}",
        "bg_need_port": "請選擇串口",
        "bg_bad_addr": "請填寫有效的 IP 位址和埠號",
        "bg_bad_port": "請填寫有效的埠號",
        "bg_refresh_ports": "重新整理串口列表",
    },
}
CHECKSUM_KEYS = ["ck_none", "ck_sum", "ck_neg_sum", "ck_xor", "ck_crc8",
                 "ck_modbus", "ck_ccitt", "ck_crc32", "ck_add16", "ck_mobus"]
