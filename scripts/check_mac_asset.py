# -*- coding: utf-8 -*-
"""Verify that a GitHub Release actually hosts CommTool_vX.Y.Z.dmg.

Used by release_macos.sh as a publish gate. Exit 0 on success, 1 on failure.

Usage:
  python scripts/check_mac_asset.py 1.5.0
  python scripts/check_mac_asset.py 1.5.0 --repo heropml/SerialTool
"""
from __future__ import print_function

import argparse
import json
import os
import subprocess
import sys
import urllib.request


def _run_gh(args):
    env = os.environ.copy()
    # Prefer caller-provided proxy; do not clear it (macOS CI may need it).
    try:
        out = subprocess.check_output(
            ["gh"] + args, stderr=subprocess.STDOUT, env=env)
        return out.decode("utf-8", errors="replace")
    except (OSError, subprocess.CalledProcessError) as e:
        msg = getattr(e, "output", b"") or str(e).encode("utf-8")
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", errors="replace")
        raise RuntimeError("gh failed: %s" % msg)


def _release_data(repo, tag):
    """Read public release metadata via gh, falling back to GitHub's API."""
    errors = []
    try:
        return json.loads(_run_gh([
            "release", "view", tag, "--repo", repo, "--json", "assets",
        ]))
    except (RuntimeError, ValueError) as e:
        errors.append(str(e))

    url = "https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CommTool-release-gate",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer %s" % token
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        errors.append("GitHub API failed: %s" % e)
    raise RuntimeError("; ".join(errors))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("version", help="App version, e.g. 1.5.0")
    p.add_argument("--repo", default="heropml/SerialTool")
    p.add_argument("--tag-prefix", default="comm-v")
    args = p.parse_args(argv)

    version = args.version.lstrip("vV")
    tag = "%s%s" % (args.tag_prefix, version)
    want = "CommTool_v%s.dmg" % version

    try:
        data = _release_data(args.repo, tag)
    except RuntimeError as e:
        raise SystemExit(str(e))
    names = [a.get("name") for a in (data.get("assets") or []) if isinstance(a, dict)]
    if want not in names:
        raise SystemExit(
            "Mac publish gate FAILED: %s missing from GitHub Release %s (assets=%s)"
            % (want, tag, names))
    print("Mac publish gate OK: %s present on %s" % (want, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
