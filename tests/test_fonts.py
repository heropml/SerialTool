# -*- coding: utf-8 -*-
import sys

import fonts


def test_localize_qss_replaces_windows_symbol_font_before_ui_alias():
    qss = "font-family: 'Segoe UI Symbol', 'Segoe UI';"
    localized = fonts.localize_qss(qss)

    if sys.platform == "win32":
        assert localized == qss
    else:
        assert "'Segoe UI Symbol'" not in localized
        assert "'%s'" % fonts.SYMBOL_FAMILY in localized
        assert "'%s'" % fonts.UI_FAMILY in localized
