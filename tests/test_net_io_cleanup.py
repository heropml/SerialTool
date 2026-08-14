# -*- coding: utf-8 -*-
"""net_io 清理路径回归：某一步失败不得跳过后续步骤，也不得让状态残留。

原实现把 abort/close/deleteLater 串在同一个 try 里并 `except Exception: pass`，
第一步抛异常会连带跳过后面几步，造成 socket 留在客户端表里或没退组就泄漏。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication  # noqa: E402
from PyQt5.QtNetwork import QAbstractSocket  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from net_io import (  # noqa: E402
    TcpServerConn, TcpClientConn, UdpGroupConn, _safe,
    ERR_SEND_BACKPRESSURE, _MAX_PENDING_BYTES,
)


class _FakeAddr:
    def toString(self):
        return "127.0.0.1"


class FakeSock:
    """假 socket：可指定某一步抛异常，并记录每步是否真的被调用。"""

    def __init__(self, raise_on=(), write_n=None, pending=0):
        self.raise_on = set(raise_on)
        self.write_n = write_n
        self.pending = pending
        self.calls = []

    def _step(self, name):
        self.calls.append(name)
        if name in self.raise_on:
            raise RuntimeError(name + " failed")

    def abort(self):
        self._step("abort")

    def close(self):
        self._step("close")

    def deleteLater(self):
        self._step("deleteLater")

    def leaveMulticastGroup(self, group):
        self._step("leaveMulticastGroup")

    def write(self, data):
        self.calls.append("write")
        return len(data) if self.write_n is None else self.write_n

    def bytesToWrite(self):
        return self.pending if hasattr(self, "pending") else 0

    def state(self):
        return QAbstractSocket.ConnectedState

    def peerAddress(self):
        return _FakeAddr()

    def peerPort(self):
        return 1234


def test_safe_reports_failure_without_raising():
    def boom():
        raise RuntimeError("x")

    assert _safe(boom) is False
    assert _safe(lambda: None) is True


def test_drop_client_removes_socket_even_if_abort_raises():
    conn = TcpServerConn("127.0.0.1", 0)
    sock = FakeSock(raise_on=("abort",))
    conn._clients = [sock]
    conn._drop_client(sock)
    assert conn._clients == []            # 摘表先于释放，不受 abort 失败影响
    assert "deleteLater" in sock.calls    # 后一步没被跳过


def test_server_close_releases_every_client_when_one_close_raises():
    bad, good = FakeSock(raise_on=("close",)), FakeSock()
    conn = TcpServerConn("127.0.0.1", 0)
    conn._clients = [bad, good]
    conn.close()
    assert conn._clients == []
    assert "deleteLater" in bad.calls     # 同一 socket 的后续步骤照常执行
    assert "deleteLater" in good.calls    # 后一个 socket 不被前一个连累


def test_tcp_server_close_deleteLaters_listener():
    conn = TcpServerConn("127.0.0.1", 0)
    srv = FakeSock()
    conn._server = srv
    conn.close()
    assert "close" in srv.calls and "deleteLater" in srv.calls
    assert conn._server is None


def test_send_drops_half_written_client_even_if_abort_raises():
    good = FakeSock()
    bad = FakeSock(raise_on=("abort",), write_n=1)   # 只写进 1 字节 = 半帧污染
    conn = TcpServerConn("127.0.0.1", 0)
    conn._clients = [good, bad]
    assert conn.send(b"hello") == 5                  # good 整帧写成功
    assert conn._clients == [good]                   # bad 必须摘除，否则后续写入错位


def test_tcp_client_close_deletes_socket_when_abort_raises():
    conn = TcpClientConn("127.0.0.1", 5000)
    sock = FakeSock(raise_on=("abort",))
    conn._sock = sock
    conn._connected = True
    conn.close()
    assert "deleteLater" in sock.calls
    assert conn._sock is None


def test_udp_group_close_still_closes_when_leave_group_raises():
    """退组失败以前会连带跳过 close/deleteLater，socket 泄漏且没退组。"""
    conn = UdpGroupConn("0.0.0.0", "239.1.1.1", 5000)
    sock = FakeSock(raise_on=("leaveMulticastGroup",))
    conn._sock = sock
    conn.close()
    assert sock.calls == ["leaveMulticastGroup", "close", "deleteLater"]
    assert conn._sock is None


def test_close_while_connecting_does_not_fake_a_disconnect():
    """还在 connecting 就关掉：从未发过 state_changed(True)，也不能发 False。

    主窗口把 False 读成「对端已断开」——会弹提示并触发自动重连，
    而这次连接根本没建立过。_on_conn_timeout 避的是同一个坑。
    """
    conn = TcpClientConn("127.0.0.1", 1)     # 不去真连，只看信号
    states = []
    conn.state_changed.connect(states.append)
    conn.close()
    assert states == []


def test_close_after_connected_still_reports_the_disconnect():
    conn = TcpClientConn("127.0.0.1", 1)
    states = []
    conn.state_changed.connect(states.append)
    conn._connected = True                          # 已连上过
    conn.close()
    assert states == [False]


def test_tcp_server_send_drops_when_client_buffer_full():
    slow = FakeSock(pending=_MAX_PENDING_BYTES)
    errors = []
    conn = TcpServerConn("127.0.0.1", 0)
    conn.error_occurred.connect(errors.append)
    conn._clients = [slow]
    assert conn.send(b"hello") == 0
    assert "write" not in slow.calls
    assert errors == [ERR_SEND_BACKPRESSURE]
    assert conn.send(b"hello") == 0
    assert errors == [ERR_SEND_BACKPRESSURE]   # edge-triggered


def test_tcp_server_send_keeps_fast_client_when_peer_is_slow():
    fast = FakeSock()
    slow = FakeSock(pending=_MAX_PENDING_BYTES)
    conn = TcpServerConn("127.0.0.1", 0)
    conn._clients = [fast, slow]
    assert conn.send(b"hello") == 5
    assert "write" in fast.calls
    assert "write" not in slow.calls
    assert conn.last_send_client_keys() == ["127.0.0.1:1234"]


def test_tcp_server_last_send_clients_reset_after_failed_send():
    fast = FakeSock()
    conn = TcpServerConn("127.0.0.1", 0)
    conn._clients = [fast]
    assert conn.send(b"hello") == 5
    assert conn.last_send_client_keys() == ["127.0.0.1:1234"]
    fast.pending = _MAX_PENDING_BYTES
    assert conn.send(b"again") == 0
    assert conn.last_send_client_keys() == []


def test_tcp_client_send_drops_when_buffer_full():
    sock = FakeSock(pending=_MAX_PENDING_BYTES)
    errors = []
    conn = TcpClientConn("127.0.0.1", 1)
    conn.error_occurred.connect(errors.append)
    conn._sock = sock
    conn._connected = True
    assert conn.send(b"hello") == 0
    assert "write" not in sock.calls
    assert errors == [ERR_SEND_BACKPRESSURE]
