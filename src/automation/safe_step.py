# -*- coding: utf-8 -*-
"""One-step cleanup helper shared by serial_io / net_io.

Failure is logged at debug and swallowed so later steps in the same
cleanup sequence still run.
"""
import logging

_log = logging.getLogger(__name__)


def safe_step(func, *args, log=None, kind="cleanup step"):
    try:
        func(*args)
        return True
    except Exception:
        logger = log if log is not None else _log
        logger.debug("%s %s failed", kind, getattr(func, "__name__", func),
                     exc_info=True)
        return False
