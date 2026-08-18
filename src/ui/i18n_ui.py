# -*- coding: utf-8 -*-
"""UI retranslate helpers / tables. B5 thin extract from CommTool._apply_language."""
from __future__ import annotations

import logging

_log = logging.getLogger("commtool.i18n_ui")

# Open dialogs on CommTool that expose ``retranslate()``.
RETRANSLATE_DIALOG_ATTRS = (
    "_multi_send_dlg",
    "_keyword_dlg",
    "_plot_dlg",
    "_dash_dlg",
    "_script_dlg",
    "_rr_dlg",
    "_rd_dlg",
    "_snip_dlg",
    "_send_hist_dlg",
    "_cpreset_dlg",
    "_ble_scan_dlg",
    "_triggers_dlg",
    "_frame_dlg",
    "_ar_dlg",
    "_mbm_dlg",
    "_device_center_dlg",
    "_structured_dlg",
    "_seq_dlg",
    "_frame_builder_dlg",
    "_toolbox_dlg",
    "_xfer_dlg",
    "_bridge_dlg",
)


def apply_tr_properties(widgets, t_fn, set_tooltip_fn, label_col_width=None,
                        log=None):
    """Apply ``tr_text`` / ``tr_placeholder`` / ``tr_tooltip`` / ``tr_fixedw``.

    ``t_fn(key)`` localizes; ``set_tooltip_fn(widget, text)`` sets tips;
    ``label_col_width`` when set is called for widgets with ``tr_fixedw``.
    """
    log = log or _log
    for w in widgets:
        k = w.property("tr_text")
        if k:
            try:
                w.setText(t_fn(k))
            except Exception:
                log.debug("apply_tr_properties tr_text failed", exc_info=True)
        k = w.property("tr_placeholder")
        if k:
            try:
                w.setPlaceholderText(t_fn(k))
            except Exception:
                log.debug("apply_tr_properties tr_placeholder failed",
                          exc_info=True)
        k = w.property("tr_tooltip")
        if k:
            try:
                set_tooltip_fn(w, t_fn(k))
            except Exception:
                log.debug("apply_tr_properties tr_tooltip failed",
                          exc_info=True)
        if label_col_width is not None and w.property("tr_fixedw"):
            w.setFixedWidth(label_col_width())


def refill_combo_keys(combo, keys, t_fn, *, current_index=None):
    """Clear and refill a combo from i18n key list; restore index when possible."""
    if current_index is None:
        current_index = combo.currentIndex()
    combo.blockSignals(True)
    combo.clear()
    for key in keys:
        combo.addItem(t_fn(key))
    if 0 <= current_index < combo.count():
        combo.setCurrentIndex(current_index)
    combo.blockSignals(False)


def refill_combo_data_items(combo, items, t_fn, *, current_data=None):
    """Clear and refill ``(data, key)`` items; restore by ``current_data``."""
    if current_data is None:
        current_data = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for data, key in items:
        combo.addItem(t_fn(key), data)
    idx = combo.findData(current_data)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def retranslate_dialogs(host, attrs=RETRANSLATE_DIALOG_ATTRS):
    """Call ``retranslate()`` on each non-None dialog attribute of ``host``."""
    for attr in attrs:
        dlg = getattr(host, attr, None)
        if dlg is not None:
            dlg.retranslate()
