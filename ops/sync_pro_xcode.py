"""Keep the Pro's Wheel Xcode checkout at the latest merged official revision."""
import argparse
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPOSITORY = "WahBun/AllYouNeedIsWheel"
BRANCH = "Ben/wheel-1.8"
LABEL = "com.wahbun.wheel-pro-xcode-sync"
SUPPORT = Path.home() / "Library/Application Support/Wheel/XcodeSync"


def run(args, *, cwd=None, check=True, timeout=25):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1",
               GIT_OPTIONAL_LOCKS="0")
    for scheme, proxy in urllib.request.getproxies().items():
        if scheme in ("http", "https", "no") and scheme.upper() + "_PROXY" not in env:
            env.setdefault(scheme + "_proxy", proxy)
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                          check=check, timeout=timeout)


def git(root, *args, check=True):
    return run(["/usr/bin/git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
                "-c", "submodule.recurse=false", *args], cwd=root, check=check)


def git_text(root, *args):
    return git(root, *args).stdout.decode().strip()


def github(path):
    response = run(["gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}/{path}"])
    return json.loads(response.stdout)


def build_active():
    # xcodebuild covers CLI builds. Xcode GUI builds open an activity log and
    # the build service holds the build database while processing the build.
    cli = run(["/usr/bin/pgrep", "-x", "xcodebuild"], check=False)
    if cli.returncode != 1:
        return True
    opened = run(["/usr/sbin/lsof", "-nP", "-Fn", "-c", "Xcode",
                  "-c", "XCBBuildService", "-c", "SWBBuildService"], check=False)
    return opened.returncode not in (0, 1) or any(
        line.endswith(b"/XCBuildData/build.db") or
        (b"/Logs/Build/" in line and line.endswith(b".xcactivitylog"))
        for line in opened.stdout.splitlines())


def checkout_ok(root):
    origin = git_text(root, "remote", "get-url", "origin").removesuffix(".git")
    return (root == Path(git_text(root, "rev-parse", "--show-toplevel")).resolve()
            and (root / "ios/Wheel.xcodeproj/project.pbxproj").is_file()
            and origin in (f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}")
            and git_text(root, "branch", "--show-current") == BRANCH)


def sync(root):
    if not checkout_ok(root):
        return {"state": "paused", "reason": "Checkout, origin or branch does not match."}
    sha = github(f"git/ref/heads/{BRANCH}")["object"]["sha"]
    if not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("Invalid GitHub commit ID")
    head = git_text(root, "rev-parse", "HEAD")
    if head == sha:
        return {"state": "current", "head": head}
    pulls = github(f"commits/{sha}/pulls")
    merged = next((pr for pr in pulls if pr.get("merged_at") and pr.get("merge_commit_sha") == sha
                   and pr["base"]["ref"] == BRANCH
                   and pr["base"]["repo"]["full_name"] == REPOSITORY), None)
    if not merged:
        return {"state": "waiting", "reason": "Branch tip is not a confirmed PR merge.", "target": sha}
    if git(root, "cat-file", "-e", sha + "^{commit}", check=False).returncode:
        git(root, "fetch", "--no-tags", "--no-write-fetch-head", "--refmap=",
            "--no-auto-maintenance", "--no-recurse-submodules", "origin", sha)
    if git(root, "merge-base", "--is-ancestor", head, sha, check=False).returncode:
        return {"state": "blocked", "reason": "Local commits prevent fast-forward.", "target": sha}
    gitdir = Path(git_text(root, "rev-parse", "--absolute-git-dir"))
    if any((gitdir/name).exists() for name in ("index.lock", "MERGE_HEAD", "CHERRY_PICK_HEAD",
           "REVERT_HEAD", "rebase-apply", "rebase-merge", "sequencer", "BISECT_START")):
        return {"state": "busy", "reason": "Git operation in progress."}
    if github(f"git/ref/heads/{BRANCH}")["object"]["sha"] != sha:
        return {"state": "waiting", "reason": "Official branch moved during the check."}
    if build_active():
        return {"state": "busy", "reason": "Xcode build in progress."}
    if not checkout_ok(root) or git_text(root, "rev-parse", "HEAD") != head:
        return {"state": "busy", "reason": "Checkout changed during the check."}
    # Git holds its normal locks and refuses overlapping tracked, untracked and
    # ignored files. No stash, cleanup, rebase, new merge commit or push.
    result = git(root, "merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore",
                 "--no-edit", sha, check=False)
    if result.returncode:
        return {"state": "blocked", "reason": result.stderr.decode(errors="replace").strip()[:900],
                "target": sha}
    if git_text(root, "rev-parse", "HEAD") != sha:
        raise RuntimeError("Could not verify the updated checkout.")
    return {"state": "updated", "head": sha, "pr": merged["number"]}


def atomic_write(path, data, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        out.write(data)
    tmp = Path(out.name)
    tmp.chmod(mode)
    tmp.replace(path)


def record(result):
    path = SUPPORT / "status.json"
    old = json.loads(path.read_bytes()) if path.is_file() else {}
    now = datetime.now(timezone.utc).isoformat()
    last = ({"pr": result["pr"], "head": result["head"], "at": now}
            if result["state"] == "updated" else old.get("lastUpdate"))
    atomic_write(path, json.dumps(dict(result, checkedAt=now, lastUpdate=last)).encode())
    if result["state"] == "updated":
        message = f'Xcode project updated after PR #{result["pr"]} ({result["head"][:8]}).'
    elif result["state"] == "blocked" and (old.get("state"), old.get("target")) != ("blocked", result["target"]):
        message = "Local changes need attention before Wheel can sync."
    else:
        return
    run(["/usr/bin/osascript", "-e", f'display notification "{message}" with title "Wheel Xcode Sync"'],
        check=False)


def launcher(root, gh_dir):
    # LaunchServices attributes the Documents consent request to this specific
    # user app. A bare launchd Python/git process cannot present that request.
    app = SUPPORT / "Wheel Xcode Sync.app"
    shell = ("export PATH=" + shlex.quote(gh_dir + ":/usr/bin:/bin:/usr/sbin:/sbin") + "; exec " +
             shlex.join(["/usr/bin/python3", str(SUPPORT / "sync_pro_xcode.py"), str(root)]))
    script = "on run\ntry\ndo shell script " + json.dumps(shell, ensure_ascii=False) + "\nend try\nend run\n"
    stamp = SUPPORT / "launcher-source.txt"
    if app.is_dir() and stamp.exists() and stamp.read_text() == script:
        return app
    with tempfile.TemporaryDirectory(dir=SUPPORT) as folder:
        built = Path(folder) / app.name
        run(["/usr/bin/osacompile", "-o", str(built), "-e", script])
        info = built / "Contents/Info.plist"
        data = plistlib.loads(info.read_bytes())
        data.update(CFBundleIdentifier=LABEL, CFBundleName="Wheel Xcode Sync",
                    CFBundleDisplayName="Wheel Xcode Sync", LSUIElement=True,
                    NSDocumentsFolderUsageDescription="Sync the Wheel Xcode project after a GitHub merge.")
        info.write_bytes(plistlib.dumps(data))
        run(["/usr/bin/codesign", "--force", "--sign", "-", str(built)])
        if app.exists():
            app.rename(Path(folder) / "previous.app")
        built.rename(app)
    atomic_write(stamp, script.encode())
    return app


def install(root):
    if not checkout_ok(root) or not shutil.which("gh"):
        raise RuntimeError("Select the official Wheel checkout and configure GitHub CLI first.")
    SUPPORT.mkdir(mode=0o700, parents=True, exist_ok=True)
    worker = SUPPORT / "sync_pro_xcode.py"
    # Keep the installed worker independent of future checkouts.
    atomic_write(worker, Path(__file__).read_bytes())
    agent = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    agent.parent.mkdir(parents=True, exist_ok=True)
    app = launcher(root, str(Path(shutil.which("gh")).parent))
    config = {"Label": LABEL, "ProgramArguments": ["/usr/bin/open", "-g", "-W", str(app)],
              "StartInterval": 60, "RunAtLoad": True, "ProcessType": "Background",
              "EnvironmentVariables": {"PATH": str(Path(shutil.which("gh")).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin"}}
    atomic_write(agent, plistlib.dumps(config))
    domain = f"gui/{os.getuid()}"
    if run(["launchctl", "print", domain + "/" + LABEL], check=False).returncode == 0:
        run(["launchctl", "bootout", domain + "/" + LABEL])
    run(["launchctl", "bootstrap", domain, str(agent)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    root = args.checkout.resolve()
    if args.install:
        install(root)
    else:
        with (SUPPORT / "sync.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(0)
            try:
                result = sync(root)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or b"").decode(errors="replace").strip()[:450]
                result = {"state": "error", "reason": f"{Path(exc.cmd[0]).name} exited {exc.returncode}: {detail}"}
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
                result = {"state": "error", "reason": str(exc)}
            record(result)
            sys.exit(int(result["state"] == "error"))
