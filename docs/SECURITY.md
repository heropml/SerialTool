# Security model

## Online updates

Automatic download and execution requires all of the following:

- an HTTPS artifact URL;
- a valid 64-character SHA-256 in `latest.json`;
- an exact digest match after download;
- an exact byte-size match when the manifest supplies a size;
- the platform installer signature gate (`MZ` on Windows, shebang on Linux).

Old manifests without a digest remain version-readable, but the app only opens the
manual release page. Release scripts call `scripts/update_manifest_integrity.py` so
new Windows, macOS, and Linux artifacts receive their own digest and size fields.

## Trigger webhooks

The default boundary is public HTTPS only. CommTool resolves every destination
address, rejects the request if any answer is non-public, and connects directly to
one of those validated addresses. HTTPS certificate validation and SNI still use the
original hostname. Redirects are not followed.

A rule can explicitly enable **Allow LAN / HTTP (unsafe)** for a trusted local
integration. On an untrusted config/project import, declining to keep external
actions strips this permission. Keeping them only backfills a missing field on a
legacy rule; an explicit Off is left alone.

## Diagnostics and payload privacy

Application logs rotate at 2 MiB with three backups; each profile uses a separate
file so concurrent app processes do not race the same rotation. Logging sites record failures,
component names, counters, and lifecycle metadata—not serial/network RX or TX
payloads. **Help → Export diagnostics** creates a ZIP with:

- platform, Python, app, and dependency versions;
- a settings key inventory and a small allow-list of harmless UI values;
- the rotated application logs.

Command bodies, send history, webhook URLs, project content, and capture payloads are
not copied into the settings report. Review any support bundle before sharing it if
your exception messages or local paths are themselves sensitive.

## Reporting

Do not publish an exploit or a bundle containing credentials/device data in a public
issue. Contact the maintainer privately first and include the affected version,
platform, reproduction boundary, and a redacted diagnostic bundle where possible.
