# Gateway stable upgrade — 2026-10-07

Updated the existing single-instance Mini Gateway from 10.45.1j / IBC 3.24.1 to the freshly pulled stable 10.50.1f / IBC 3.24.2, native arm64.

- Registry stable digest: sha256:1e2236804ac949b789197c225a048c0c891c9958f948c87166226e5b647ff581
- Running platform image: sha256:2b616da677b246b14c97c9c2d65ab18e7a80228d242caea0e9c70ffc3935911b
- Original image retained locally as wheel-gateway-rollback:20261007. Private backup of original container metadata, compose/.env, and stopped-container settings stored on Mini under Library/Application Support/Wheel/gateway-backups/20261007-141258. Do not commit those private files.
- Verified original account credentials, Paper mode, API read-only setting and host port mappings unchanged. No dual-instance configuration adopted. No order writes or phone installation.
- Container start 06:12:59 UTC, login completed 06:13:14 UTC: roughly 15 seconds on this run. Not a controlled comparison or a guarantee. Backend logged successful API connection at 14:13:30 Shanghai time.
- First historical read timed out. A subsequent read recovered 375 MNQ five-minute bars. Final read reported live IB tick-by-tick with current bid/ask and tick timestamp; Paper profile verified.
- Live authentication and broker execution under the new image remain untested. Retain RTH acceptance gate.
