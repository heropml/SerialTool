#!/usr/bin/env python3
"""Write one built artifact's SHA-256 and byte size into latest.json."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


FIELDS = {
    "windows": ("sha256", "size"),
    "mac": ("sha256_mac", "size_mac"),
    "linux": ("sha256_linux", "size_linux"),
}


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_manifest(manifest_path, artifact_path, platform_name, version=""):
    manifest = Path(manifest_path)
    artifact = Path(artifact_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if version and str(data.get("version", "")) != str(version):
        return False
    hash_field, size_field = FIELDS[platform_name]
    artifact_size = artifact.stat().st_size
    if artifact_size <= 0:
        raise ValueError("artifact must not be empty")
    data[hash_field] = sha256_file(artifact)
    data[size_field] = artifact_size
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, temp_path = tempfile.mkstemp(
        prefix=".%s-" % manifest.name, suffix=".tmp", dir=str(manifest.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, manifest)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("artifact")
    parser.add_argument("platform", choices=sorted(FIELDS))
    parser.add_argument("--version", default="")
    args = parser.parse_args(argv)
    changed = update_manifest(
        args.manifest, args.artifact, args.platform, version=args.version)
    print("manifest integrity updated" if changed else "manifest version differs; skipped")
    return 0 if changed else 2


if __name__ == "__main__":
    raise SystemExit(main())
