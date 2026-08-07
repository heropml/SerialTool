# -*- coding: utf-8 -*-
"""Trigger action safety helpers (Qt-free).

S-2 slice: webhook SSRF host checks and run_cmd placeholder shell quoting.
"""
import ipaddress
import shlex
import sys
from urllib.parse import urlparse


def is_private_url(url):
    """True if URL host is private/loopback/link-local/unspecified.

    Hostnames are left alone (no DNS lookup). IPv4-mapped IPv6 forms
    like ::ffff:192.168.1.1 / ::ffff:c0a8:101 are unwrapped first.
    """
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        if host.lower() == "localhost":
            return True
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        mapped = getattr(addr, "ipv4_mapped", None)
        if mapped is not None:
            addr = mapped
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_unspecified
        )
    except Exception:
        return False


def shell_value(value, platform=None):
    """Quote a placeholder value so it stays shell-inert text.

    run_cmd uses shell=True; name/pattern from rules must not inject a second
    command. Control chars and newlines are stripped first.
    """
    text = "".join(ch for ch in str(value) if ch >= " ")
    plat = sys.platform if platform is None else platform
    if plat == "win32":
        # cmd.exe still expands %VAR% / !VAR! inside quotes; strip those.
        return '"%s"' % text.replace('"', "'").replace("%", "").replace("!", "")
    return shlex.quote(text)
