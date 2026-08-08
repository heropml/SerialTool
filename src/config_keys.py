# -*- coding: utf-8 -*-
"""Session/config export key set (Qt-free).

S-2 R18: shared by CommTool import/export and project packaging.
"""

CFG_KEYS = (
    # 网络连接
    "net_proto", "net_local_ip", "net_local_port",
    "net_remote_ip", "net_remote_port", "net_use_remote", "net_group_addr",
    # 虚拟连接（离线模式）
    "vconn_loopback",
    # 串口连接
    "ser_port", "ser_baud", "ser_databits", "ser_parity", "ser_stopbits",
    "ser_flow", "serial_dtr", "serial_rts",
    # 数据区显示
    "rx_hex", "hexdump_view", "hexdump_width", "numview", "numview_type", "ansi_color",
    "proto_highlight", "wrap", "show_timestamp", "packet_split", "packet_timeout",
    "line_split", "line_nl_mode", "encoding", "max_lines", "ts_format", "freeze_view",
    "log_split", "filter_highlight", "recv_font_size",
    # 发送区
    "tx_hex", "append_newline", "append_nl_mode", "period_ms",
    "checksum_idx", "send_text",
    # 主题/语言
    "theme", "language",
    # 多条发送 / 关键字 / 帧解析 / 绘图
    "multi_send_groups", "multi_send_group_idx", "multi_send_split", "snippets",
    "connection_presets",
    "keyword_groups", "keyword_active",
    "frame_rules",
    "plot_mode", "plot_sep", "plot_regex", "plot_hex_fields",
    "plot_hex_header", "plot_maxpts", "plot_xaxis",
    # 数值仪表盘
    "dash_mode", "dash_sep", "dash_regex", "dash_fields", "dash_header", "dash_thresholds",
    # 脚本控制台
    "script_lib", "script_active",
    # 自动应答
    "autoreply_rules", "autoreply_on", "autoreply_frame", "autoreply_fault", "autoreply_sm",
    "autoreply_modbus", "autoreply_split",
    # Modbus 主机轮询
    "modbus_master", "modbus_master_on", "modbus_master_variant", "modbus_master_echo",
    "modbus_master_views", "modbus_master_split", "device_registers",
    "device_plot_tags", "device_dash_tags",
    # 自动化测试序列
    "sequence_rules", "sequence_loops", "sequence_stop_on_fail",
    "sequence_csv_path",
    # 触发告警
    "triggers",
    # 帧构造器
    "frame_builder_fields", "frame_builder_split",
    # 终端模式
    "terminal_mode", "terminal_echo", "terminal_enter",
    # 杂项
    "auto_reconnect", "auto_update_check",
)

# Keys kept local to the machine / user preference (not in project snapshot).
PROJECT_PERSONAL_KEYS = frozenset((
    "theme", "language", "auto_update_check",
))
