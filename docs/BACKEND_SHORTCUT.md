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

### SSH timeout repair (2026-10-16)

The native runner logged NMSSH error 0 with an empty message after exactly 120
seconds. Mini's direct GitHub connection timed out while the same read-only Git
request through its existing system proxy succeeded. Git invoked from SSH does
not automatically use the macOS system proxy. GitHub fetches now inherit that
existing proxy for the subprocess only, respect explicit environment settings,
and stop after 20 seconds. Errors go to stderr so Shortcuts can display them.
No system proxy, SSH permissions, broker state or retry policy is changed.

REA inspected the exported workflow and its SHA references
(`ev_1434a7d54732f335ec958cbe4049ef73cecb2e0e258be60d6c08b4f724b8aad7`).
The actual Mac shortcut completed preview, confirmation and the read-only
deployment-check action. Diagnostic action edits were restored afterward.
The helper-only repair can be advanced independently of chart changes, without
restarting Backend; the user performs the subsequent full deployment.

### Choose whether to restart (2026-10-16)

Deploy latest first previews and confirms an exact SHA. A second menu then offers
Deploy only or Deploy & Restart Backend; canceling either step performs no update.
Both branches use the same confirmed SHA. The fixed SSH allowlist adds
`wheel-backend-deploy-only <SHA>` without permitting arbitrary shell commands.

Deploy only retains clean-worktree, branch/ancestry, rollback, lock and pending
operation checks. It verifies the updated checkout, unchanged Backend PID and
health, but does not claim the running Python process loaded that commit. Refresh
web pages for assets read dynamically; Backend Python changes require a later
restart, and bundled iPhone assets still require the user's Xcode Run. Explicit
Deploy & Restart Backend restarts even at the same SHA, supporting a later restart
after a code-only update. The standalone Pro deployment CLI retains its previous
same-version no-op behavior. Gateway remains outside both deployment choices.

Validation: 24 focused Git/mock-service, SSH allowlist and workflow-structure tests
passed. REA inspected the 19-action generated workflow, including the nested menu
and pinned SHA references (ev_65deec5a856ba0c021595dcd8069f673c92ade47b86a2a7de5f491b0d00f2cae).

### Automatic restart advice

The version preview now includes Restart recommended, No restart expected or
Review required, with reasons and representative changed files. This is advice
only: the existing second menu and explicit user choice still control deployment.
The comparison uses exact commits and disables rename detection so neither the
old nor new path is missed. Backend Python and cached templates recommend restart;
known request-loaded chart assets, static assets, docs/tests and on-demand helper
scripts do not. Dependencies, migrations, startup/configuration and unclassified
files require review; a restart alone may not activate those changes. Native iPhone
changes still need an app rebuild.

Code-only updates that may need restart retain their original baseline privately
in `.git/wheel-deferred-restart.json`. Later previews include those changes even
when the next update only changes docs. A verified deployment restart or standalone
shortcut restart clears the advisory record. An external restart may leave a
conservative recommendation; an invalid record produces Review required. This is
not proof of the running process's loaded version and does not weaken pending
deployment, broker or no-replay guards.

The existing 19-action workflow was rechecked with REA
(ev_228bb4645fb753d78f42e33688e153643b284fc86f62e248c9d5b9670c864db2).
No workflow replacement is needed: its existing summary field carries the advice.
29 focused tests cover classification, rename paths, deferred backend changes
across a later docs update, invalid state, confirmed restart clearing, timeout,
SSH allowlisting and the unchanged manual selection workflow.
