# -*- coding: utf-8 -*-
"""脚本控制台对话框 ScriptConsoleDialog：多脚本库 + 编辑区 + 运行/停止 + 输出日志。

脚本用 send/expect/sleep/log/check 编排真实收发（执行核心见 script_console.ScriptWorker，
跑在 worker 线程里）。脚本库随配置持久化（script_lib / script_active），导入配置里带脚本时
走与「脚本应答」一致的信任门禁。单实例非模态，复用刷新主题/语言。
"""
import json
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QPushButton, QPlainTextEdit, QSplitter, QScrollArea,
                             QFrame, QInputDialog, QFileDialog)

from automation.script_console import ScriptWorker
from ui.theme import chrome_for
from ui.fonts import localize_qss, mono_font
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui.ui_tips import set_tooltip

_log = logging.getLogger("commtool.script")

_MAX_SCRIPTS = 50          # 脚本库条数上限
_MAX_CODE_CHARS = 200000   # 单脚本字符上限（防坏配置/超大导入）
_MAX_LOG_BLOCKS = 5000     # 输出区行数上限

_DEFAULT_CODE = """\
# CommTool 脚本控制台 —— 点「?」看完整 API
# send/recv/expect/sleep/log/check/hexs

log("开始自检")
send("AT\\r\\n")
r = expect("OK", timeout=1000)
check(r is not None, "AT 应答 OK")

send(hexs("01 03 00 00 00 01 84 0A"))        # Modbus 读保持寄存器（末两字节是 CRC）
r = expect(hexs("01 03"), timeout=500)
check(r is not None, "Modbus 有响应")

log("完成")
"""


class ScriptConsoleDialog(QDialog):
    def __init__(self, app):
        # parent=None：避免干扰主窗 WM_NCHITTEST（同波形图/帧解析）。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(640, 420)
        self.resize(900, 620)

        self._scripts = []        # [{"name": str, "code": str}]
        self._active = 0
        self._worker = None
        self._worker_sid = None   # session that owns self._worker (not the visible tab)
        self._loading = False
        self._warned_code_len = False    # 代码超长提示只弹一次，不随每次按键刷屏

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 顶栏：脚本库 + 管理 =====
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_script = QLabel()
        self.cb_script = QComboBox()
        self.cb_script.setObjectName("ScScript")
        # 不接收焦点：Windows 原生样式会给「聚焦的非可编辑下拉框」画一堆装饰（accent 边框、
        # 用 selection 色涂当前项底、再套一圈焦点虚框），逐个用 QSS 盖不干净，而且离屏渲染
        # 复现不出来。索性不让它拿焦点 —— 外观恒等于主界面那些未聚焦的下拉框。
        # 鼠标点开/选择完全不受影响，焦点始终留在代码区（本来也是打开就该写脚本）。
        self.cb_script.setFocusPolicy(Qt.NoFocus)
        self.cb_script.setMinimumWidth(160)
        # 高度跟同排 PlotGhostBtn 等高：**必须** setFixedHeight，否则会被按钮行纵向拉伸，
        # 而原生样式仍按自然高度在里面画一层框 → 视觉上「框中框」。同 cb_ms_group 的处理，
        # 那里也注明了不能用 setMinimumHeight（会被 QComboBox 在 styleSheet apply 期间的
        # 内部 sizePolicy 计算覆盖回默认 ~22px）。
        self.cb_script.setFixedHeight(28)
        self.cb_script.currentIndexChanged.connect(self._on_script_changed)
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("PlotGhostBtn")
        self.btn_new.clicked.connect(self._on_new)
        self.btn_rename = QPushButton()
        self.btn_rename.setObjectName("PlotGhostBtn")
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_del = QPushButton()
        self.btn_del.setObjectName("PlotGhostBtn")
        self.btn_del.clicked.connect(self._on_delete)
        self.btn_import = QPushButton()
        self.btn_import.setObjectName("PlotGhostBtn")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._on_export)
        bar.addWidget(self.lbl_script)
        bar.addWidget(self.cb_script)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_rename)
        bar.addWidget(self.btn_del)
        bar.addSpacing(8)
        bar.addWidget(self.btn_import)
        bar.addWidget(self.btn_export)
        bar.addStretch(1)
        self.btn_rec = QPushButton()
        self.btn_rec.setObjectName("PlotGhostBtn")
        self.btn_rec.clicked.connect(self._on_record)
        bar.addWidget(self.btn_rec)
        self.btn_run = QPushButton()
        self.btn_run.setObjectName("PlotPrimaryBtn")
        self.btn_run.setMinimumSize(68, 34)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("PlotDangerBtn")
        self.btn_stop.setMinimumSize(68, 34)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setVisible(False)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_stop)
        bar.addWidget(self.btn_help)
        root.addLayout(bar)

        # ===== 编辑区 / 输出区（可拖分隔）=====
        self._split = QSplitter(Qt.Vertical)
        self._split.setObjectName("ScSplit")
        self._split.setChildrenCollapsible(False)
        self.ed_code = QPlainTextEdit()
        self.ed_code.setObjectName("ScCode")
        self.ed_code.setFont(mono_font(11))
        self.ed_code.setTabStopDistance(4 * self.ed_code.fontMetrics().horizontalAdvance(" "))
        self.ed_code.textChanged.connect(self._on_code_changed)
        self.txt_out = QPlainTextEdit()
        self.txt_out.setObjectName("ScOut")
        self.txt_out.setReadOnly(True)
        self.txt_out.setFont(mono_font(11))
        self.txt_out.document().setMaximumBlockCount(_MAX_LOG_BLOCKS)
        self._split.addWidget(self.ed_code)
        self._split.addWidget(self.txt_out)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        self._split.setSizes([360, 200])
        root.addWidget(self._split, 1)

        # ===== 底栏：状态 + 清空输出 =====
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("MsHint")
        foot.addWidget(self.lbl_status, 1)
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("PlotGhostBtn")
        self.btn_clear.clicked.connect(self._clear_out)
        foot.addWidget(self.btn_clear)
        root.addLayout(foot)

        self.retranslate()
        self._load_cfg()
        self.refresh_theme()

    # ---------------- 脚本库持久化 ----------------
    def _load_cfg(self):
        s = self.app.settings
        self._loading = True
        try:
            self._scripts = self.parse_lib(s.value("script_lib", "") or "")
            if not self._scripts:
                self._scripts = [{"name": self.app._t("sc_default_name"), "code": _DEFAULT_CODE}]
            name = s.value("script_active", "") or ""
            self._active = next((i for i, sc in enumerate(self._scripts)
                                 if sc["name"] == name), 0)
            self._rebuild_combo()
            self.ed_code.setPlainText(self._scripts[self._active]["code"])
            self._warned_code_len = False
        finally:
            self._loading = False

    def reload_cfg(self):
        """配置导入/切换后调用：按新配置重建脚本库。"""
        self._load_cfg()

    @staticmethod
    def parse_lib(raw):
        """JSON → [{"name","code"}]；坏数据/超限一律安全过滤。"""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out = []
        for it in data[:_MAX_SCRIPTS]:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            code = str(it.get("code") or "")
            if not name:
                continue
            out.append({"name": name[:80], "code": code[:_MAX_CODE_CHARS]})
        return out

    def _save_cfg(self):
        if self._loading:
            return
        s = self.app.settings
        s.setValue("script_lib", json.dumps(self._scripts, ensure_ascii=False))
        s.setValue("script_active",
                   self._scripts[self._active]["name"] if self._scripts else "")

    def _rebuild_combo(self):
        self.cb_script.blockSignals(True)
        self.cb_script.clear()
        for sc in self._scripts:
            self.cb_script.addItem(sc["name"])
        self.cb_script.setCurrentIndex(max(0, min(self._active, len(self._scripts) - 1)))
        self.cb_script.blockSignals(False)

    # ---------------- 脚本库操作 ----------------
    def _on_script_changed(self, i):
        if self._loading or not (0 <= i < len(self._scripts)):
            return
        self._active = i
        self._loading = True
        try:
            self.ed_code.setPlainText(self._scripts[i]["code"])
        finally:
            self._loading = False
        self._warned_code_len = False
        self._save_cfg()

    def _on_code_changed(self):
        if self._loading or not self._scripts:
            return
        code = self.ed_code.toPlainText()
        if len(code) > _MAX_CODE_CHARS:
            # 超上限只存前 N 字符；编辑器必须同步截断，否则界面看起来还在、保存/重启却丢尾。
            if not self._warned_code_len:
                self._warned_code_len = True
                self.app.toast(self.app._t("sc_code_too_long", n=_MAX_CODE_CHARS), error=True)
            code = code[:_MAX_CODE_CHARS]
            self._loading = True
            try:
                self.ed_code.setPlainText(code)
                cursor = self.ed_code.textCursor()
                cursor.setPosition(len(code))
                self.ed_code.setTextCursor(cursor)
            finally:
                self._loading = False
        else:
            self._warned_code_len = False
        self._scripts[self._active]["code"] = code
        self._save_cfg()

    def _uniq_name(self, base):
        names = {sc["name"] for sc in self._scripts}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def _on_new(self):
        if len(self._scripts) >= _MAX_SCRIPTS:
            self.app.toast(self.app._t("sc_max", n=_MAX_SCRIPTS), error=True)
            return
        name = self._uniq_name(self.app._t("sc_default_name"))
        self._scripts.append({"name": name, "code": _DEFAULT_CODE})
        self._active = len(self._scripts) - 1
        self._rebuild_combo()
        self._loading = True
        try:
            self.ed_code.setPlainText(_DEFAULT_CODE)
        finally:
            self._loading = False
        self._warned_code_len = False
        self._save_cfg()

    def _on_rename(self):
        if not self._scripts:
            return
        cur = self._scripts[self._active]["name"]
        name, ok = QInputDialog.getText(self, self.app._t("sc_rename"),
                                        self.app._t("sc_name_prompt"), text=cur)
        name = (name or "").strip()[:80]
        if not ok or not name or name == cur:
            return
        self._scripts[self._active]["name"] = self._uniq_name(name)
        self._rebuild_combo()
        self._save_cfg()

    def _on_delete(self):
        if len(self._scripts) <= 1:
            self.app.toast(self.app._t("sc_keep_one"), error=True)
            return
        cur = self._scripts[self._active]["name"]
        if not self.app._confirm_dlg(self.app._t("sc_delete"),
                                     self.app._t("sc_delete_warn", name=cur),
                                     ok_text=self.app._t("sc_delete"), danger=True):
            return
        del self._scripts[self._active]
        self._active = max(0, self._active - 1)
        self._rebuild_combo()
        self._loading = True
        try:
            self.ed_code.setPlainText(self._scripts[self._active]["code"])
        finally:
            self._loading = False
        self._warned_code_len = False
        self._save_cfg()

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, self.app._t("sc_export"),
                                              "commtool_scripts.json",
                                              "JSON (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._scripts, f, ensure_ascii=False, indent=2)
            self.app.toast(self.app._t("saved_to", path=path))
        except Exception as e:
            self.app.toast(self.app._t("err_save_failed", e=e), error=True)

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, self.app._t("sc_import"), "",
                                              "JSON (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read(5 * 1024 * 1024)      # 限 5MB
        except Exception as e:
            self.app.toast(self.app._t("err_open_failed", e=e), error=True)
            return
        items = self.parse_lib(raw)
        if not items:
            self.app.toast(self.app._t("sc_import_bad"), error=True)
            return
        # 与「脚本应答」一致的信任门禁：导入的脚本会在本机执行，先征求同意
        if not self.app._ar_confirm(self.app._t("sc_import_title"),
                                    self.app._t("sc_import_warn", n=len(items))):
            return
        added = 0
        for it in items:
            if len(self._scripts) >= _MAX_SCRIPTS:
                break
            it["name"] = self._uniq_name(it["name"])
            self._scripts.append(it)
            added += 1
        if added < len(items):      # 库已满/装不下：明确说清丢了几个，别静默吞掉
            self.app.toast(self.app._t("sc_import_partial",
                                       n=added, skipped=len(items) - added,
                                       max=_MAX_SCRIPTS), error=True)
        if added == 0:
            return
        self._active = len(self._scripts) - 1
        self._rebuild_combo()
        self._loading = True
        try:
            self.ed_code.setPlainText(self._scripts[self._active]["code"])
        finally:
            self._loading = False
        self._warned_code_len = False
        self._save_cfg()

    # ---------------- 宏录制 ----------------
    def _on_record(self):
        """开始/停止录制。停止时把录到的手动收发翻译成脚本，存为新脚本并切过去。"""
        rec = self.app._macro
        if rec.recording:                   # 正在录 → 停止并保存
            rec.stop()
            bind = getattr(self.app, "bind_macro_owner", None)
            if callable(bind):
                bind(False)
            self.app._mbm_tick()            # 录制期间若有人打开了 Modbus 主机，此刻按原开关恢复
            self._set_rec_ui(False)
            self._save_recording(rec)
            return
        if self.is_running():
            return                          # 脚本正在跑：录了也是脚本自己的发送，无意义
        if len(rec) > 0:
            # 上次停止时因脚本库满没保存成功、数据还留着 → 本次点击当作「重试保存」，
            # 而不是开新一轮把它清掉（否则提示用户「腾空位再点一次」就是骗人的）
            self._save_recording(rec)
            return
        if len(self._scripts) >= _MAX_SCRIPTS:
            # 开始前就检查：否则用户白录一场，停止时才被告知存不下
            self.app.toast(self.app._t("sc_max", n=_MAX_SCRIPTS), error=True)
            return
        if self.app._macro_start_blocked():
            self.app.toast_io_exclusive_busy(exclude=("macro",))
            return
        rec.start()
        bind = getattr(self.app, "bind_macro_owner", None)
        if callable(bind):
            bind(True)
        self._set_rec_ui(True)
        self.app.toast(self.app._t("sc_rec_started"))

    def _save_recording(self, rec):
        """把录到的事件生成脚本存进库。库满时**保留**录制数据，供腾出空位后重试。"""
        if len(rec) == 0:
            self.app.toast(self.app._t("sc_rec_empty"), error=True)
            return
        # 上限检查必须在 clear() **之前**：录制期间用户仍可新建脚本把库塞满，若先清空再报错，
        # 录到的东西就没了，腾出空位也没法重试。
        if len(self._scripts) >= _MAX_SCRIPTS:
            self.app.toast(self.app._t("sc_rec_full", n=_MAX_SCRIPTS), error=True)
            return
        code = rec.to_script(max_chars=_MAX_CODE_CHARS)
        tx, rx = rec.tx_count, rec.rx_count
        rec.clear()
        name = self._uniq_name(self.app._t("sc_rec_name"))
        self._scripts.append({"name": name, "code": code})
        self._active = len(self._scripts) - 1
        self._rebuild_combo()
        self._loading = True
        try:
            self.ed_code.setPlainText(code)
        finally:
            self._loading = False
        self._warned_code_len = False
        self._save_cfg()
        self.app.toast(self.app._t("sc_rec_done", tx=tx, rx=rx, name=name))

    def _status_key(self, running=None):
        """底部状态文案优先级：录制中 > 脚本运行中 > 普通提示。
        running 显式传入：_set_running_ui 在 w.start() 之前就调用，此刻 isRunning()
        还是 False，现查会错判成「空闲」。"""
        if self.app._macro.recording:
            return "sc_rec_running"
        r = self.is_running() if running is None else running
        return "sc_running" if r else "sc_hint"

    def _set_rec_ui(self, on):
        self.btn_rec.setText(self.app._t("sc_rec_stop" if on else "sc_rec"))
        self.btn_rec.setObjectName("PlotDangerBtn" if on else "PlotGhostBtn")
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.btn_run.setEnabled(not on)      # 录制期间不让跑脚本（会把脚本的发送录进去）
        self._set_status(self.app._t(self._status_key()))

    # ---------------- 运行 / 停止 ----------------
    def is_running(self):
        """True if the visible tab's script is running (each tab can run its own)."""
        running = getattr(self.app, "_script_running", None)
        if callable(running):
            return bool(running())
        worker = getattr(self.app, "_script_worker", None)
        if worker is None:
            return False
        fn = getattr(worker, "isRunning", None)
        return bool(fn()) if callable(fn) else True

    def _on_run(self):
        if self.is_running():
            return
        if self.app._script_start_blocked():
            self._reject_run(
                "io_exclusive_busy",
                self.app._io_busy_message(
                    "io_exclusive_busy", exclude=("script", "modbus")))
            return
        if not self.app._is_open():
            self._reject_run("net_not_open")
            return
        code = self.ed_code.toPlainText()
        if not code.strip():
            self._reject_run("sc_code_empty")
            return
        w = ScriptWorker(code)
        w.send_requested.connect(self.app._script_send)
        finder = getattr(self.app, "active_session", None)
        session = finder() if callable(finder) else None
        sid = getattr(session, "id", None) if session is not None else None
        if session is not None:
            session._script_log = []
        self.txt_out.clear()
        self._append_out(self.app._t("sc_started"), sid=sid)
        w.log_line.connect(lambda line, _sid=sid: self._append_out(line, sid=_sid))
        # 把 worker 绑进连接：run_finished 是队列信号，上一轮的完成信号可能在本轮已经开跑之后
        # 才送达，_on_finished 必须能认出发信人是不是当前这个 worker（否则会把新 worker 架空）。
        w.run_finished.connect(lambda ok, s, _w=w, _sid=sid: self._on_finished(_w, ok, s, sid=_sid))
        self._worker = w
        self._worker_sid = sid
        self.app._script_begin(w)       # 主窗接管：喂 RX + 暂停自动应答/Modbus
        self._set_running_ui(True)
        w.start()

    def _on_stop(self):
        worker = getattr(self.app, "_script_worker", None)
        if worker is None:
            worker = self._worker
            if worker is not None:
                # 当前标签没有在跑的脚本，但本对话框最近启动的 worker 仍在后台标签运行：
                # 提示而不是静默停掉其它标签的脚本。
                self.app.toast(self.app._t("sc_stop_other_session"), error=True)
        if worker is not None:
            stop = getattr(worker, "stop", None)
            if callable(stop):
                stop()

    def _on_finished(self, worker, ok, summary, sid=None):
        # 日志先从 worker 本身取计数 —— 关窗/换轮场景下 self._worker 可能已经不是它了，
        # 但 worker 对象仍持有正确的 checks_passed/checks_failed，先记日志再判断是否做状态清理。
        key = {"stopped": "sc_done_stopped", "syntax": "sc_done_error",
               "error": "sc_done_error", "checks": "sc_done_fail"}.get(
                   summary, "sc_done_ok" if ok else "sc_done_fail")
        self._append_out(self.app._t(key, ok=worker.checks_passed,
                                     fail=worker.checks_failed), sid=sid)
        end = getattr(self.app, "_script_end", None)
        if worker is self._worker:
            if callable(end):
                end(worker)
            self._worker = None
            self._worker_sid = None
        else:
            # 迟到的旧 worker：会话已钉上新一轮 → 不清理，避免误释放 I/O。
            # 后台标签仍钉着这个 worker 时必须 end，否则那一标签的收流永不释放。
            _log.debug("script finish from non-current worker %r (current=%r)",
                       worker, self._worker)
            pinned = any(
                getattr(session, "_script_worker", None) is worker
                for session in getattr(self.app, "_sessions", ()) or ())
            if pinned and callable(end):
                end(worker)
        self._set_running_ui(self.is_running())

    def _set_running_ui(self, running):
        self.btn_run.setVisible(not running)
        self.btn_stop.setVisible(running)
        for w in (self.cb_script, self.btn_new, self.btn_rename, self.btn_del,
                  self.btn_import, self.btn_export, self.btn_rec, self.ed_code):
            w.setEnabled(not running)      # 含 btn_rec：脚本跑着不能录（_on_record 也会 return，但禁用更直观）
        self._set_status(self.app._t(self._status_key(running)))

    def _set_status(self, text, error=False):
        """状态必须显示在当前对话框内；主窗口 toast 可能被本窗口遮住。"""
        self.lbl_status.setText(text)
        if error:
            self.lbl_status.setStyleSheet(
                "color: %s; font-weight: 600;" % chrome_for(self.app._theme_id())["danger"])
        else:
            self.lbl_status.setStyleSheet("")

    def _reject_run(self, key, msg=None):
        """用主题弹框说明启动失败，并在控制台内留下可追溯的错误文字。"""
        msg = self.app._t(key) if msg is None else msg
        self.app.toast(msg, error=True)
        self._append_out("✕ " + msg)
        self._set_status(msg, error=True)
        self.app._info_dlg(self.app._t("sc_title"), msg, is_error=True)

    def _visible_sid(self):
        finder = getattr(self.app, "active_session", None)
        session = finder() if callable(finder) else None
        return getattr(session, "id", None) if session is not None else None

    def _session_by_id(self, sid):
        if sid is None:
            return None
        finder = getattr(self.app, "find_session", None)
        if callable(finder):
            return finder(sid)
        return None

    def _clear_out(self):
        session = self._session_by_id(self._visible_sid())
        if session is not None:
            session._script_log = []
        self.txt_out.clear()

    def show_session_log(self):
        """Swap the output pane to the visible tab's buffer."""
        session = self._session_by_id(self._visible_sid())
        lines = list(getattr(session, "_script_log", None) or []) if session else []
        self.txt_out.setPlainText("\n".join(lines))
        sb = self.txt_out.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_out(self, line, sid=None):
        sid = sid if sid is not None else self._worker_sid or self._visible_sid()
        session = self._session_by_id(sid)
        if session is not None:
            lines = list(getattr(session, "_script_log", None) or [])
            lines.append(line)
            if len(lines) > _MAX_LOG_BLOCKS:
                lines = lines[-_MAX_LOG_BLOCKS:]
            session._script_log = lines
        if sid == self._visible_sid() or session is None:
            self.txt_out.appendPlainText(line)
            sb = self.txt_out.verticalScrollBar()
            sb.setValue(sb.maximum())

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("sc_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(760, 560)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("sc_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        btn_close = QPushButton(
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(f"""
            QDialog {{ background-color: {c['window_bg']}; }}
            QLabel {{ color: {c['text']}; background: transparent;
                      font-family: 'Segoe UI'; font-size: 12px; }}
            QScrollArea {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        dlg.exec_()

    def refresh_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QPushButton#PlotGhostBtn {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px;
        }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 600; padding: 5px 16px;
        }}
        QPushButton#PlotPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PlotPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#PlotDangerBtn {{
            background-color: {c['danger']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 600; padding: 5px 16px;
        }}
        QPushButton#PlotDangerBtn:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        /* 脚本库只有 1 条时弹出列表很矮、Qt 会把它叠在下拉框上方，此时下拉框的蓝色焦点边框
           正好把弹出列表整个框住，看着像给弹窗描了一圈蓝边（主界面因为列表落在下方、把焦点框
           挡住了才没这现象）。这里用同 ID 覆盖 focus/on 两态为中性边框——ID 选择器优先级高于
           _dialog_list_qss 里的 QComboBox:focus，且不影响其它对话框的共享样式。 */
        QComboBox#ScScript,
        QComboBox#ScScript:hover,
        QComboBox#ScScript:focus,
        QComboBox#ScScript:on {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']};
            selection-background-color: {c['input_bg']};
            selection-color: {c['text']};
        }}
        QPlainTextEdit#ScCode, QPlainTextEdit#ScOut {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            selection-background-color: {c['accent']}; selection-color: #FFFFFF;
        }}
        QSplitter#ScSplit::handle:vertical {{ height: 5px; background: transparent; }}
        QSplitter#ScSplit::handle:vertical:hover {{ background: {c['accent']}; }}
        """))
        # QComboBoxPrivateContainer 是独立顶层窗口，和主界面使用同一方式显式刷底色，
        # 避免 Windows 原生 palette 在打开/收起时短暂透出系统强调色。
        _style_combo_popups(self, c)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("sc_title"))
        self.lbl_script.setText(t("sc_script"))
        self.btn_new.setText(t("sc_new"))
        self.btn_rename.setText(t("sc_rename"))
        self.btn_del.setText(t("sc_delete"))
        self.btn_import.setText(t("sc_import"))
        self.btn_export.setText(t("sc_export"))
        self.btn_run.setText(t("sc_run"))
        self.btn_stop.setText(t("sc_stop"))
        self.btn_clear.setText(t("sc_clear_out"))
        set_tooltip(self.btn_help, t("sc_help_btn"))
        # 走 _set_rec_ui 而不是只改按钮文字：切语言/配置时录制态的按钮样式(红)、
        # 「运行」禁用态、状态栏文案都要一起同步，否则录制中切语言会退回成非录制外观。
        self._set_rec_ui(self.app._macro.recording)

    # ---------------- 生命周期 ----------------
    def showEvent(self, e):
        super().showEvent(e)
        # 焦点给代码区：打开控制台就是要写脚本；否则焦点默认落在第一个可聚焦控件（脚本下拉），
        # 那个蓝色焦点环（_dialog_list_qss 的 QComboBox:focus）一直亮着，看着像选中态。
        self.ed_code.setFocus()

    def closeEvent(self, e):
        workers = []
        for candidate in (self._worker, getattr(self.app, "_script_worker", None)):
            if candidate is not None and candidate not in workers:
                workers.append(candidate)
        for session in getattr(self.app, "_sessions", ()) or ():
            candidate = getattr(session, "_script_worker", None)
            if candidate is not None and candidate not in workers:
                workers.append(candidate)
        for target in workers:
            running = bool(getattr(target, "isRunning", lambda: False)())
            if running:
                stop = getattr(target, "stop", None)
                if callable(stop):
                    stop()
                wait = getattr(target, "wait", None)
                if callable(wait):
                    wait(1500)
                if bool(getattr(target, "isRunning", lambda: False)()):
                    # 不可中断的脚本（纯计算死循环）：等不到它退出。**必须**把对象转移到主窗常驻
                    # 列表续命——否则 self._worker 这个唯一引用随对话框销毁而消失，正在跑的
                    # QThread 被析构 → Qt std::terminate() 让整个进程 abort。
                    self.app._script_orphans.append(target)
            end = getattr(self.app, "_script_end", None)
            if callable(end):
                # Owner may be a background tab; _script_end scans sessions by
                # worker identity and re-enters with that owner.
                end(target)
        self._worker = None
        self._worker_sid = None
        self._save_cfg()
        super().closeEvent(e)
