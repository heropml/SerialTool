# -*- coding: utf-8 -*-
"""Connection settings sidebar card factory (Qt).

S-2 R38: move CommTool.build_settings_card body here so main_window
stays a thin wrapper. Widgets are attached onto the host `app`.
"""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from theme import COLOR_TEXT_SECONDARY
from ui_tips import set_tooltip
from widgets import Card, IOSSwitch
from conn_ui import visible_conn_types
from net_io import local_ipv4_list
import ble_uuid
from serial_params import (
    BAUD_RATES,
    DATABITS_OPTIONS,
    PARITY_OPTIONS,
    STOPBITS_OPTIONS,
    FLOW_OPTIONS,
)


def build(app):
    """Build the connection-settings Card and bind widgets onto `app`.

    Required on `app`: `_t`, `_tr_label`, `_label_col_width`, plus handlers
    used by presets / serial / ctrl-line / open-button wiring, and
    `_update_net_fields` / `_rebuild_connection_preset_combo`.
    """
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(6)
    layout.addWidget(app._tr_label("conn_settings", 12, bold=True))

    def make_row(label_key, field):
        """一行：固定宽标签 + 字段，整行包成 QWidget 便于按协议显隐。"""
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        lbl = app._tr_label(label_key, color=COLOR_TEXT_SECONDARY)
        lbl.setFixedWidth(app._label_col_width())
        lbl.setProperty("tr_fixedw", True)
        rl.addWidget(lbl)
        rl.addWidget(field, 1)
        layout.addWidget(row)
        return row

    # connection presets row
    preset_box = QWidget()
    pbl_preset = QHBoxLayout(preset_box)
    pbl_preset.setContentsMargins(0, 0, 0, 0)
    pbl_preset.setSpacing(6)
    app.cb_conn_preset = QComboBox()
    app.cb_conn_preset.setMinimumWidth(100)
    app.cb_conn_preset.setSizeAdjustPolicy(
        QComboBox.AdjustToMinimumContentsLengthWithIcon)
    app.cb_conn_preset.setMinimumContentsLength(12)
    app.cb_conn_preset.activated.connect(app._on_connection_preset_activated)
    pbl_preset.addWidget(app.cb_conn_preset, 1)
    app.btn_cpreset_save = QPushButton(app._t("cpreset_save_btn"))
    app.btn_cpreset_save.setObjectName("GhostBtnSm")
    app.btn_cpreset_save.setProperty("tr_text", "cpreset_save_btn")
    app.btn_cpreset_save.setProperty("tr_tooltip", "cpreset_save_btn_tip")
    set_tooltip(app.btn_cpreset_save, app._t("cpreset_save_btn_tip"))
    app.btn_cpreset_save.clicked.connect(
        lambda *_: app.save_connection_preset_from_ui(prompt_name=True))
    pbl_preset.addWidget(app.btn_cpreset_save)
    app.btn_cpreset_manage = QPushButton(app._t("cpreset_manage_btn"))
    app.btn_cpreset_manage.setObjectName("GhostBtnSm")
    app.btn_cpreset_manage.setProperty("tr_text", "cpreset_manage_btn")
    app.btn_cpreset_manage.setProperty("tr_tooltip", "cpreset_manage_btn_tip")
    set_tooltip(app.btn_cpreset_manage, app._t("cpreset_manage_btn_tip"))
    app.btn_cpreset_manage.clicked.connect(app.open_connection_presets)
    pbl_preset.addWidget(app.btn_cpreset_manage)
    app.row_conn_preset = make_row("cpreset_label", preset_box)

    # 连接类型：串口 + 网络协议，统一进一个下拉
    app.cb_proto = QComboBox()
    app.cb_proto.addItems(visible_conn_types())
    app.cb_proto.currentIndexChanged.connect(lambda _: app._update_net_fields())
    make_row("protocol_type", app.cb_proto)

    # ===== 串口字段（仅 Serial 类型显示）=====
    # 端口：下拉 + ⟳ 刷新按钮，包成一个容器塞进 make_row 的字段位
    port_box = QWidget()
    pbl = QHBoxLayout(port_box)
    pbl.setContentsMargins(0, 0, 0, 0)
    pbl.setSpacing(6)
    app.cb_port = QComboBox()
    app.cb_port.setMinimumWidth(100)
    app.cb_port.activated.connect(app._on_serial_port_selected)
    pbl.addWidget(app.cb_port, 1)
    app.btn_refresh = QPushButton("⟳")
    app.btn_refresh.setObjectName("IconBtn")
    app.btn_refresh.setFixedSize(30, 26)
    app.btn_refresh.clicked.connect(app.refresh_ports)
    pbl.addWidget(app.btn_refresh)
    app.row_port = make_row("port", port_box)

    app.cb_baud = QComboBox()
    app.cb_baud.setEditable(True)
    for b in BAUD_RATES:
        app.cb_baud.addItem(b)
    app.cb_baud.setCurrentText("115200")
    app.row_baud = make_row("baud_rate", app.cb_baud)

    app.cb_databits = QComboBox()
    app.cb_databits.addItems(list(DATABITS_OPTIONS))
    app.cb_databits.setCurrentText("8")
    app.row_databits = make_row("data_bits", app.cb_databits)

    app.cb_parity = QComboBox()
    app.cb_parity.addItems(list(PARITY_OPTIONS))
    app.row_parity = make_row("parity", app.cb_parity)

    app.cb_stopbits = QComboBox()
    app.cb_stopbits.addItems(list(STOPBITS_OPTIONS))
    app.cb_stopbits.setCurrentText("1")
    app.row_stopbits = make_row("stop_bits", app.cb_stopbits)

    # 硬件/软件流控：None / RTS-CTS（硬件）/ XON-XOFF（软件）
    app.cb_flow = QComboBox()
    app.cb_flow.addItems(list(FLOW_OPTIONS))
    app.cb_flow.setCurrentText("None")
    app.cb_flow.currentIndexChanged.connect(app._on_flow_changed)
    app.row_flow = make_row("flow_control", app.cb_flow)

    # 串口参数连接期间可改、改动即应用（见 _apply_serial_params_live）。
    # 刻意只挂 activated（用户在下拉里点选）与 editingFinished（波特率手输后回车/失焦）：
    # currentTextChanged 会在手输过程中逐字符触发（1→11→115…），把中间值打进串口；
    # 程序化 setCurrentText（切配置/导入）也会触发 currentIndexChanged —— 都不能用。
    for _cb in (app.cb_baud, app.cb_databits, app.cb_parity,
                app.cb_stopbits, app.cb_flow):
        _cb.activated.connect(app._apply_serial_params_live)
    app.cb_baud.lineEdit().editingFinished.connect(app._apply_serial_params_live)

    # 本地 IP（TCP Server / UDP）— 下拉本机网卡 IP，可编辑
    app.cb_local_ip = QComboBox()
    app.cb_local_ip.setEditable(True)
    app.cb_local_ip.setMinimumWidth(100)
    app.cb_local_ip.addItems(local_ipv4_list())
    app.row_local_ip = make_row("local_ip", app.cb_local_ip)

    # 组播地址（仅 UDP Multicast）
    app.ed_group = QLineEdit("239.0.0.1")
    app.row_group = make_row("group_addr", app.ed_group)

    # 本地端口
    app.ed_local_port = QLineEdit("8080")
    app.row_local_port = make_row("local_port", app.ed_local_port)

    # 指定远程 开关（仅 UDP）：关=回复最近对端；开=固定发往下面的远程地址
    app.sw_udp_remote = IOSSwitch(False)
    app.sw_udp_remote.toggled.connect(lambda _=False: app._update_net_fields())
    sw_row = QWidget()
    swl = QHBoxLayout(sw_row)
    swl.setContentsMargins(0, 0, 0, 0)
    swl.setSpacing(6)
    sw_lbl = app._tr_label("use_remote", color=COLOR_TEXT_SECONDARY)
    sw_lbl.setFixedWidth(app._label_col_width())
    sw_lbl.setProperty("tr_fixedw", True)
    swl.addWidget(sw_lbl)
    swl.addWidget(app.sw_udp_remote)
    swl.addStretch(1)
    layout.addWidget(sw_row)
    app.row_udp_remote = sw_row

    # 远程 IP（TCP Client 必填 / UDP 由「指定远程」开关启用）
    app.ed_remote_ip = QLineEdit()
    app.row_remote_ip = make_row("remote_ip", app.ed_remote_ip)

    # 远程端口
    app.ed_remote_port = QLineEdit()
    app.row_remote_port = make_row("remote_port", app.ed_remote_port)

    # 目标客户端（仅 TCP Server 监听后显示）
    app.cb_target = QComboBox()
    app.row_target = make_row("target_client", app.cb_target)

    # 回环 开关（仅虚拟连接）：开=发出去的数据原样当成收到的回来，可离线自测规则/脚本
    app.sw_vconn_loop = IOSSwitch(False)
    app.sw_vconn_loop.toggled.connect(app._on_vconn_loop_toggled)
    vrow = QWidget()
    vl = QHBoxLayout(vrow)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(6)
    v_lbl = app._tr_label("vconn_loopback", color=COLOR_TEXT_SECONDARY)
    v_lbl.setFixedWidth(app._label_col_width())
    v_lbl.setProperty("tr_fixedw", True)
    v_lbl.setProperty("tr_tooltip", "vconn_tip")
    set_tooltip(v_lbl, app._t("vconn_tip"))
    vl.addWidget(v_lbl)
    vl.addWidget(app.sw_vconn_loop)
    app.sw_vconn_loop.setProperty("tr_tooltip", "vconn_tip")
    set_tooltip(app.sw_vconn_loop, app._t("vconn_tip"))
    vl.addStretch(1)
    layout.addWidget(vrow)
    app.row_vconn_loop = vrow

    # ===== BLE (Windows central / UART-style Notify+Write) =====
    ble_scan_box = QWidget()
    ble_scan_l = QHBoxLayout(ble_scan_box)
    ble_scan_l.setContentsMargins(0, 0, 0, 0)
    ble_scan_l.setSpacing(6)
    app.btn_ble_scan = QPushButton(app._t("ble_scan"))
    app.btn_ble_scan.setObjectName("PrimaryBtn")
    app.btn_ble_scan.setProperty("tr_text", "ble_scan")
    app.btn_ble_scan.setProperty("tr_tooltip", "ble_scan_tip")
    set_tooltip(app.btn_ble_scan, app._t("ble_scan_tip"))
    app.btn_ble_scan.clicked.connect(app._on_ble_scan_clicked)
    ble_scan_l.addWidget(app.btn_ble_scan)
    ble_scan_l.addStretch(1)
    app.row_ble_scan = make_row("ble_scan", ble_scan_box)

    app.ed_ble_name = QLineEdit()
    app.ed_ble_name.setReadOnly(True)
    app.row_ble_name = make_row("ble_name", app.ed_ble_name)

    app.ed_ble_address = QLineEdit()
    app.row_ble_address = make_row("ble_address", app.ed_ble_address)

    app.cb_ble_profile = QComboBox()
    app.cb_ble_profile.blockSignals(True)
    for _pid in ble_uuid.PROFILES:
        app.cb_ble_profile.addItem(ble_uuid.PROFILE_LABELS[_pid], _pid)
    app.cb_ble_profile.setCurrentIndex(0)
    app.cb_ble_profile.blockSignals(False)
    app.cb_ble_profile.currentIndexChanged.connect(app._on_ble_profile_changed)
    app.row_ble_profile = make_row("ble_profile", app.cb_ble_profile)

    app.ed_ble_service = QLineEdit()
    app.row_ble_service = make_row("ble_service_uuid", app.ed_ble_service)

    write_box = QWidget()
    write_l = QHBoxLayout(write_box)
    write_l.setContentsMargins(0, 0, 0, 0)
    write_l.setSpacing(6)
    app.ed_ble_write = QLineEdit()
    write_l.addWidget(app.ed_ble_write, 1)
    app.btn_ble_swap = QPushButton(app._t("ble_swap"))
    app.btn_ble_swap.setObjectName("GhostBtnSm")
    app.btn_ble_swap.setProperty("tr_text", "ble_swap")
    app.btn_ble_swap.setProperty("tr_tooltip", "ble_swap_tip")
    set_tooltip(app.btn_ble_swap, app._t("ble_swap_tip"))
    app.btn_ble_swap.clicked.connect(app._on_ble_swap_clicked)
    write_l.addWidget(app.btn_ble_swap)
    app.row_ble_write = make_row("ble_write_uuid", write_box)

    app.ed_ble_notify = QLineEdit()
    app.row_ble_notify = make_row("ble_notify_uuid", app.ed_ble_notify)

    app.cb_ble_write_mode = QComboBox()
    app.cb_ble_write_mode.blockSignals(True)
    for _mid in ble_uuid.WRITE_MODES:
        app.cb_ble_write_mode.addItem(ble_uuid.WRITE_MODE_LABELS[_mid], _mid)
    app.cb_ble_write_mode.setCurrentIndex(0)
    app.cb_ble_write_mode.blockSignals(False)
    app.cb_ble_write_mode.setProperty("tr_tooltip", "ble_write_mode_tip")
    set_tooltip(app.cb_ble_write_mode, app._t("ble_write_mode_tip"))
    app.row_ble_write_mode = make_row("ble_write_mode", app.cb_ble_write_mode)

    _ble_preset = ble_uuid.apply_preset(ble_uuid.PROFILE_FFF0)
    app.ed_ble_service.setText(ble_uuid.short_uuid(_ble_preset["service_uuid"]))
    app.ed_ble_write.setText(ble_uuid.short_uuid(_ble_preset["write_uuid"]))
    app.ed_ble_notify.setText(ble_uuid.short_uuid(_ble_preset["notify_uuid"]))

    # 动作按钮（文案随协议/状态变化）
    app.btn_open = QPushButton(app._t("btn_listen"))
    app.btn_open.setObjectName("PrimaryBtn")
    app.btn_open.setMinimumHeight(34)
    app.btn_open.clicked.connect(app.toggle_conn)
    layout.addWidget(app.btn_open)

    # 控制线（仅串口 + 已连接时显示）：DTR/RTS 输出开关 + 复位脉冲 + CTS/DSR/DCD/RI 状态灯
    app.box_ctrl = QWidget()
    cl = QVBoxLayout(app.box_ctrl)
    cl.setContentsMargins(0, 8, 0, 0)
    cl.setSpacing(6)
    app.lbl_ctrl_head = app._tr_label("ctrl_line", 12, bold=True)
    cl.addWidget(app.lbl_ctrl_head)
    # DTR / RTS 输出开关 + 复位 / Break 按钮同一行（紧凑排布，按钮用小号 GhostBtnSm 省横向空间）
    r_out = QHBoxLayout()
    r_out.setSpacing(4)
    app.sw_dtr = IOSSwitch(True)
    app.sw_dtr.toggled.connect(app._on_dtr_toggled)
    app.sw_dtr.setProperty("tr_tooltip", "ctrl_dtr_tip")
    set_tooltip(app.sw_dtr, app._t("ctrl_dtr_tip"))
    app.sw_rts = IOSSwitch(True)
    app.sw_rts.toggled.connect(app._on_rts_toggled)
    app.sw_rts.setProperty("tr_tooltip", "ctrl_rts_tip")
    set_tooltip(app.sw_rts, app._t("ctrl_rts_tip"))
    _dtr_l = QLabel("DTR"); _dtr_l.setObjectName("CtrlLbl")
    _rts_l = QLabel("RTS"); _rts_l.setObjectName("CtrlLbl")
    app.btn_reset = QPushButton(app._t("ctrl_reset"))
    app.btn_reset.setObjectName("GhostBtnSm")
    app.btn_reset.setProperty("tr_text", "ctrl_reset")
    app.btn_reset.setProperty("tr_tooltip", "ctrl_reset_tip")
    set_tooltip(app.btn_reset, app._t("ctrl_reset_tip"))
    app.btn_reset.clicked.connect(app._pulse_reset)
    app.btn_break = QPushButton(app._t("ctrl_break"))
    app.btn_break.setObjectName("GhostBtnSm")
    app.btn_break.setProperty("tr_text", "ctrl_break")
    app.btn_break.setProperty("tr_tooltip", "ctrl_break_tip")
    set_tooltip(app.btn_break, app._t("ctrl_break_tip"))
    app.btn_break.clicked.connect(app._send_break)
    # DTR / RTS / 复位 / 中断 四组两端对齐、均匀铺满整行（与下方 CTS/DSR/DCD/RI 状态灯行同分布，上下一致）
    r_out.addWidget(_dtr_l); r_out.addWidget(app.sw_dtr)
    r_out.addStretch(1)
    r_out.addWidget(_rts_l); r_out.addWidget(app.sw_rts)
    r_out.addStretch(1)
    r_out.addWidget(app.btn_reset)
    r_out.addStretch(1)
    r_out.addWidget(app.btn_break)
    cl.addLayout(r_out)
    r_in = QHBoxLayout()
    r_in.setSpacing(0)
    app._ctrl_dots = {}
    _dot_keys = ("cts", "dsr", "dcd", "ri")
    for _i, k in enumerate(_dot_keys):
        lb = QLabel(k.upper()); lb.setObjectName("CtrlLbl")
        dot = QLabel("●"); dot.setObjectName("CtrlDot")
        app._ctrl_dots[k] = dot
        r_in.addWidget(lb)
        r_in.addSpacing(5)               # 标签与其状态点之间固定小间距
        r_in.addWidget(dot)
        if _i < len(_dot_keys) - 1:
            r_in.addStretch(1)           # 组间等分弹簧 → 四组两端对齐、均匀铺满整行
    cl.addLayout(r_in)
    layout.addWidget(app.box_ctrl)
    # 输入状态线轮询定时器（连接期间 ~5Hz 刷新状态灯）
    app._ctrl_poll_timer = QTimer(app)
    app._ctrl_poll_timer.setInterval(200)
    app._ctrl_poll_timer.timeout.connect(app._poll_ctrl_lines)
    # DTR reset-pulse timers are owned by Session so delayed release cannot
    # jump to another tab after a session switch.
    if not hasattr(app, "_reset_timer"):
        app._reset_timer = None

    app._update_net_fields()
    app._rebuild_connection_preset_combo()
    return card
