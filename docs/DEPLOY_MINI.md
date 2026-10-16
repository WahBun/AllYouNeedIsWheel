# Deploy Mini from Pro

Run from the Pro checkout with Python 3.9+ and an existing SSH connection to Mini:

```sh
python3 ops/deploy_mini.py 82ac78b --check
python3 ops/deploy_mini.py 82ac78b
```

The first command validates only. The second deploys and requests one Backend
restart. Run when no order submission is in flight. Neither command sends broker
writes or changes Gateway. This updates Backend and served web files, not the
installed iPhone app. Health means HTTP process health, not broker connectivity,
account correctness or chart acceptance.

## One-time local settings

Create `ops/deploy-mini.local.json` on Pro (Git ignores this file):

```json
{
  "host": "your-mini-ssh-alias",
  "identity": "~/.ssh/your-mini-key",
  "repo": "~/Projects/AllYouNeedIsWheel",
  "branch": "codex/chart-labels-1.7"
}
```

`identity` is optional when your SSH configuration supplies it. Values can be
overridden with `--host`, `--identity`, `--repo`, and `--branch`. Do not commit
machine addresses, keys, credentials or local configuration. The Mini user must
already have `python3`, Git and the configured Backend LaunchAgent.

## What happens

1. Stop if Pro or Mini has staged, unstaged or untracked files, an unfinished Git
   operation, an unexpected origin, or Mini is not on the selected branch.
   Ignored settings, logs and databases are preserved.
2. Fetch the selected branch from the fixed GitHub repository on Pro. Resolve the
   requested short/full SHA and verify that it belongs to that branch. Mini must
   be an ancestor of the target; divergence and downgrades stop without reset.
3. Verify Mini's existing Backend process and health. `--check` ends here.
   If Mini already has the target SHA and is healthy, deployment is a no-op.
4. Transfer an incremental Git bundle over SSH; Mini does not need GitHub access.
   Acquire the existing Backend restart lock, repeat preflight, and reject a
   changed Mini HEAD. Create `rollback/deploy-<timestamp>-<id>` at the old SHA.
5. Record the pending deployment in `.git/wheel-deploy-pending.json`, fast-forward
   to the exact target without overwriting ignored files, and send SIGTERM only
   to `com.wahbun.allyouneediswheel`. The existing KeepAlive policy restarts it.
6. Wait up to 90 seconds for a different Backend PID and healthy HTTP response.
   Recheck target SHA and clean workspace, then remove the pending record and
   report success. Network calls have separate bounded timeouts.

The script does not install dependencies, migrate databases, change service
configuration, force-reset Git, or automatically roll back. Commits requiring
those steps need separate preparation. Refresh the browser after deployment.

## Failure or interrupted connection

Stop and inspect Mini before rerunning. A failure after update begins can mean
the new code is present but the running version is unknown. The pending record
blocks another deployment until the operator reconciles the state. The printed
rollback branch and the pending record retain the previous SHA; no record is
removed automatically on failure.

On Mini, inspect:

```sh
cd ~/Projects/AllYouNeedIsWheel
git status --short
git rev-parse HEAD
cat .git/wheel-deploy-pending.json
launchctl print "gui/$(id -u)/com.wahbun.allyouneediswheel"
curl --max-time 10 -fsS http://127.0.0.1:8000/health
tail -n 60 logs/web-error.log
```

If necessary, use the recorded rollback branch in a separately reviewed recovery;
the deploy command deliberately refuses backward updates. Do not delete the
pending record merely to bypass a failure. Clear it only after confirming the
intended checkout, Backend process and health (including any manually completed
restart). A deployment rollback preserves code, not a snapshot of live databases.

## Validation

`python3 tests/test_deploy_mini.py` uses disposable real Git repositories and
mocked Backend calls. It never connects to SSH or IB. REA inspected the actual
Mini LaunchAgent before implementation: fixed service label, project working
directory, KeepAlive enabled, one Gunicorn worker. Evidence:
`ev_4dcdb4b4b687abf82cdd8f3ec3268c33185ff5299587268dd8626a743f02f150`.
