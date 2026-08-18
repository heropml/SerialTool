# -*- coding: utf-8 -*-
"""Qt-free unit tests for trigger_safe (S-2)."""
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import trigger_safe as ts


def test_is_private_url_matrix():
    assert ts.is_private_url("http://127.0.0.1/webhook") is True
    assert ts.is_private_url("http://10.0.0.1/hook") is True
    assert ts.is_private_url("http://192.168.1.1/hook") is True
    assert ts.is_private_url("http://172.16.0.1/hook") is True
    assert ts.is_private_url("http://169.254.1.1/hook") is True
    assert ts.is_private_url("http://localhost/hook") is True
    assert ts.is_private_url("http://[::ffff:192.168.1.1]/hook") is True
    assert ts.is_private_url("http://[::ffff:127.0.0.1]/hook") is True
    assert ts.is_private_url("http://[::ffff:c0a8:101]/hook") is True
    assert ts.is_private_url("http://8.8.8.8:8080/hook") is False
    assert ts.is_private_url("http://example.com/webhook") is False
    assert ts.is_private_url("not-a-url") is False


def test_shell_value_win32():
    q = ts.shell_value("; rm -rf /", platform="win32")
    assert q.startswith('"') and q.endswith('"')
    assert '"' not in q[1:-1]
    assert "%" not in q and "!" not in q
    assert "\n" not in q and "\r" not in q
    assert "%" not in ts.shell_value("a%PATH%b", platform="win32")
    # cmd.exe treats these as literal text while they remain inside the one
    # surrounding quote pair; an embedded quote is replaced above.
    meta = ts.shell_value("a & b | c > d < e ^ (f)", platform="win32")
    assert meta == '"a & b | c > d < e ^ (f)"'


def test_shell_value_posix():
    payload = "; rm -rf / && id"
    quoted = ts.shell_value(payload, platform="linux")
    expected = "".join(ch for ch in payload if ch >= " ")
    assert shlex.split(quoted) == [expected]
    nl = ts.shell_value("a\nb", platform="linux")
    assert "\n" not in nl and "\r" not in nl


def test_shell_value_default_platform():
    assert isinstance(ts.shell_value("x"), str)
