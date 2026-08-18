# -*- coding: utf-8 -*-
"""Map raw connection/open error strings to actionable i18n tip keys.

Qt-free so unit tests do not need a QApplication. The tip key is optional:
callers keep showing the protocol-level title (open/listen/connect failed)
and replace or append the tip when classify() returns a key.
"""


def classify_conn_error(msg):
    """Return an i18n tip key for a known failure pattern, else None.

    Matching is keyword-based on the lowercased message so it covers pyserial
    SerialException wrappers, Qt socket errorString(), and OSError text on
    Windows/POSIX without depending on exception types crossing thread/signal
    boundaries (errors arrive as str via error_occurred).

    Disconnect patterns are checked before permission: USB yank often surfaces
    as ClearCommError wrapping PermissionError(13), which should read as a
    lost link rather than "port in use".
    """
    s = (msg or "").strip().lower()
    if not s:
        return None

    # Runtime disconnect / device yanked / broken pipe (before permission)
    if (
        "clearcommerror" in s
        or "device reported readiness" in s
        or "device disconnected" in s
        or "device was removed" in s
        or "the device does not recognize" in s
        or "handle is invalid" in s
        or "broken pipe" in s
        or "connection reset" in s
        or "connection aborted" in s
        or "network dropped" in s
        or "errno 32" in s
        or "[errno 32]" in s
        or "errno 104" in s
        or "[errno 104]" in s
    ):
        return "err_hint_disconnected"

    # Permission / exclusive open (serial port busy, Access is denied, errno 13)
    if (
        "permission" in s
        or "access is denied" in s
        or "access denied" in s
        or "errno 13" in s
        or "[errno 13]" in s
        or ("busy" in s and ("port" in s or "device" in s or "com" in s))
        or ("in use" in s and ("port" in s or "device" in s))
        or "could not exclusively lock" in s
        or "resource temporarily unavailable" in s
    ):
        return "err_hint_permission"

    # Missing serial device / no such port
    if (
        "filenotfound" in s
        or "no such file" in s
        or ("could not find" in s and "port" in s)
        or "port not found" in s
        or "cannot find the device" in s
        or "the system cannot find" in s
        or "errno 2" in s
        or "[errno 2]" in s
    ):
        return "err_hint_port_missing"

    # Bind / listen address already in use
    if (
        "address already in use" in s
        or "addressinuse" in s
        or "eaddrinuse" in s
        or "only one usage of each socket address" in s
        or "normally only one usage" in s
    ):
        return "err_hint_addr_in_use"

    # Connection refused
    if (
        "connection refused" in s
        or "actively refused" in s
        or "econnrefused" in s
        or "errno 111" in s
        or "[errno 111]" in s
        or "errno 61" in s
        or "[errno 61]" in s
    ):
        return "err_hint_refused"

    # Host unreachable / network down
    if (
        "network is unreachable" in s
        or "host is unreachable" in s
        or "no route to host" in s
        or "network unreachable" in s
        or "enetunreach" in s
        or "ehostunreach" in s
    ):
        return "err_hint_unreachable"

    # DNS / hostname
    if (
        "name or service not known" in s
        or "nodename nor servname" in s
        or "getaddrinfo failed" in s
        or "temporary failure in name resolution" in s
        or "no such host is known" in s
        or "host not found" in s
        or "unknown host" in s
    ):
        return "err_hint_host"

    return None


def format_conn_error_detail(msg, translate):
    """Build the `{e}` payload for toast: tip first, raw message kept under it.

    `translate(key)` should return the localized tip string (e.g. app._t).
    Unknown patterns keep the original message unchanged.
    """
    raw = (msg or "").strip() or str(msg)
    key = classify_conn_error(raw)
    if not key:
        return raw
    tip = translate(key)
    if not tip or tip == key:
        return raw
    if raw.lower() in tip.lower() or tip.lower() in raw.lower():
        return tip
    return "%s\n(%s)" % (tip, raw)
