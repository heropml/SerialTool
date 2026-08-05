# -*- coding: utf-8 -*-
"""帧构造器 FrameBuilderDialog —— 字段化拼帧 + 协议模板，实时出 HEX，可填入发送框 / 直接发送。

是「帧解析」(frame_dialog)的镜像：复用 binproto 的类型词汇(HEX_FMT)与新增的 pack_field/build_frame，
校验字段复用 CommTool.compute_checksum。每行一个字段：名称 / 类型 / 值；校验、长度为「自动字段」(值由
其他字段算出)。内置 Modbus/AT/NMEA 模板一键填充。单实例非模态，随主窗刷新主题/语言，字段定义持久化。
MVP 不含：位域、范围可配置、模板保存、剪贴板、插入序列（见计划二期）。
"""
import json

from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint, QMimeData
from PyQt5.QtGui import QDrag, QFont, QFontMetrics
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QFrame, QLineEdit,
                             QComboBox, QHBoxLayout, QVBoxLayout, QScrollArea, QSplitter)

import binproto
from theme import chrome_for
from fonts import localize_qss
from i18n import CHECKSUM_KEYS
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _DragHandle
from ui_tips import set_tooltip

# 内置模板：key -> [(kind, typ, value, name), ...]。name 为默认标签(可编辑，不影响拼出的字节)。
# checksum 的 typ 是 CHECKSUM_KEYS 下标(5=ModbusCRC16)；length 的 typ 是编码宽度。
# 只放适合「二进制帧」模型的模板：Modbus(二进制+尾部CRC)、AT(ascii+CRLF)。NMEA 是 ASCII 协议、
# 校验排除 $ 且以 ASCII-hex 文本传，不适合本构造器，留二期(需 ascii-hex 校验变体)。
_TEMPLATES = {
    "modbus_read": [("num", "u8", "1", "unit"), ("num", "u8", "3", "func"),
                    ("num", "u16be", "0", "addr"), ("num", "u16be", "1", "qty"),
                    ("checksum", 5, "", "CRC16")],
    "modbus_write": [("num", "u8", "1", "unit"), ("num", "u8", "6", "func"),
                     ("num", "u16be", "0", "addr"), ("num", "u16be", "0", "value"),
                     ("checksum", 5, "", "CRC16")],
    "at": [("ascii", "ascii", "AT", "cmd"), ("hex", "hex", "0D 0A", "CRLF")],
}
_TEMPLATE_ORDER = ["custom", "modbus_read", "modbus_write", "at"]


class FrameBuilderDialog(QDialog):
    _DEL_W = 24
    _DATA_MIN_W = 56               # 名称/类型/值 三列最小宽（表头标签与行控件取同值 → 任意宽度都对齐）
    _MAX_FIELDS = 500              # 防异常配置同步创建海量 Qt 控件卡死 GUI
    _MAX_CFG_CHARS = 2 * 1024 * 1024
    _MAX_SPLIT_SIZE = 10000        # QSplitter.setSizes 走 C++ int；同时拒绝无意义的巨宽配置

    def __init__(self, app):
        super().__init__(None)          # parent=None：同其它子对话框，避免干扰无边框主窗
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(680, 300)
        self.resize(860, 420)
        self._loading = False
        self._rows = []
        self._drag_frame = None                 # 拖拽排序：当前被拖的行 frame
        # 列宽拖拽：名称/类型/值 放进 3 面板 splitter，所有行 + 表头共享同一比例、持久化
        self._type_w = self._combo_w([lbl for _k, _t, lbl in self._type_items()], 90)
        self._DEFAULT_SPLIT = [120, self._type_w, 300]   # 名称/类型/值 初始宽（拖分隔条后落盘）
        self._split_sizes = self._load_split_sizes()     # 上次拖好的列宽（列数不符则 None → 用默认）
        self._syncing_split = False              # 防止同步分隔条时递归
        self._fields_cfg = self._load_fields()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._commit)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_tmpl = QLabel()
        self.cb_tmpl = QComboBox()
        self.cb_tmpl.setFixedWidth(150)
        for k in _TEMPLATE_ORDER:
            self.cb_tmpl.addItem("", k)
        self.cb_tmpl.activated.connect(self._on_template)
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._schedule()))
        self.btn_fill = QPushButton()
        self.btn_fill.setObjectName("PlotGhostBtn")
        self.btn_fill.clicked.connect(self._on_fill)
        self.btn_send = QPushButton()
        self.btn_send.setObjectName("DialogPrimaryBtn")
        self.btn_send.setMinimumHeight(30)
        self.btn_send.clicked.connect(self._on_send)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(lambda *_: self._show_help_dlg())
        top.addWidget(self.lbl_tmpl)
        top.addWidget(self.cb_tmpl)
        top.addWidget(self.btn_add)
        top.addStretch(1)
        top.addWidget(self.btn_fill)
        top.addWidget(self.btn_send)
        top.addWidget(self.btn_help)
        root.addLayout(top)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("ArDesc")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        # 表头：名称/类型/值 放进可拖 3 面板 splitter（与每行同步）；☰、✕ 两列固定
        self.hdr = QWidget()
        self._hdr_layout = hh = QHBoxLayout(self.hdr)
        hh.setContentsMargins(10, 2, 10, 2)
        hh.setSpacing(6)
        hh.addSpacing(18)                       # 对齐每行左侧的拖拽手柄（宽 18）
        self._hdr_labels = []
        self._hdr_split = self._make_split()
        for key in ("fb_col_name", "fb_col_type", "fb_col_value"):
            lb = QLabel()
            lb.setObjectName("SeqHdr")
            lb.setProperty("k", key)
            lb.setMinimumWidth(self._DATA_MIN_W)
            self._hdr_split.addWidget(lb)
            self._hdr_labels.append(lb)
        self._hdr_split.setSizes(self._split_sizes or self._DEFAULT_SPLIT)
        self._hdr_split.splitterMoved.connect(lambda *_: self._sync_splits(self._hdr_split))
        hh.addWidget(self._hdr_split, 1)
        hh.addSpacing(self._DEL_W)               # 对齐每行右侧的 ✕ 删除按钮
        root.addWidget(self.hdr)

        host = QWidget()
        host.setObjectName("MsListHost")
        self._list_host = host                  # 拖拽排序：容器接收 drop 按落点重排行
        host.setAcceptDrops(True)
        host.installEventFilter(self)
        self.rows_v = QVBoxLayout(host)
        self.rows_v.setContentsMargins(0, 0, 0, 0)
        self.rows_v.setSpacing(5)
        self.rows_v.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("MsScroll")
        self.scroll.setWidget(host)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._update_header_scroll_margin)
        root.addWidget(self.scroll, 1)

        # 底部：实时 HEX 输出 + 字节数/错误
        out = QHBoxLayout()
        out.setSpacing(8)
        self.lbl_out = QLabel()
        self.ed_out = QLineEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setObjectName("FbOut")
        self.lbl_bytes = QLabel()
        out.addWidget(self.lbl_out)
        out.addWidget(self.ed_out, 1)
        out.addWidget(self.lbl_bytes)
        root.addLayout(out)

        self.reload_rows()
        self.retranslate()
        self.refresh_theme()
        QTimer.singleShot(0, self._update_header_scroll_margin)

    # ---------------- 类型下拉项 ----------------
    def _type_items(self):
        """类型下拉的 (kind, typ, 显示文本) 列表（随语言刷新）。"""
        t = self.app._t
        items = [("num", n, n) for n in binproto.HEX_FMT.keys()]
        items.append(("ascii", "ascii", "ascii"))
        items.append(("hex", "hex", "hex"))
        for i, k in enumerate(CHECKSUM_KEYS):
            if i == 0:
                continue                    # 0=无，不作校验字段
            items.append(("checksum", i, "%s: %s" % (t("fb_type_checksum"), t(k))))
        items.append(("length", "u8", "%s: u8" % t("fb_type_length")))
        items.append(("length", "u16be", "%s: u16be" % t("fb_type_length")))
        return items

    # ---------------- 行 ----------------
    def _add_row(self, field=None):
        if len(self._rows) >= self._MAX_FIELDS:
            if not self._loading:
                self.app.toast(self.app._t("fb_fields_limit", n=self._MAX_FIELDS), error=True)
            return
        kind, typ, value, name = field or ("num", "u8", "0", "")
        d = {}
        frame = QFrame()
        frame.setObjectName("MsRow")
        d["frame"] = frame
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 5, 10, 5)
        h.setSpacing(6)

        d["grip"] = _DragHandle(self, frame)
        h.addWidget(d["grip"])                 # 拖拽手柄：拖它改变字段顺序（拼帧字节序随之变）

        d["name"] = QLineEdit("" if name is None else str(name))
        d["name"].setMinimumWidth(self._DATA_MIN_W)
        d["name"].textChanged.connect(self._schedule)

        cb = QComboBox()
        cb.setMinimumWidth(self._DATA_MIN_W)
        sel, found = 0, False
        for n, (k, ty, label) in enumerate(self._type_items()):
            cb.addItem(label, (k, ty))
            if k == kind and str(ty) == str(typ):
                sel, found = n, True
        if not found:
            # 未知/不支持的类型：原样保留并显式选中，绝不静默落到首项(u8)——
            # 拼帧时 build_frame 会对它报错标红，不会悄悄改变实际发送字节。
            cb.addItem("%s:%s (?)" % (kind, typ), (kind, typ))
            sel = cb.count() - 1
        cb.setCurrentIndex(sel)
        cb.currentIndexChanged.connect(lambda *_, dd=d: self._on_type_changed(dd))
        d["type"] = cb

        d["val"] = QLineEdit("" if value is None else str(value))
        d["val"].setMinimumWidth(self._DATA_MIN_W)
        d["val"].textChanged.connect(self._schedule)

        # 名称/类型/值 装进 3 面板 splitter：拖分隔条调列宽，所有行 + 表头同步、持久化
        split = self._make_split()
        split.addWidget(d["name"])
        split.addWidget(cb)
        split.addWidget(d["val"])
        split.setSizes(self._split_sizes or self._DEFAULT_SPLIT)
        split.splitterMoved.connect(lambda *_, s=split: self._sync_splits(s))
        d["split"] = split
        h.addWidget(split, 1)

        btn = QPushButton("✕")
        btn.setObjectName("MsDelBtn")
        btn.setFixedWidth(self._DEL_W)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda *_, dd=d: self._del_row(dd))
        d["del"] = btn
        h.addWidget(btn)

        self.rows_v.insertWidget(self.rows_v.count() - 1, frame)
        self._rows.append(d)
        self._apply_val_enabled(d)
        c = chrome_for(self.app._theme_id())
        cb.view().window().setStyleSheet("background-color: %s;" % c["combo_dropdown_bg"])

    def _del_row(self, d):
        if d in self._rows:
            self._rows.remove(d)
        d["frame"].setParent(None)
        d["frame"].deleteLater()
        self._schedule()

    # ---------------- 拖拽排序 ----------------
    def eventFilter(self, obj, event):
        """容器 host 接收字段行的 drag/drop（手柄发起、按落点重排）。"""
        if obj is self._list_host:
            et = event.type()
            if et in (QEvent.DragEnter, QEvent.DragMove):
                if event.mimeData().hasFormat("application/x-fbfield-row"):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Drop:
                if event.mimeData().hasFormat("application/x-fbfield-row"):
                    self._on_row_drop(event.pos().y())
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.DragLeave:
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _begin_row_drag(self, frame):
        """行手柄按下：发起 QDrag，用整行截图作拖拽影像。"""
        self._drag_frame = frame
        drag = QDrag(frame)
        mime = QMimeData()
        mime.setData("application/x-fbfield-row", b"1")
        drag.setMimeData(mime)
        pm = frame.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(12, pm.height() // 2))
        drag.exec_(Qt.MoveAction)
        self._drag_frame = None

    def _on_row_drop(self, y):
        """按落点 y 把被拖的字段行插到目标位置，重排 _rows + 布局，并触发重算/落盘。"""
        src = self._drag_frame
        if src is None:
            return
        frames = [r["frame"] for r in self._rows]
        if src not in frames:
            return
        src_idx = frames.index(src)
        target = len(frames)
        for i, f in enumerate(frames):
            if y < f.y() + f.height() / 2:     # 落点在某行上半 → 插到它之前
                target = i
                break
        if target > src_idx:                   # 源行移除后其后目标索引前移 1
            target -= 1
        if target < 0 or target == src_idx:
            return
        row = self._rows.pop(src_idx)
        self._rows.insert(target, row)
        self.rows_v.removeWidget(src)
        self.rows_v.insertWidget(target, src)
        self._schedule()                       # 顺序变 → 重算 HEX + 落盘

    # ---------------- 列宽拖拽 ----------------
    def _combo_w(self, labels, min_w):
        """按下拉选项里最长文案算列宽：最长项像素宽 + 箭头/内边距余量，不小于 min_w。"""
        f = QFont("Segoe UI")
        f.setPixelSize(11)                     # 与 QComboBox 的 QSS 字号一致
        fm = QFontMetrics(f)
        need = max((fm.horizontalAdvance(s) for s in labels), default=0)
        return max(min_w, need + 32)           # +32 = 箭头(16)+内边距(12)+边框(~4)

    def _make_split(self):
        sp = QSplitter(Qt.Horizontal)
        sp.setObjectName("MsColSplit")
        sp.setChildrenCollapsible(False)
        sp.setHandleWidth(8)
        return sp

    def _load_split_sizes(self):
        """从 settings 读上次拖好的列宽 'w1,w2,w3'；列数不符/非法则 None（用默认）。"""
        raw = self.app.settings.value("frame_builder_split", "")
        try:
            parts = [int(x) for x in str(raw).split(",")]
            if (len(parts) == len(self._DEFAULT_SPLIT)
                    and all(0 < p <= self._MAX_SPLIT_SIZE for p in parts)):
                return parts
        except (ValueError, TypeError):
            pass
        return None

    def _sync_splits(self, src):
        """任一行(或表头)拖动分隔条 → 所有行 + 表头同步到相同比例（列对齐），并持久化列宽。"""
        if self._syncing_split:
            return
        try:                       # 对话框已关(deleteLater)后 singleShot 仍可能触发 → C++ 已删，忽略
            sizes = src.sizes()
        except RuntimeError:
            return
        if not sizes or sum(sizes) <= 0:
            return
        self._split_sizes = sizes
        self.app.settings.setValue("frame_builder_split", ",".join(str(s) for s in sizes))
        self._syncing_split = True
        try:
            targets = [getattr(self, "_hdr_split", None)] + [r.get("split") for r in self._rows]
            for sp in targets:
                if sp is not None and sp is not src:
                    try:
                        sp.setSizes(sizes)
                    except RuntimeError:
                        pass
        finally:
            self._syncing_split = False

    def _update_header_scroll_margin(self, *_args):
        """数据区出现垂直滚动条时，表头右侧预留同宽空间，保持 splitter 像素对齐。"""
        try:                       # 延迟触发时对话框可能已析构，静默跳过防止槽内异常 abort
            bar = self.scroll.verticalScrollBar()
            extra = bar.sizeHint().width() if bar.maximum() > bar.minimum() else 0
            self._hdr_layout.setContentsMargins(10, 2, 10 + extra, 2)
        except RuntimeError:
            return
        QTimer.singleShot(0, lambda: self._sync_splits(self._hdr_split))

    def _apply_val_enabled(self, d):
        """校验/长度是自动字段 → 禁用值框、给占位提示。"""
        kind = d["type"].currentData()[0]
        auto = kind in ("checksum", "length")
        d["val"].setEnabled(not auto)
        d["val"].setPlaceholderText(self.app._t("fb_auto") if auto else "")
        if auto:
            d["val"].setText("")

    def _on_type_changed(self, d):
        self._apply_val_enabled(d)
        self._schedule()

    def _row_to_field(self, d):
        kind, typ = d["type"].currentData()
        return (kind, typ, d["val"].text(), d["name"].text())

    def _all_fields(self):
        return [self._row_to_field(d) for d in self._rows]

    # ---------------- 拼帧 / 输出 ----------------
    def _built_hex(self):
        """据当前字段拼帧 → (hex_str 或 None, 错误信息 或 None)。"""
        self._error_row = None
        fields = [(k, t, v) for (k, t, v, _n) in self._all_fields()]
        if not fields:
            return "", None
        try:
            data = binproto.build_frame(fields, self.app.compute_checksum)
            return data.hex(" ").upper(), None
        except Exception as e:
            self._error_row = getattr(e, "field_index", None)
            return None, str(e)

    def _rebuild(self):
        c = chrome_for(self.app._theme_id())
        for d in self._rows:
            d["val"].setStyleSheet("")
        hexs, err = self._built_hex()
        if err is not None:
            if isinstance(self._error_row, int) and 0 <= self._error_row < len(self._rows):
                self._rows[self._error_row]["val"].setStyleSheet(
                    "border: 1px solid %s;" % c["danger"])
            self.ed_out.setText("")
            self.lbl_bytes.setText(self.app._t("fb_err", e=err))
            self.lbl_bytes.setStyleSheet("color: %s;" % c["danger"])
            self.btn_fill.setEnabled(False)
            self.btn_send.setEnabled(False)
            return
        self.ed_out.setText(hexs)
        nbytes = 0 if not hexs else len(hexs.split())
        self.lbl_bytes.setText(self.app._t("fb_bytes", n=nbytes))
        self.lbl_bytes.setStyleSheet("color: %s;" % c["text_sec"])
        self.btn_fill.setEnabled(nbytes > 0)
        self.btn_send.setEnabled(nbytes > 0)

    def _on_fill(self):
        hexs, err = self._built_hex()
        if err is not None or not hexs:
            return
        self.app._fb_fill_send(hexs)        # 主窗：填发送框 + 置 HEX 发送态 + toast

    def _on_send(self):
        hexs, err = self._built_hex()
        if err is not None or not hexs:
            return
        # 构造器输出已经是一整帧；不得再继承主界面的追加换行/校验，否则线上字节会被二次改写。
        ok = self.app._send_text(hexs, hex_mode=True, newline=0, checksum=0)
        if ok:
            self.app.toast(self.app._t("fb_sent"))

    # ---------------- 模板 ----------------
    def _on_template(self, _idx):
        key = self.cb_tmpl.currentData()
        if key == "custom" or key not in _TEMPLATES:
            return
        # 套用模板会抹掉当前所有字段 → 有字段时先确认；取消则回到「自定义」、字段不动。
        if self._rows:
            name = self.app._t("fb_tmpl_%s" % key)
            if not self.app._confirm_dlg(self.app._t("fb_tmpl_apply"),
                                         self.app._t("fb_tmpl_apply_confirm", name=name), danger=False):
                self.cb_tmpl.setCurrentIndex(0)
                return
        self._loading = True
        for d in list(self._rows):
            d["frame"].setParent(None)
            d["frame"].deleteLater()
        self._rows = []
        for field in _TEMPLATES[key]:
            self._add_row(field)
        self._loading = False
        self.cb_tmpl.setCurrentIndex(0)     # 选完回到「自定义」，表示当前是编辑态
        self._schedule()

    # ---------------- 持久化 ----------------
    def _load_fields(self):
        raw = self.app.settings.value("frame_builder_fields", "")
        try:
            if isinstance(raw, str) and len(raw) > self._MAX_CFG_CHARS:
                self.app.toast(self.app._t("fb_config_too_large"), error=True)
                return []
            fields = json.loads(raw) if raw else []
            if not isinstance(fields, list):
                return []
            if len(fields) > self._MAX_FIELDS:
                self.app.toast(self.app._t("fb_fields_limit", n=self._MAX_FIELDS), error=True)
                fields = fields[:self._MAX_FIELDS]
            return fields
        except Exception:
            return []

    def _schedule(self):
        if not self._loading:
            self._rebuild()
            self._save_timer.start(400)

    def _commit(self):
        fields = [list(f) for f in self._all_fields()]
        self._fields_cfg = fields
        self.app.settings.setValue("frame_builder_fields", json.dumps(fields, ensure_ascii=False))
        self.app.settings.sync()

    def commit_pending(self):
        """把尚在防抖窗口内的编辑提交到当前 settings；配置槽切换前必须先调用。"""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit()

    def reload_rows(self, discard_pending=False):
        """从当前 settings 重载。外部导入/切换配置时 discard_pending=True，禁止旧草稿反写新配置。"""
        if self._save_timer.isActive():
            self._save_timer.stop()
            if not discard_pending:
                self._commit()
        self._fields_cfg = self._load_fields()
        self._split_sizes = self._load_split_sizes()
        self._hdr_split.setSizes(self._split_sizes or self._DEFAULT_SPLIT)
        self._loading = True
        for d in list(self._rows):
            d["frame"].setParent(None)
            d["frame"].deleteLater()
        self._rows = []
        for f in self._fields_cfg:
            if isinstance(f, (list, tuple)) and len(f) >= 3:
                kind, typ, value = f[0], f[1], f[2]
                name = f[3] if len(f) > 3 else ""
                self._add_row((kind, typ, value, name))
        if not self._rows:                  # 空则给个默认模板，便于直接上手
            for field in _TEMPLATES["modbus_read"]:
                self._add_row(field)
        self._loading = False
        self._rebuild()
        QTimer.singleShot(0, self._update_header_scroll_margin)

    # ---------------- 语言 / 主题 ----------------
    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("fb_title"))
        self.lbl_tmpl.setText(t("fb_template"))
        self.btn_add.setText(t("fb_add"))
        self.btn_fill.setText(t("fb_fill"))
        self.btn_send.setText(t("fb_send"))
        set_tooltip(self.btn_help, t("fb_help_btn"))
        self.lbl_hint.setText(t("fb_hint"))
        self.lbl_out.setText(t("fb_out"))
        for i, k in enumerate(_TEMPLATE_ORDER):
            self.cb_tmpl.setItemText(i, t("fb_tmpl_%s" % k))
        for lb in self._hdr_labels:
            k = lb.property("k")
            lb.setText(t(k) if k else "")
        # 类型下拉项随语言刷新（保留选中）
        items = self._type_items()
        for d in self._rows:
            cb = d["type"]
            cur = cb.currentData()
            cb.blockSignals(True)
            for n, (k, ty, label) in enumerate(items):
                if n < cb.count():
                    cb.setItemText(n, label)
            cb.blockSignals(False)
            set_tooltip(d["grip"], {"zh": "按住拖动改变顺序", "en": "Drag to reorder",
                                   "zh_tw": "按住拖動改變順序"}.get(self.app._lang,
                                                                      "Drag to reorder"))
            self._apply_val_enabled(d)
        self._rebuild()

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(self, c)
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + """
            QLabel#ArDesc {{ color: {sec}; font-size: 11px; }}
            QLabel#SeqHdr {{ color: {sec}; font-size: 11px; font-weight: 600; }}
            QLabel#MsDragGrip {{ color: {sec}; font-size: 13px; }}
            QLabel#MsDragGrip:hover {{ color: {acc}; }}
            QSplitter#MsColSplit {{ background: transparent; }}
            QSplitter#MsColSplit::handle {{ background: {sep}; margin: 5px 3px; border-radius: 1px; }}
            QSplitter#MsColSplit::handle:hover {{ background: {acc}; margin: 3px 3px; }}
            QLineEdit#FbOut {{ font-family: 'Consolas'; }}
            QPushButton#DialogPrimaryBtn {{ background-color: {acc}; color: white; border: 0px;
                border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; padding: 5px 16px; }}
            QPushButton#DialogPrimaryBtn:disabled {{ background-color: {sep}; color: {sec}; }}
            QPushButton#PlotGhostBtn {{ background-color: {gb}; color: {txt}; border: 0px;
                border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 5px 14px; }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {gh}; }}
            QPushButton#ArHelpBtn {{ background-color: {gb}; color: {sec}; border: 0px;
                border-radius: 13px; font-family: 'Segoe UI'; font-size: 14px; font-weight: 600; }}
            QPushButton#ArHelpBtn:hover {{ background-color: {gh}; color: {txt}; }}
        """.format(sec=c["text_sec"], acc=c["accent"], sep=c["separator"], gb=c["ghost_bg"],
                   gh=c["ghost_hover"], txt=c["text"])))
        # 下拉弹出是独立顶层窗，QSS 罩不到窗框 → 单独上色，避免深色主题露白边（含顶部模板下拉）
        for cb in [self.cb_tmpl] + [d["type"] for d in self._rows]:
            cb.view().window().setStyleSheet("background-color: %s;" % c["combo_dropdown_bg"])
        self._rebuild()

    def _show_help_dlg(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("fb_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                           | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(720, 500)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("fb_help"))
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

    def closeEvent(self, e):
        self.commit_pending()
        self.app.settings.sync()
        super().closeEvent(e)
