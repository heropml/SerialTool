# -*- coding: utf-8 -*-
"""Serial UI text <-> pyserial constants (Qt-free).

S-2 R31: shared by CommTool open_conn / live apply and BridgeDialog.
"""
import serial

PARITY_MAP = {
    "None": serial.PARITY_NONE,
    "Even": serial.PARITY_EVEN,
    "Odd": serial.PARITY_ODD,
    "Mark": serial.PARITY_MARK,
    "Space": serial.PARITY_SPACE,
}
STOPBITS_MAP = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}
DATABITS_MAP = {
    "5": serial.FIVEBITS,
    "6": serial.SIXBITS,
    "7": serial.SEVENBITS,
    "8": serial.EIGHTBITS,
}
FLOW_MAP = {
    "None": "none",
    "RTS/CTS": "rtscts",
    "XON/XOFF": "xonxoff",
}

BAUD_RATES = (
    "1200", "2400", "4800", "9600", "19200", "38400", "57600",
    "115200", "230400", "256000", "460800", "500000", "512000",
    "600000", "750000", "921600", "1000000", "1500000", "2000000",
)
DATABITS_OPTIONS = ("5", "6", "7", "8")
PARITY_OPTIONS = ("None", "Even", "Odd", "Mark", "Space")
STOPBITS_OPTIONS = ("1", "1.5", "2")
FLOW_OPTIONS = ("None", "RTS/CTS", "XON/XOFF")


def resolve_pyserial(databits, parity, stopbits, flow="None"):
    """Map UI combo texts to pyserial kwargs (+ flow string for SerialConn)."""
    return {
        "bytesize": DATABITS_MAP[databits],
        "parity": PARITY_MAP[parity],
        "stopbits": STOPBITS_MAP[stopbits],
        "flow": FLOW_MAP.get(flow, "none"),
    }
