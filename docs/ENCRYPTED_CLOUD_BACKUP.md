# Optional encrypted off-device backup

This job is independent of Backend and Gateway. It reads only completed daily
SQLite snapshots produced by `ops/maintenance.py`; it does not open live databases,
import Wheel, call IB, modify orders, rotate logs or restart services.

The initial scope is the six existing snapshot stores: Paper orders, Live orders,
performance, drawings, favorites and notifications. This is **not** a full Mac
image, credential backup or replacement for GitHub. Private configuration,
certificates and recovery keys are not uploaded by this job.

## Preparation

Validate a synthetic file through encryption, actual cloud upload/download and
decryption before enabling this job. Use a supported `age` binary and a separately
reviewed cloud189 CLI. Initial validation used age 1.3.2 and gowsp/cloud189 0.7.0
on Apple silicon, with release checksums verified. The uploader is third-party,
not an officially supported Tianyi backup API. Its login can expire; scan-login
does not guarantee automatic reauthentication. Keep local copies when it fails.

Generate a **new production** age identity on the recovery computer. Store its
private key outside Git and outside the upload directory, with permissions 0600.
Keep an additional user-controlled offline copy; losing every private-key copy
makes the encrypted cloud backups unrecoverable. Mini needs only the public
recipient string. Cloud credentials belong in a separate 0600 file in a 0700
directory; never put them in command arguments or logs.

Example private configuration (all paths must be absolute):

```json
{
  "maintenance_directory": "/Users/USER/Library/Application Support/Wheel/Maintenance",
  "state_directory": "/Users/USER/Library/Application Support/Wheel/CloudBackup/state",
  "age": "/Users/USER/Library/Application Support/Wheel/CloudBackup/bin/age",
  "recipient": "age1REPLACE_WITH_PUBLIC_RECIPIENT",
  "cloud189": "/Users/USER/Library/Application Support/Wheel/CloudBackup/bin/cloud189",
  "credentials": "/Users/USER/Library/Application Support/Wheel/CloudBackup/cloud189.json",
  "remote_directory": "/Wheel-Encrypted-Backups",
  "sources": ["orders-paper", "orders-live", "performance", "chart_drawings", "chart_favorites", "notifications"]
}
```

Create the dedicated remote directory once. Install the script from an exact
pushed GitHub SHA into a private, independent directory. Record that SHA and
binary checksums there; do not modify Mini's running checkout to enable backups.

Run with `/usr/bin/nice -n 15 /usr/bin/python3 cloud_backup.py --config CONFIG`.
Use a separate LaunchAgent with `ProcessType=Background`, `LowPriorityIO=true`
and an hourly schedule at minute 15, after the existing maintenance task. Do not
add KeepAlive or change the Backend/Gateway LaunchAgents. It starts after macOS
login, not before login. Test one real archive and restore it before bootstrapping
the new agent. Confirm Backend's PID and health before and after.

## Verification and failure behavior

- All configured sources must have a common daily snapshot, at most one day old;
  maintenance's last success must be within 30 hours. Symlinks and path traversal
  are rejected. A snapshot set larger than 512 MiB is rejected for review.
- A manifest includes each source's size and SHA-256. A gzip tar streams directly
  into age; no plaintext archive is stored on Mini. Snapshot hashes are checked
  again after encryption.
- A content-derived filename and upload `skip` policy prevent overwrites on retry.
  Upload is single-concurrency. Remote size/checksum and a full download SHA-256
  must match before `status.json` records success. Cloud MD5 is only a transport
  check; age authenticates the ciphertext and restore checks use SHA-256.
- A lock prevents concurrent jobs. Repeated checks skip a previously verified
  unchanged set. Transfer commands time out after 180 seconds; failures are retried
  on the next scheduled run, not in a tight loop. An encrypted local copy and
  previous success status survive cloud errors. Sanitized failure details live in
  `last_failure.json`; no signed cloud URLs are logged.
- This first version does not delete cloud archives or local encrypted archives.
  Existing maintenance still retains its own 14 daily database snapshots. Review
  storage growth before adding a separately authorized retention policy.

## Restore and disable

Download an archive to a separate recovery directory on Pro, decrypt with age,
inspect `manifest.json`, verify every extracted source SHA-256 and run SQLite
`PRAGMA integrity_check` on those extracted copies. Never restore over running
databases. Actual recovery of orders requires a planned maintenance window and
read-only reconciliation with IB before trading resumes.

To pause automatic cloud backups, boot out **only**
`com.wahbun.wheel.cloud-backup`; leave existing maintenance, Backend and Gateway
running. Local daily maintenance backups remain independent.

Focused checks:

```sh
WHEEL_TEST_AGE=/absolute/path/to/age python3 -m unittest discover -s tests -p test_cloud_backup.py -v
```
