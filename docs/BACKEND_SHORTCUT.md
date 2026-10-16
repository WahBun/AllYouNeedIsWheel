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
