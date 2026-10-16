# Backend restart shortcut

The private Apple Shortcut `Restart Wheel Backend` asks for confirmation, runs
`wheel-backend-restart` over SSH to Mini, and displays the result. Use it only
when no order request is in progress or awaiting confirmation.

Its existing Shortcuts SSH public key is authorized with a forced command:
`/usr/bin/python3 /Users/legal/Projects/AllYouNeedIsWheel/ops/restart_backend.py ssh`.
The key is restricted against forwarding, PTY allocation and arbitrary commands.
Keys and host-specific SSH configuration remain outside Git.

The helper permits exactly `wheel-backend-check` and `wheel-backend-restart`.
Restart requests are serialized, signal only the Wheel launch agent, and wait
up to 45 seconds for a different service PID and a healthy local health response.
Failure does not trigger a second restart. Gateway is never restarted.

Validation uses `wheel-backend-check` without restarting anything. Actual restart
acceptance requires a separately authorized invocation. iPhone availability and
SSH key synchronization must be checked on the device; Tailscale must be connected.

## Combined menu: Wheel Backend

The combined private shortcut works through the same SSH action on macOS and iOS:

- **Deploy latest & Restart Backend** fetches the selected branch tip using
  `wheel-backend-deploy-preview`, shows the branch, current SHA, latest SHA and
  commit subject for confirmation, then sends `wheel-backend-deploy <SHA>` with
  the exact SHA from that preview. Cancel performs no deployment or restart.
  A later branch update does not change the confirmed deployment target.
- **Restart Backend only** retains the existing confirmation and
  `wheel-backend-restart` command.

The existing forced-command handler now also recognizes
`wheel-backend-deploy-check <SHA>` for read-only preflight. All deployment command
arguments must match 7–40 hexadecimal characters; arbitrary commands, branch
names, extra arguments, newlines and shell expressions are rejected. No SSH
permissions or authorized keys need to change.

Mini fetches the fixed repository and `codex/chart-labels-1.7` branch itself, checks
branch membership, clean working tree, forward-only history and Backend health,
then uses the same rollback/lock/pending-record/new-PID verification as the Pro
script. A failed GitHub fetch stops before changing the checkout. The shortcut
checks Mini's workspace; it cannot inspect uncommitted work on Pro. It deploys
only published commits. Commit and push selected changes on Pro beforehand.

`ops/build_backend_shortcut.py` generates the two-branch workflow from a private
export of the original `.wflow`, preserving its SSH connection settings. Generated
files and exports contain machine settings and stay outside Git. The original
shortcut is retained as a fallback. The generated menu uses only iOS-compatible
SSH, input, alert, menu and result actions; no Mac-only shell action is used.

REA inspected the original exported workflow, evidence
`ev_96589d3fa0a5783e73b16b719a6e03a8b60eedbc8debcbb81655d596a1524ff8`.
The actual iPhone still needs Tailscale and its existing authorized Shortcuts SSH
key. iCloud sync and successful execution on that physical device must be verified
there; a successful Mac import is not proof of iPhone execution.
