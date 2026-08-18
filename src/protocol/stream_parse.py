# -*- coding: utf-8 -*-
"""从 RX 字节流解析出「命名数值通道」的纯解析器（不依赖 Qt / pyqtgraph）。

与波形图(plot_dialog) 语义一致的三种模式，抽成可复用、可单测的独立模块，供数值仪表盘使用：
- 分隔符：每行按 逗号/空白/Tab/分号/自动 拆，每列一个通道 CH1/CH2…（ASCII 数字流，如 "1.2,3.4"）
- 正则：每行用正则，每个捕获组一个通道 CH1/CH2…（如 temp=(\\d+).*hum=(\\d+)）
- HEX 字节：按 binproto「帧头 + 偏移:类型」从字节里取数值，每字段一个通道（字段名即通道名）

feed(data) 返回本次 chunk 解出的 [(name, value), ...]（按出现顺序；调用方对每个通道名取最后一个
即最新值）。文本模式跨包缓冲不成行的残段。
"""
import codecs
import re

from protocol import binproto

_SEP_RX = [r",", r"\s+", r"\t", r";", r"[,\s;]+"]
MODE_DELIM, MODE_REGEX, MODE_HEX = 0, 1, 2


class NumericStreamParser:
    """有状态的数值流解析器（文本模式跨包缓冲行）。配置项直接读写属性 mode/sep_index，
    正则/字段/帧头经 set_* 校验后落地。"""

    def __init__(self):
        self.mode = MODE_DELIM
        self.sep_index = 0
        self._regex = None
        self.hex_fields = []          # [(name, off, typ)]
        self.hex_header = b""
        self.hex_header_valid = True
        self._buf = ""                # 文本模式跨包残段
        self._decoder = None           # 文本模式增量解码器（多字节字符可跨 chunk）
        self._decoder_codec = None

    # ---------------- 配置 ----------------
    def set_regex(self, pattern):
        """设正则；空=不匹配任何。非法正则返回 False（并置空），调用方据此提示。"""
        pattern = (pattern or "").strip()
        if not pattern:
            self._regex = None
            return True
        try:
            self._regex = re.compile(pattern)
            return True
        except re.error:
            self._regex = None
            return False

    def set_fields(self, spec):
        """设 HEX 字段定义（binproto 语法）。非法返回 False（并置空）。"""
        try:
            self.hex_fields = binproto.parse_field_spec(spec or "")
            return True
        except (ValueError, TypeError):
            self.hex_fields = []
            return False

    def set_header(self, spec):
        """设 HEX 帧头过滤（hex，可空=每包一帧不过滤）。非法返回 False 并停止 HEX 解析
        （不退化成「空帧头=匹配全部」，避免把垃圾当帧）。"""
        try:
            self.hex_header = binproto.parse_hex_header(spec or "")
            self.hex_header_valid = True
            return True
        except ValueError:
            self.hex_header_valid = False
            return False

    def reset(self):
        """清跨包缓冲（清屏/切模式/重连时调用）。"""
        self._buf = ""
        self._decoder = None
        self._decoder_codec = None

    # ---------------- 解析 ----------------
    def feed(self, data, codec="utf-8"):
        """喂一个 chunk，返回 [(name, value:float), ...]。"""
        out = []
        if self.mode == MODE_HEX:
            if not self.hex_header_valid or not self.hex_fields:
                return out
            for frame in binproto.iter_frames(bytes(data), self.hex_header):
                for name, off, typ in self.hex_fields:
                    v = binproto.read_field(frame, off, typ)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.append((name, float(v)))
            return out
        # 文本模式：解码 + 缓冲 + 拆完整行
        codec = codec or "utf-8"
        try:
            # 每个底层收包不保证落在字符边界；用增量解码器保留末尾半个 UTF-8/GBK
            # 字符，避免下一包到来前被 errors="replace" 提前替换掉。
            if self._decoder is None or self._decoder_codec != codec:
                if self._decoder_codec is not None and self._decoder_codec != codec:
                    self._buf = ""          # 编码切换是文本流边界，不能拼接旧编码残段
                self._decoder = codecs.getincrementaldecoder(codec)(errors="replace")
                self._decoder_codec = codec
            text = self._decoder.decode(bytes(data), final=False)
        except (LookupError, TypeError, UnicodeError):
            self._decoder = None
            self._decoder_codec = None
            return out
        self._buf += text
        if len(self._buf) > 65536:        # 长期收不到换行：防缓冲无限膨胀
            self._buf = self._buf[-4096:]
        norm = self._buf.replace("\r\n", "\n").replace("\r", "\n")
        parts = norm.split("\n")
        self._buf = parts.pop()           # 最后一段可能未完成，留到下次
        for line in parts:
            line = line.strip()
            if line:
                out.extend(self._parse_line(line))
        return out

    def _parse_line(self, line):
        if self.mode == MODE_REGEX:
            if self._regex is None:
                return []
            m = self._regex.search(line)
            if not m:
                return []
            tokens = m.groups() if m.groups() else (m.group(0),)
        else:                             # 分隔符
            tokens = re.split(_SEP_RX[self.sep_index], line)
        res = []
        for i, tok in enumerate(tokens):
            tok = (tok or "").strip()
            if tok == "":
                continue
            try:
                res.append(("CH%d" % (i + 1), float(tok)))
            except ValueError:
                continue                  # 非数值列跳过（通道号仍按 token 位置，与波形图一致）
        return res
