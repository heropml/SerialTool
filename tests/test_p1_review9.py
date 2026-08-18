# -*- coding: utf-8 -*-
"""Wrap-up regression: tooltip HTML helper, Modbus advanced UI, plot jump."""
import math
import os
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main_window import CommTool, PortScannerThread
from ui.auto_reply_dialog import AutoReplyDialog
from ui.plot_dialog import PlotDialog
from ui.ui_tips import tip_html
from ui import i18n
_APP = QApplication.instance() or QApplication([])


def _patch_window_runtime(monkeypatch, settings_path):
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(settings_path)))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)


def test_tip_html_wraps_plain_text_and_preserves_newlines():
    html = tip_html("hello\nworld <x>")
    assert html.lower().startswith("<html>")
    assert "<br>" in html
    assert "&lt;x&gt;" in html
    assert tip_html("<html><body>x</body></html>") == "<html><body>x</body></html>"
    assert tip_html("") == ""
    assert tip_html(None) == ""


def test_long_tips_become_rich_text_for_qt_wrap():
    keys = ("seq_extract_tip", "mbm_echo_tip", "ar_gap_tip", "vconn_tip",
            "ar_modbus_tip", "ctrl_reset_tip")
    for lang in ("zh", "en", "zh_tw"):
        for key in keys:
            html = tip_html(i18n.TR[lang][key])
            assert html.lower().startswith("<html>"), (lang, key)


def test_modbus_dialog_advanced_widgets_roundtrip(tmp_path, monkeypatch):
    """Advanced exception/dynamics/server_id widgets load from cfg and commit back."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("ar-adv-ui-test")
    try:
        window._set_ar_modbus({
            "on": True, "addr": 1,
            "server_id": "RIG-9",
            "dynamics": [{"space": "holding", "addr": 5, "mode": "sine",
                          "step": 1, "min": 10, "max": 20, "period_ms": 500}],
            "exception": {"enabled": True, "code": 3, "mode": "n", "n": 4,
                          "funcs": [3, 16], "addrs": [5, 6]},
        })
        monkeypatch.setattr(QDialog, "exec_", lambda self: QDialog.Accepted)
        dlg = AutoReplyDialog(window)
        try:
            dlg._open_modbus()
            cfg = window._ar_modbus
            assert cfg.get("server_id") == "RIG-9"
            exc = cfg.get("exception") or {}
            assert exc.get("mode") == "n" and exc.get("n") == 4
            assert list(exc.get("funcs") or []) == [3, 16]
            assert list(exc.get("addrs") or []) == [5, 6]
            dyn = cfg.get("dynamics") or []
            assert len(dyn) == 1 and dyn[0]["mode"] == "sine" and dyn[0]["addr"] == 5
            assert dyn[0]["period_ms"] == 500
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_plot_named_samples_keep_wall_and_jump(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-jump-test")
    jumped = []
    window.jump_to_session_time = lambda wall_t: jumped.append(wall_t)
    try:
        dlg = PlotDialog(window)
        try:
            t0 = time.time()
            dlg.feed_named_samples([
                {"tag": "A", "value": 1.5, "timestamp": t0},
                {"tag": "B", "value": 2.5, "timestamp": t0},
            ])
            assert dlg._channels
            for ch in dlg._channels:
                assert list(ch.get("walls") or []) == [t0]

            class _Ev(object):
                def double(self):
                    return True

                def scenePos(self):
                    return None

            class _VB(object):
                def mapSceneToView(self, _pos):
                    return type("MP", (), {"x": lambda self: 0.0})()

            dlg.plot.plotItem.vb = _VB()
            dlg._on_plot_clicked(_Ev())
            assert jumped and abs(jumped[0] - t0) < 1e-6
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_plot_cursor_stats_refresh_after_rolling_overflow(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-stats-roll")
    try:
        dlg = PlotDialog(window)
        try:
            dlg._max_points = 2
            dlg._append_vals([1.0])
            dlg._append_vals([2.0])
            dlg._refresh_cursor_stats_cache()
            assert "min=1" in dlg._cursor_stats_extra
            dlg._append_vals([100.0])
            dlg._refresh_cursor_stats_cache()
            assert "min=2" in dlg._cursor_stats_extra
            assert "max=100" in dlg._cursor_stats_extra
            assert "mean=51" in dlg._cursor_stats_extra
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_histogram_extreme_range_has_finite_pyqtgraph_geometry(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-hist-extreme")
    try:
        dlg = PlotDialog(window)
        try:
            dlg._append_vals([-1e308])
            dlg._append_vals([1e308])
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", RuntimeWarning)
                dlg.cb_view.setCurrentIndex(2)
                _APP.processEvents()
                assert dlg._hist_item is not None
                assert math.isfinite(dlg._hist_item.opts["width"])
                assert all(math.isfinite(float(value))
                           for value in dlg._hist_item.opts["x"])
                dlg._hist_item.boundingRect()

            assert not any(issubclass(warning.category, RuntimeWarning)
                           for warning in caught)
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_io_graph_restores_plot_view_and_dual_y(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-io-restore")
    try:
        dlg = PlotDialog(window)
        try:
            dlg.cb_view.setCurrentIndex(2)
            assert dlg.apply_io_graph_preset()
            dlg.leave_io_graph_preset()
            assert dlg.cb_view.currentIndex() == 2

            dlg.cb_view.setCurrentIndex(0)
            dlg.cb_dual_y.setChecked(True)
            assert dlg.apply_io_graph_preset()
            dlg.leave_io_graph_preset()
            assert dlg.cb_dual_y.isChecked()
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_fc08_sub_data_qty_normalizes():
    from modbus.modbus_master import normalize_poll

    rec = normalize_poll({
        "enabled": True, "name": "d", "unit": 1, "func": 8,
        "addr": 0, "qty": "1", "wval": "7", "diag_sub": "12", "period": 1000,
    })
    assert rec["func"] == 8
    assert rec["diag_sub"] == 12
    assert rec["wval"] == 7


def test_fc08_bare_qty_is_data_with_sub_zero():
    """Bare qty must mean loopback DATA under sub=0 — never sub-function alone.

    Switching FC03 qty=1 to FC08 used to emit diag_sub=1 (Restart Communications).
    """
    from modbus.modbus_master import normalize_poll

    rec = normalize_poll({
        "enabled": True, "name": "d", "unit": 1, "func": 8,
        "addr": 0, "qty": "1", "wval": "1", "diag_sub": "0", "period": 1000,
    })
    assert rec["diag_sub"] == 0
    assert rec["wval"] == 1

    # Leftover "12:7" as wval (old collect bug) must not become a live rule.
    bad = normalize_poll({
        "enabled": True, "name": "d", "unit": 1, "func": 8,
        "addr": 0, "qty": "1", "wval": "12:7", "diag_sub": 12, "period": 1000,
    })
    assert bad["wval"] is None or bad.get("diag_data") is None


def test_fc08_collect_bare_qty_after_func_switch(tmp_path, monkeypatch):
    """Dialog: FC03 qty=1 then switch to 08 must collect sub=0,data=1 — not sub=1."""
    from PyQt5.QtWidgets import QComboBox
    from ui.modbus_master_dialog import ModbusMasterDialog
    from modbus import modbus_master as mm
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("fc08-switch-test")
    window._mbm_rules = [mm.normalize_poll({
        "enabled": True, "name": "r", "unit": 1, "func": 3,
        "addr": 0, "qty": 1, "period": 1000,
    })]
    try:
        dlg = ModbusMasterDialog(window)
        try:
            rec = dlg._rows[0]
            # Switch function to 08 — qty rewriter should produce "0:1".
            idx = next(i for i in range(rec["func"].count())
                       if rec["func"].itemData(i) == 0x08)
            rec["func"].setCurrentIndex(idx)
            assert ":" in rec["qty"].text(), rec["qty"].text()
            collected = dlg._collect()[0]
            assert int(collected.get("diag_sub") or 0) == 0
            assert str(collected.get("wval")) in ("1", "1.0")
            norm = mm.normalize_poll(collected)
            assert norm["diag_sub"] == 0 and norm["wval"] == 1
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_plot_jump_skips_rate_channels(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-rate-skip")
    jumped = []
    window.jump_to_session_time = lambda wall_t: jumped.append(wall_t)
    try:
        dlg = PlotDialog(window)
        try:
            dlg.feed_named_samples([
                {"tag": "rx_Bps", "value": 100.0},  # same X, no sample ts
            ])
            dlg.feed_named_samples([
                {"tag": "sensor", "value": 1.0, "timestamp": 12345.0},
            ])
            # Force both channels to share x=0 for a worst-case collision.
            for ch in dlg._channels:
                ch["xs"].clear(); ch["xs"].append(0)
                if ch["name"] == "rx_Bps":
                    ch["ys"].clear(); ch["ys"].append(100.0)
                    ch["walls"].clear(); ch["walls"].append(999.0)
                else:
                    ch["ys"].clear(); ch["ys"].append(1.0)
                    ch["walls"].clear(); ch["walls"].append(12345.0)

            class _Ev(object):
                def double(self):
                    return True
                def scenePos(self):
                    return None
            class _VB(object):
                def mapSceneToView(self, _pos):
                    return type("MP", (), {
                        "x": lambda self: 0.0,
                        "y": lambda self: 1.0,  # nearer the sensor
                    })()
            dlg.plot.plotItem.vb = _VB()
            dlg._on_plot_clicked(_Ev())
            assert jumped == [12345.0], jumped
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_plot_click_backfills_missing_walls(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-walls-backfill")
    jumped = []
    window.jump_to_session_time = lambda wall_t: jumped.append(wall_t)
    try:
        dlg = PlotDialog(window)
        try:
            dlg.feed_named_samples([{"tag": "A", "value": 1.0, "timestamp": 100.0}])
            # Simulate a pre-walls channel left over from an older session object.
            ch = dlg._channels[0]
            del ch["walls"]
            class _Ev(object):
                def double(self):
                    return True
                def scenePos(self):
                    return None
            class _VB(object):
                def mapSceneToView(self, _pos):
                    return type("MP", (), {"x": lambda self: 0.0})()
            dlg.plot.plotItem.vb = _VB()
            dlg._on_plot_clicked(_Ev())
            assert "walls" in ch and len(ch["walls"]) == len(ch["xs"])
            assert jumped  # still jumps (wall may be 0 after pad)
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_fc08_to_read_func_clamps_zero_qty(tmp_path, monkeypatch):
    """Leaving FC08 with data=0 for FC03 must yield qty=1, not qty=0."""
    from ui.modbus_master_dialog import ModbusMasterDialog
    from modbus import modbus_master as mm
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("fc08-to-read")
    window._mbm_rules = [mm.normalize_poll({
        "enabled": True, "name": "r", "unit": 1, "func": 8,
        "addr": 0, "qty": 1, "wval": 0, "diag_sub": 0, "period": 1000,
    })]
    try:
        dlg = ModbusMasterDialog(window)
        try:
            rec = dlg._rows[0]
            assert ":" in rec["qty"].text()
            idx = next(i for i in range(rec["func"].count())
                       if rec["func"].itemData(i) == 0x03)
            rec["func"].setCurrentIndex(idx)
            assert rec["qty"].text().strip() == "1", rec["qty"].text()
            collected = dlg._collect()[0]
            norm = mm.normalize_poll(collected)
            assert norm["func"] == 3
            assert norm["qty"] >= 1
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_dynamics_max_zero_survives_dialog_commit(tmp_path, monkeypatch):
    """max=0 is legal; `or 0xFFFF` used to turn it into 65535."""
    from PyQt5.QtWidgets import QDialog

    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("dyn-max0")
    try:
        window._set_ar_modbus({
            "on": True, "addr": 1,
            "dynamics": [{"space": "holding", "addr": 0, "mode": "static",
                          "step": 1, "min": 0, "max": 0, "period_ms": 1000}],
            "exception": {"enabled": False, "code": 4, "mode": "always",
                          "n": 1, "funcs": [], "addrs": []},
        })
        monkeypatch.setattr(QDialog, "exec_", lambda self: QDialog.Accepted)
        dlg = AutoReplyDialog(window)
        try:
            dlg._open_modbus()
            dyn = window._ar_modbus.get("dynamics") or []
            assert len(dyn) == 1
            assert dyn[0]["min"] == 0 and dyn[0]["max"] == 0, dyn[0]
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_tray_tooltip_stays_plain_text(tmp_path, monkeypatch):
    """Tray tip must stay plain on all three production setToolTip sites.

    Covers: CommTool.__init__ -> _setup_tray, _set_language -> _apply_language,
    and _switch_profile. The test never calls setToolTip itself; the stub only
    records what production code writes.
    """
    from PyQt5.QtWidgets import QApplication
    from ui.ui_tips import tip_html
    import main_window as mw

    tips = []
    setup_calls = []

    class _Activated(object):
        def connect(self, *a, **k):
            pass

    class _Tray(object):
        """Stand-in so production _setup_tray can run under offscreen CI."""
        Trigger = 1
        DoubleClick = 2

        @staticmethod
        def isSystemTrayAvailable():
            return True

        def __init__(self, *a, **k):
            self._tip = None
            self.activated = _Activated()

        def setToolTip(self, text):
            # Sink only -- production CommTool paths call this.
            tips.append(text)
            assert not str(text or "").lower().startswith("<html"), text
            self._tip = text

        def toolTip(self):
            return self._tip

        def setContextMenu(self, menu):
            self._menu = menu

        def show(self):
            pass

    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(
            tmp_path / ("settings.ini" if not profile else "settings-%s.ini" % profile))))
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)
    monkeypatch.setattr(mw, "QSystemTrayIcon", _Tray)
    monkeypatch.setattr(CommTool, "toast", lambda self, msg, error=False: None)

    orig_setup = CommTool._setup_tray

    def _setup_wrap(self):
        setup_calls.append(1)
        return orig_setup(self)

    monkeypatch.setattr(CommTool, "_setup_tray", _setup_wrap)

    window = CommTool("")
    app = QApplication.instance()
    had_lock = hasattr(app, "_profile_lock")
    o_app_lock = getattr(app, "_profile_lock", None)
    try:
        assert setup_calls, "_setup_tray must run during CommTool.__init__"
        tray = window._tray
        assert isinstance(tray, _Tray)
        plain0 = window._t("app_title") + window._title_suffix
        assert tray.toolTip() == plain0
        assert tips[-1] == plain0
        assert tip_html(plain0).lower().startswith("<html")  # contrast

        # Explicit re-entry of _setup_tray (new tray instance, plain tip again).
        n_setup = len(setup_calls)
        n_tips = len(tips)
        window._setup_tray()
        assert len(setup_calls) == n_setup + 1
        assert len(tips) == n_tips + 1
        tray = window._tray
        assert tray.toolTip() == plain0

        # Language path: _set_language -> _apply_language -> setToolTip
        n_tips = len(tips)
        other = "en" if window._lang != "en" else "zh"
        window._set_language(other)
        assert len(tips) > n_tips
        plain_lang = window._t("app_title") + window._title_suffix
        assert tray.toolTip() == plain_lang
        assert plain_lang != plain0

        # Profile path: _switch_profile updates suffix via setToolTip
        n_tips = len(tips)
        monkeypatch.setattr(window, "_confirm_project_switch", lambda: True)
        window._switch_profile("2")
        assert window._profile == "2"
        assert window._title_suffix == " (2)"
        assert len(tips) > n_tips
        plain_prof = window._t("app_title") + window._title_suffix
        assert tray.toolTip() == plain_prof
        assert plain_prof.endswith(" (2)")
        assert not any(str(x).lower().startswith("<html") for x in tips)
    finally:
        cur = getattr(app, "_profile_lock", None)
        if cur is not None and cur is not o_app_lock:
            try:
                cur.unlock()
            except Exception:
                pass
        if had_lock:
            app._profile_lock = o_app_lock
        elif hasattr(app, "_profile_lock"):
            try:
                delattr(app, "_profile_lock")
            except Exception:
                pass
        window.deleteLater()
        _APP.processEvents()

def test_fc08_func_switch_refreshes_qty_tooltip(tmp_path, monkeypatch):
    """Switching to/from FC08 must refresh the qty cell tooltip."""
    from ui.modbus_master_dialog import ModbusMasterDialog
    from modbus import modbus_master as mm
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("fc08-tip")
    window._mbm_rules = [mm.normalize_poll({
        "enabled": True, "name": "r", "unit": 1, "func": 3,
        "addr": 0, "qty": 2, "period": 1000,
    })]
    try:
        dlg = ModbusMasterDialog(window)
        try:
            rec = dlg._rows[0]
            diag = window._t("mbm_diag_sub_tip")
            tip0 = rec["qty"].toolTip() or ""
            assert tip0.lower().startswith("<html")
            assert diag not in tip0
            idx08 = next(i for i in range(rec["func"].count())
                         if rec["func"].itemData(i) == 0x08)
            rec["func"].setCurrentIndex(idx08)
            tip08 = rec["qty"].toolTip() or ""
            assert diag in tip08
            idx03 = next(i for i in range(rec["func"].count())
                         if rec["func"].itemData(i) == 0x03)
            rec["func"].setCurrentIndex(idx03)
            tip03 = rec["qty"].toolTip() or ""
            assert diag not in tip03
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_ar_modbus_help_no_longer_claims_missing_ui():
    for lang in ("zh", "en", "zh_tw"):
        help_text = i18n.TR[lang]["ar_modbus_help"]
        assert "目前没有界面" not in help_text
        assert "no UI yet" not in help_text
        assert "目前沒有介面" not in help_text


def test_auto_reply_close_event_syncs_settings(tmp_path, monkeypatch):
    """Merged closeEvent must flush pending commit and settings.sync()."""
    import inspect
    from PyQt5.QtGui import QCloseEvent

    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("ar-close")
    synced = []
    monkeypatch.setattr(window.settings, "sync", lambda: synced.append(1))
    dlg = AutoReplyDialog(window)
    try:
        committed = []
        monkeypatch.setattr(dlg, "_commit", lambda: committed.append(1))
        dlg._save_timer.start(60_000)
        assert dlg._save_timer.isActive()
        dlg.closeEvent(QCloseEvent())
        assert committed == [1]
        assert synced == [1]
        src = inspect.getsource(AutoReplyDialog.closeEvent)
        assert "settings.sync" in src
        assert "_commit" in src
        ar_src = (Path(__file__).resolve().parents[1] /
                  "src" / "ui" / "auto_reply_dialog.py").read_text(encoding="utf-8")
        assert ar_src.count("def closeEvent") == 1
    finally:
        dlg.deleteLater()
        window.deleteLater()
        _APP.processEvents()
