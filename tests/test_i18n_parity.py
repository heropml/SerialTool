# -*- coding: utf-8 -*-
"""三语翻译表键集合对拍：任一语言缺键即失败。"""
from __future__ import print_function

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import TR

_REQUIRED_LANGS = ("zh", "en", "zh_tw")


def test_tr_has_required_langs():
    for lang in _REQUIRED_LANGS:
        assert lang in TR, "missing language table: %s" % lang
        assert isinstance(TR[lang], dict) and TR[lang], lang


def test_tr_key_sets_match_across_langs():
    base = "zh"
    base_keys = set(TR[base])
    assert len(base_keys) > 100, "unexpectedly small zh table"
    for lang in _REQUIRED_LANGS:
        if lang == base:
            continue
        keys = set(TR[lang])
        missing = sorted(base_keys - keys)
        extra = sorted(keys - base_keys)
        assert not missing, "%s missing %d keys, e.g. %s" % (
            lang, len(missing), missing[:12])
        assert not extra, "%s has %d extra keys, e.g. %s" % (
            lang, len(extra), extra[:12])


def test_tr_values_are_nonempty_strings():
    for lang in _REQUIRED_LANGS:
        for key, val in TR[lang].items():
            assert isinstance(val, str), "%s.%s not str" % (lang, key)
            assert val.strip(), "%s.%s empty" % (lang, key)


# Help / placeholder strings that document DSL or JSON, not str.format fields.
_LITERAL_BRACE_KEYS = (
    "ar_reply_ph",
    "ar_modbus_slaves_extra_ph",
    "ar_help",
    "ar_modbus_help",
)
_TEMPLATE_SAMPLES = {
    "mbm_st_mask": {"addr": 1, "aand": 2, "oor": 3},
    "plot_cursor_fmt": {"x": 1.25, "y": 2.5, "stats": ""},
}


def test_literal_brace_keys_format_without_kwargs():
    for lang in _REQUIRED_LANGS:
        for key in _LITERAL_BRACE_KEYS:
            val = TR[lang][key]
            val.format()
            val.format(unexpected=1)
            rendered = val.format()
            assert "{" in rendered, "%s.%s lost braces after format" % (lang, key)


def test_template_keys_format_with_samples():
    for lang in _REQUIRED_LANGS:
        for key, kwargs in _TEMPLATE_SAMPLES.items():
            TR[lang][key].format(**kwargs)
