# -*- coding: utf-8 -*-
"""Trigger action safety helpers (Qt-free).

S-2 slice: webhook SSRF host checks and run_cmd placeholder shell quoting.
"""
import ipaddress
import shlex
import socket
import sys
from urllib.parse import urlparse, urlunsplit


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


def _normalized_address(value):
    """Parse an IP address and unwrap IPv4-mapped IPv6 forms."""
    addr = ipaddress.ip_address(value)
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped if mapped is not None else addr


def is_public_address(value):
    """True only for globally routable unicast addresses.

    Using an allow-list (``is_global``) also rejects loopback, private,
    link-local, multicast, reserved and unspecified ranges.
    """
    try:
        addr = _normalized_address(value)
        return bool(addr.is_global and not addr.is_multicast)
    except (ValueError, TypeError):
        return False


def resolve_host_addresses(host, port, resolver=None):
    """Resolve every address for host. An empty result is a hard failure."""
    lookup = resolver or socket.getaddrinfo
    values = set()
    try:
        rows = lookup(host, port, type=socket.SOCK_STREAM)
        for row in rows or ():
            sockaddr = row[4]
            if sockaddr:
                values.add(str(sockaddr[0]))
    except (OSError, TypeError, ValueError, IndexError):
        return set()
    return values


def resolve_webhook_target(url, allow_insecure=False, resolver=None):
    """Resolve and validate a webhook target, returning pinned addresses.

    Safe-by-default rules require HTTPS and require *all* resolved addresses
    to be public. ``allow_insecure`` is an explicit per-rule escape hatch for
    trusted LAN/HTTP integrations; it still requires a valid, resolvable URL.
    """
    try:
        raw = str(url or "").strip()
        if any(ord(char) < 32 for char in raw):
            return None
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https") or not parsed.hostname:
            return None
        if (parsed.username is not None or parsed.password is not None
                or (scheme != "https" and not allow_insecure)):
            return None
        explicit_port = parsed.port
        if explicit_port is not None and explicit_port < 1:
            return None
        port = explicit_port if explicit_port is not None else (
            443 if scheme == "https" else 80)
    except (TypeError, ValueError):
        return None
    addresses = resolve_host_addresses(parsed.hostname, port, resolver=resolver)
    if not addresses:
        return None
    if not allow_insecure and not all(is_public_address(addr) for addr in addresses):
        return None
    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    return {
        "scheme": scheme,
        "host": parsed.hostname,
        "port": port,
        "path": path,
        "addresses": tuple(sorted(addresses)),
    }


def webhook_url_allowed(url, allow_insecure=False, resolver=None):
    """True when a webhook target resolves within the configured boundary."""
    return resolve_webhook_target(
        url, allow_insecure=allow_insecure, resolver=resolver) is not None


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
