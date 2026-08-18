# -*- coding: utf-8 -*-
"""工具箱 ToolboxDialog —— 进制/编码转换 + 校验计算。

两个页签：
- 进制/编码转换：①字节序列 HEX ⇄ 文本 ⇄ 十进制 ⇄ 二进制（改一个其余实时同步、非法标红）；
  ②单值多进制 十进制 / HEX / 二进制 / 八进制（可配位宽 8/16/32/64 + 有无符号，负数按补码）。
- 校验计算：输入数据（HEX 或文本），一次性列出全部校验算法结果，便于反推设备用的算法。

纯转换逻辑在 convert.py（Qt-free 可单测），校验复用 CommTool.compute_checksum + CHECKSUM_KEYS。
单实例非模态，随主窗刷新主题/语言。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QLineEdit, QComboBox, QCheckBox,
                             QTabWidget, QPushButton, QScrollArea,
                             QHBoxLayout, QVBoxLayout, QGridLayout)

from protocol import convert
from ui.theme import chrome_for
from ui.fonts import localize_qss
from ui.i18n import CHECKSUM_KEYS
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark
from ui.ui_tips import set_tooltip

_SEQ_KEYS = ("hex", "text", "dec", "bin")       # 字节序列四种表示
_VAL_KEYS = ("dec", "hex", "bin", "oct")        # 单值四种进制


class ToolboxDialog(QDialog):
    _LBL_W = 68

    def __init__(self, app):
        super().__init__(None)          # parent=None：同其它子对话框，避免干扰无边框主窗
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(640, 560)
        self.resize(760, 620)
        self._syncing = False
        self._seq_data = b""            # 字节序列当前有效数据，供解释区复用
        self._val_raw = 0               # 单值转换：当前有效的无符号 raw（供切位宽/符号后重排）

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_convert_tab()
        self._build_checksum_tab()

        # 「?」说明按钮：做成 tab 栏的子控件、手动定位到右端并与标签垂直居中（既与 tab 齐平又保证可见）
        self.btn_help = QPushButton("?", self.tabs)
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(lambda *_: self._show_help_dlg())

        self.retranslate()
        self.refresh_theme()
        QTimer.singleShot(0, self._position_help_btn)

    def _position_help_btn(self):
        """把「?」放到 tab 栏右端、与标签垂直居中（随窗口尺寸变化重定位）。"""
        bar = self.tabs.tabBar()
        bar_h = bar.height() or bar.sizeHint().height()
        x = self.tabs.width() - self.btn_help.width() - 6
        # 以 QTabBar 在 QTabWidget 内的实际 y 为基准（不假设 y=0，兼容不同风格 / Qt 版本的内边距）
        y = bar.geometry().y() + max(0, (bar_h - self.btn_help.height()) // 2)
        self.btn_help.move(max(0, x), y)
        self.btn_help.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_help_btn()

    def showEvent(self, e):
        super().showEvent(e)
        self._position_help_btn()

    # ================= 页签①：进制/编码转换 =================
    def _build_convert_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 8, 4, 4)
        v.setSpacing(6)

        # —— 字节序列 ——
        self.lbl_seq = QLabel()
        self.lbl_seq.setObjectName("TbSection")
        v.addWidget(self.lbl_seq)
        self._seq = {}
        for key in _SEQ_KEYS:
            h = QHBoxLayout()
            h.setSpacing(6)
            lb = QLabel()
            lb.setObjectName("TbFieldLbl")
            lb.setFixedWidth(self._LBL_W)
            ed = QLineEdit()
            ed.setObjectName("TbMono")
            ed.textEdited.connect(lambda _t, k=key: self._on_seq_edit(k))
            self._seq[key] = (lb, ed)
            h.addWidget(lb)
            h.addWidget(ed, 1)
            v.addLayout(h)

        interp_head = QHBoxLayout()
        interp_head.setSpacing(8)
        self.lbl_interp = QLabel()
        self.lbl_interp.setObjectName("TbSection")
        interp_head.addWidget(self.lbl_interp)
        interp_head.addStretch(1)
        self.lbl_endian = QLabel()
        interp_head.addWidget(self.lbl_endian)
        self.cb_endian = QComboBox()
        self.cb_endian.addItems(["BE", "LE"])
        self.cb_endian.setFixedWidth(64)
        self.cb_endian.currentIndexChanged.connect(self._update_interp)
        interp_head.addWidget(self.cb_endian)
        v.addLayout(interp_head)

        interp_grid = QGridLayout()
        interp_grid.setHorizontalSpacing(6)
        interp_grid.setVerticalSpacing(4)
        interp_grid.setColumnMinimumWidth(0, self._LBL_W)   # 标签列与其它区同宽 → 左列框左对齐
        interp_grid.setColumnMinimumWidth(2, self._LBL_W)
        self._interp = {}
        for row, key in enumerate(("ascii", "u16", "i16", "u32", "i32", "f32")):
            lb = QLabel()
            lb.setObjectName("TbFieldLbl")
            ed = QLineEdit()
            ed.setObjectName("TbMono")
            ed.setReadOnly(True)
            self._interp[key] = (lb, ed)
            interp_grid.addWidget(lb, row // 2, (row % 2) * 2)
            interp_grid.addWidget(ed, row // 2, (row % 2) * 2 + 1)
        interp_grid.setColumnStretch(1, 1)
        interp_grid.setColumnStretch(3, 1)
        v.addLayout(interp_grid)

        v.addSpacing(6)

        # —— 单值多进制 ——
        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_val = QLabel()
        self.lbl_val.setObjectName("TbSection")
        top.addWidget(self.lbl_val)
        top.addStretch(1)
        self.lbl_width = QLabel()
        top.addWidget(self.lbl_width)
        self.cb_width = QComboBox()
        self.cb_width.addItems(["8", "16", "32", "64"])
        self.cb_width.setCurrentText("32")
        self.cb_width.setFixedWidth(64)
        self.cb_width.currentIndexChanged.connect(self._on_val_reformat)
        top.addWidget(self.cb_width)
        self.chk_signed = QCheckBox()
        self.chk_signed.toggled.connect(self._on_val_reformat)
        top.addWidget(self.chk_signed)
        v.addLayout(top)

        self._val = {}
        for key in _VAL_KEYS:
            h = QHBoxLayout()
            h.setSpacing(6)
            lb = QLabel()
            lb.setObjectName("TbFieldLbl")
            lb.setFixedWidth(self._LBL_W)
            ed = QLineEdit()
            ed.setObjectName("TbMono")
            ed.textEdited.connect(lambda _t, k=key: self._on_val_edit(k))
            self._val[key] = (lb, ed)
            h.addWidget(lb)
            h.addWidget(ed, 1)
            v.addLayout(h)

        bits_row = QHBoxLayout()
        bits_row.setSpacing(6)
        self.lbl_bits = QLabel()
        self.lbl_bits.setObjectName("TbFieldLbl")
        self.lbl_bits.setFixedWidth(self._LBL_W)
        self.ed_bits = QLineEdit()
        self.ed_bits.setObjectName("TbMono")
        self.ed_bits.textEdited.connect(self._on_bits_edit)
        bits_row.addWidget(self.lbl_bits)
        bits_row.addWidget(self.ed_bits, 1)
        v.addLayout(bits_row)

        v.addStretch(1)
        self.lbl_conv_hint = QLabel()
        self.lbl_conv_hint.setObjectName("TbHint")
        self.lbl_conv_hint.setWordWrap(True)
        v.addWidget(self.lbl_conv_hint)
        self.tabs.addTab(page, "")

    def _cur_width(self):
        try:
            return int(self.cb_width.currentText())
        except ValueError:
            return 32

    def _on_seq_edit(self, which):
        if self._syncing:
            return
        _lb, ed = self._seq[which]
        c = chrome_for(self.app._theme_id())
        try:
            if which == "hex":
                data = convert.hex_to_bytes(ed.text())
            elif which == "text":
                data = convert.text_to_bytes(ed.text())
            elif which == "dec":
                data = convert.dec_to_bytes(ed.text())
            else:
                data = convert.bin_to_bytes(ed.text())
        except Exception:
            ed.setStyleSheet("border: 1px solid %s;" % c["danger"])
            return
        ed.setStyleSheet("")
        self._seq_data = data
        reps = {"hex": convert.bytes_to_hex(data), "text": convert.bytes_to_text(data),
                "dec": convert.bytes_to_dec(data), "bin": convert.bytes_to_bin(data)}
        self._syncing = True
        try:
            for k, (_l, e) in self._seq.items():
                if k != which:
                    e.setText(reps[k])
                    e.setStyleSheet("")
        finally:
            self._syncing = False
        self._update_interp()

    def _update_interp(self, *_):
        if not hasattr(self, "_interp"):
            return
        endian = "le" if self.cb_endian.currentText() == "LE" else "be"
        vals = convert.interpret_bytes(self._seq_data, endian)
        for k, (_l, e) in self._interp.items():
            e.setText(vals.get(k, ""))

    def _on_val_edit(self, which):
        if self._syncing:
            return
        _lb, ed = self._val[which]
        c = chrome_for(self.app._theme_id())
        try:
            raw = convert.parse_value(ed.text(), which, self._cur_width())
        except Exception:
            ed.setStyleSheet("border: 1px solid %s;" % c["danger"])
            return
        ed.setStyleSheet("")
        self._val_raw = raw
        self._apply_val(skip=which)

    def _on_bits_edit(self, *_):
        if self._syncing:
            return
        c = chrome_for(self.app._theme_id())
        try:
            raw = convert.parse_bits(self.ed_bits.text(), self._cur_width())
        except Exception:
            self.ed_bits.setStyleSheet("border: 1px solid %s;" % c["danger"])
            return
        self.ed_bits.setStyleSheet("")
        self._val_raw = raw
        self._apply_val(skip="bits")

    def _on_val_reformat(self, *_):
        # 切位宽/符号：把当前 raw 重新钳进新位宽再全部重排
        self._val_raw &= (1 << self._cur_width()) - 1
        self._apply_val(skip=None)

    def _apply_val(self, skip):
        reps = convert.format_value(self._val_raw, self._cur_width(), self.chk_signed.isChecked())
        self._syncing = True
        try:
            for k, (_l, e) in self._val.items():
                if k != skip:
                    e.setText(reps[k])
                    e.setStyleSheet("")
            if skip != "bits":
                self.ed_bits.setText(convert.bits_from_value(self._val_raw, self._cur_width()))
                self.ed_bits.setStyleSheet("")
        finally:
            self._syncing = False

    # ================= 页签②：校验计算 =================
    def _build_checksum_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 8, 4, 4)
        v.setSpacing(6)

        # 输入行 + 全算法结果放进同一网格 → 输入框与结果框左右对齐（col0 标签 / col1 数据 / col2 开关）
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self.lbl_ck_in = QLabel()
        self.lbl_ck_in.setObjectName("TbFieldLbl")
        self.ed_ck_in = QLineEdit()
        self.ed_ck_in.setObjectName("TbMono")
        self.ed_ck_in.textChanged.connect(self._recompute_checksums)
        self.chk_ck_text = QCheckBox()
        self.chk_ck_text.toggled.connect(self._recompute_checksums)
        grid.addWidget(self.lbl_ck_in, 0, 0)
        grid.addWidget(self.ed_ck_in, 0, 1)
        grid.addWidget(self.chk_ck_text, 0, 2)

        self.lbl_ck_res = QLabel()
        self.lbl_ck_res.setObjectName("TbSection")
        grid.addWidget(self.lbl_ck_res, 1, 0, 1, 3)     # 结果标题跨三列

        self._ck_rows = []              # (algo_index, name_label, result_edit)
        r = 2
        for i, k in enumerate(CHECKSUM_KEYS):
            if i == 0:
                continue                # 0=无
            name = QLabel()
            name.setObjectName("TbFieldLbl")
            name.setProperty("ck_key", k)
            res = QLineEdit()
            res.setObjectName("TbMono")
            res.setReadOnly(True)
            grid.addWidget(name, r, 0)
            grid.addWidget(res, r, 1)
            self._ck_rows.append((i, name, res))
            r += 1
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)

        self.lbl_ck_custom = QLabel()
        self.lbl_ck_custom.setObjectName("TbSection")
        v.addWidget(self.lbl_ck_custom)

        custom = QGridLayout()
        custom.setHorizontalSpacing(8)
        custom.setVerticalSpacing(5)
        self.lbl_crc_width = QLabel()
        self.lbl_crc_width.setObjectName("TbFieldLbl")
        self.cb_crc_width = QComboBox()
        self.cb_crc_width.addItems(["8", "16", "32", "64"])
        self.cb_crc_width.setCurrentText("16")
        self.cb_crc_width.currentIndexChanged.connect(self._recompute_checksums)
        self.lbl_crc_poly = QLabel()
        self.lbl_crc_poly.setObjectName("TbFieldLbl")
        self.ed_crc_poly = QLineEdit("8005")
        self.ed_crc_poly.setObjectName("TbMono")
        self.ed_crc_poly.textChanged.connect(self._recompute_checksums)
        self.lbl_crc_init = QLabel()
        self.lbl_crc_init.setObjectName("TbFieldLbl")
        self.ed_crc_init = QLineEdit("FFFF")
        self.ed_crc_init.setObjectName("TbMono")
        self.ed_crc_init.textChanged.connect(self._recompute_checksums)
        self.lbl_crc_xor = QLabel()
        self.lbl_crc_xor.setObjectName("TbFieldLbl")
        self.ed_crc_xor = QLineEdit("0000")
        self.ed_crc_xor.setObjectName("TbMono")
        self.ed_crc_xor.textChanged.connect(self._recompute_checksums)
        self.chk_crc_refin = QCheckBox()
        self.chk_crc_refin.setChecked(True)
        self.chk_crc_refin.toggled.connect(self._recompute_checksums)
        self.chk_crc_refout = QCheckBox()
        self.chk_crc_refout.setChecked(True)
        self.chk_crc_refout.toggled.connect(self._recompute_checksums)
        self.lbl_crc_order = QLabel()
        self.lbl_crc_order.setObjectName("TbFieldLbl")
        self.cb_crc_order = QComboBox()
        self.cb_crc_order.addItems(["BE", "LE"])
        self.cb_crc_order.setCurrentText("LE")
        self.cb_crc_order.currentIndexChanged.connect(self._recompute_checksums)
        self.lbl_crc_result = QLabel()
        self.lbl_crc_result.setObjectName("TbFieldLbl")
        self.ed_crc_result = QLineEdit()
        self.ed_crc_result.setObjectName("TbMono")
        self.ed_crc_result.setReadOnly(True)

        custom.addWidget(self.lbl_crc_width, 0, 0)
        custom.addWidget(self.cb_crc_width, 0, 1)
        custom.addWidget(self.lbl_crc_poly, 0, 2)
        custom.addWidget(self.ed_crc_poly, 0, 3)
        custom.addWidget(self.lbl_crc_init, 1, 0)
        custom.addWidget(self.ed_crc_init, 1, 1)
        custom.addWidget(self.lbl_crc_xor, 1, 2)
        custom.addWidget(self.ed_crc_xor, 1, 3)
        custom.addWidget(self.chk_crc_refin, 2, 0)
        custom.addWidget(self.chk_crc_refout, 2, 1)
        custom.addWidget(self.lbl_crc_order, 2, 2)
        custom.addWidget(self.cb_crc_order, 2, 3)
        custom.addWidget(self.lbl_crc_result, 3, 0)
        custom.addWidget(self.ed_crc_result, 3, 1, 1, 3)
        custom.setColumnStretch(3, 1)
        v.addLayout(custom)

        v.addStretch(1)
        self.lbl_ck_hint = QLabel()
        self.lbl_ck_hint.setObjectName("TbHint")
        self.lbl_ck_hint.setWordWrap(True)
        v.addWidget(self.lbl_ck_hint)
        self.tabs.addTab(page, "")

    def _recompute_checksums(self, *_):
        if not hasattr(self, "_ck_rows"):
            return
        c = chrome_for(self.app._theme_id())
        raw = self.ed_ck_in.text()
        try:
            data = convert.text_to_bytes(raw) if self.chk_ck_text.isChecked() \
                else convert.hex_to_bytes(raw)
        except Exception:
            self.ed_ck_in.setStyleSheet("border: 1px solid %s;" % c["danger"])
            for _i, _n, res in self._ck_rows:
                res.setText("")
            if hasattr(self, "ed_crc_result"):
                self.ed_crc_result.setText("")
            return
        self.ed_ck_in.setStyleSheet("")
        for idx, _name, res in self._ck_rows:
            try:
                res.setText(self.app.compute_checksum(data, idx).hex(" ").upper())
            except Exception:
                res.setText("")
        self._recompute_custom_crc(data)

    @staticmethod
    def _parse_crc_int(s):
        s = str(s).strip()
        if not s:
            raise ValueError("empty")
        return int(s[2:] if s.lower().startswith("0x") else s, 16)

    def _recompute_custom_crc(self, data):
        c = chrome_for(self.app._theme_id())
        edits = (self.ed_crc_poly, self.ed_crc_init, self.ed_crc_xor)
        if not data:
            self.ed_crc_result.setText("")
            for ed in edits:
                ed.setStyleSheet("")
            return
        try:
            width = int(self.cb_crc_width.currentText())
            poly = self._parse_crc_int(self.ed_crc_poly.text())
            init = self._parse_crc_int(self.ed_crc_init.text())
            xorout = self._parse_crc_int(self.ed_crc_xor.text())
            order = "little" if self.cb_crc_order.currentText() == "LE" else "big"
            out = convert.custom_crc(data, width=width, poly=poly, init=init,
                                     refin=self.chk_crc_refin.isChecked(),
                                     refout=self.chk_crc_refout.isChecked(),
                                     xorout=xorout, byteorder=order)
        except Exception:
            for ed in edits:
                ed.setStyleSheet("border: 1px solid %s;" % c["danger"])
            self.ed_crc_result.setText("")
            return
        for ed in edits:
            ed.setStyleSheet("")
        self.ed_crc_result.setText(out.hex(" ").upper())

    # ================= 帮助 =================
    def _show_help_dlg(self):
        """弹独立窗口看用法说明（富文本、可滚动可复制），同帧构造器。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("tb_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                           | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(680, 480)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("tb_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        v.addWidget(scroll, 1)
        btn = QPushButton({"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
        btn.setObjectName("PlotGhostBtn")
        btn.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(
            "QDialog {{ background-color: {bg}; }}"
            "QLabel {{ color: {txt}; background: transparent; font-family: 'Segoe UI'; font-size: 12px; }}"
            "QScrollArea {{ background: transparent; border: 1px solid {sep}; border-radius: 6px; }}"
            "QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            "QPushButton#PlotGhostBtn {{ background-color: {gb}; color: {txt}; border: 0px;"
            " border-radius: 8px; font-size: 12px; padding: 6px 16px; }}"
            "QPushButton#PlotGhostBtn:hover {{ background-color: {gh}; }}".format(
                bg=c["window_bg"], txt=c["text"], sep=c["separator"], gb=c["ghost_bg"], gh=c["ghost_hover"])))
        _set_win_titlebar_dark(dlg, c)
        dlg.exec_()

    # ================= 语言 / 主题 =================
    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("tb_title"))
        set_tooltip(self.btn_help, t("tb_help_btn"))
        self.tabs.setTabText(0, t("tb_tab_convert"))
        self.tabs.setTabText(1, t("tb_tab_checksum"))
        self.lbl_seq.setText(t("tb_seq_title"))
        for key in _SEQ_KEYS:
            self._seq[key][0].setText(t("tb_seq_%s" % key))
        self.lbl_interp.setText(t("tb_interp_title"))
        self.lbl_endian.setText(t("tb_endian"))
        for key in ("ascii", "u16", "i16", "u32", "i32", "f32"):
            self._interp[key][0].setText(t("tb_interp_%s" % key))
        self.lbl_val.setText(t("tb_val_title"))
        self.lbl_width.setText(t("tb_width"))
        self.chk_signed.setText(t("tb_signed"))
        for key in _VAL_KEYS:
            self._val[key][0].setText(t("tb_val_%s" % key))
        self.lbl_bits.setText(t("tb_bits"))
        self.lbl_conv_hint.setText(t("tb_conv_hint"))
        self.lbl_ck_in.setText(t("tb_ck_input"))
        self.chk_ck_text.setText(t("tb_ck_text"))
        self.lbl_ck_res.setText(t("tb_ck_result"))
        for _i, name, _res in self._ck_rows:
            name.setText(t(name.property("ck_key")))
        self.lbl_ck_custom.setText(t("tb_ck_custom"))
        self.lbl_crc_width.setText(t("tb_crc_width"))
        self.lbl_crc_poly.setText(t("tb_crc_poly"))
        self.lbl_crc_init.setText(t("tb_crc_init"))
        self.lbl_crc_xor.setText(t("tb_crc_xor"))
        self.chk_crc_refin.setText(t("tb_crc_refin"))
        self.chk_crc_refout.setText(t("tb_crc_refout"))
        self.lbl_crc_order.setText(t("tb_crc_order"))
        self.lbl_crc_result.setText(t("tb_crc_result"))
        # CRC 各参数悬停中文解释（标签 + 对应控件都挂上）
        for widgets, key in (
                ((self.lbl_crc_width, self.cb_crc_width), "tb_crc_width_tip"),
                ((self.lbl_crc_poly, self.ed_crc_poly), "tb_crc_poly_tip"),
                ((self.lbl_crc_init, self.ed_crc_init), "tb_crc_init_tip"),
                ((self.lbl_crc_xor, self.ed_crc_xor), "tb_crc_xor_tip"),
                ((self.chk_crc_refin,), "tb_crc_refin_tip"),
                ((self.chk_crc_refout,), "tb_crc_refout_tip"),
                ((self.lbl_crc_order, self.cb_crc_order), "tb_crc_order_tip")):
            for wdg in widgets:
                set_tooltip(wdg, t(key))
        self.lbl_ck_hint.setText(t("tb_ck_hint"))

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(self, c)
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + """
            QTabWidget::pane {{ border: 1px solid {sep}; border-radius: 8px; top: -1px; }}
            QTabBar::tab {{ background: {gb}; color: {sec}; padding: 6px 16px;
                border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
            QTabBar::tab:selected {{ background: {acc}; color: white; }}
            QLabel#TbSection {{ color: {txt}; font-weight: 600; font-size: 12px; }}
            QLabel#TbFieldLbl {{ color: {sec}; font-size: 12px; }}
            QLabel#TbHint {{ color: {sec}; font-size: 11px; }}
            QLineEdit#TbMono {{ font-family: 'Consolas'; }}
            QLineEdit#TbMono[readOnly="true"] {{ background-color: {gb}; }}
            QPushButton#ArHelpBtn {{ background-color: {gb}; color: {sec}; border: 0px;
                border-radius: 12px; font-family: 'Segoe UI'; font-size: 14px; font-weight: 600; }}
            QPushButton#ArHelpBtn:hover {{ background-color: {gh}; color: {txt}; }}
        """.format(sep=c["separator"], gb=c["ghost_bg"], sec=c["text_sec"],
                   acc=c["accent"], txt=c["text"], gh=c["ghost_hover"])))
        # 弹出下拉随主题上色，避免深色主题露白边
        for cb in (self.cb_width, self.cb_endian, self.cb_crc_width, self.cb_crc_order):
            cb.view().window().setStyleSheet("background-color: %s;" % c["combo_dropdown_bg"])

    def closeEvent(self, e):
        self.app.settings.sync()
        super().closeEvent(e)
