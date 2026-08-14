#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify GitHub Release hosts CommTool_Setup_vX.Y.Z_linux_x86_64.run."""
import sys

from check_mac_asset import main as _main


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    version = argv[0] if argv else ""
    ver = version.lstrip("vV")
    extra = ["--asset", "CommTool_Setup_v%s_linux_x86_64.run" % ver]
    return _main(argv + extra)


if __name__ == "__main__":
    sys.exit(main())
