#!/usr/bin/env python3
"""User-triggered Xcode signing renewal. Default mode performs read-only checks."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


class RenewalError(Exception):
    pass


def date(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def command(args, timeout=60, cwd=ROOT, log=None):
    try:
        if log:
            with log.open("w") as stream:
                result = subprocess.run(args, cwd=cwd, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=timeout)
            output = ""
        else:
            result = subprocess.run(args, cwd=cwd, capture_output=True,
                                    text=True, timeout=timeout)
            output = result.stdout
    except subprocess.TimeoutExpired as exc:
        raise RenewalError("Command timed out; no automatic retry. Check the run log.") from exc
    if result.returncode:
        detail = f" See {log}." if log else f" {result.stderr.strip()[-1200:]}"
        raise RenewalError(f"{Path(args[0]).name} failed (exit {result.returncode}).{detail}")
    return output.strip()


def github_branch_head(branch):
    # SSH Git does not inherit macOS system proxies. Apply the existing settings
    # only to this read; preserve explicit environment choices and host config.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    for scheme, proxy in urllib.request.getproxies().items():
        key = scheme + "_proxy"
        if scheme in ("http", "https", "no") and key not in env and key.upper() not in env:
            env[key] = proxy
    args = ["/usr/bin/git", "-c", "credential.interactive=false", "ls-remote",
            "--exit-code", "origin", "refs/heads/" + branch]
    with subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        try:
            output, error = process.communicate(timeout=20)
        except subprocess.TimeoutExpired as exc:
            # Git's HTTPS helper can outlive its parent and keep the SSH channel
            # open. Stop this dedicated process group, including that helper.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise RenewalError("GitHub check timed out after 20 seconds. No signing or build was started. Check the Pro's GitHub connectivity.") from exc
        if process.returncode:
            raise RenewalError(f"GitHub check failed (exit {process.returncode}). {error.strip()[-1200:]}")
    rows = output.split()
    if not rows:
        raise RenewalError("GitHub returned no commit for the configured branch.")
    return rows[0]


def github_revision(config):
    git = lambda *args: command(["/usr/bin/git", *args])
    if git("status", "--porcelain"):
        raise RenewalError("The checkout has uncommitted changes. Commit and push them first.")
    branch = git("branch", "--show-current")
    if branch != config["branch"]:
        raise RenewalError("The checkout is on a different branch. Select the configured branch first.")
    remote = git("remote", "get-url", "origin")
    if remote.rstrip("/").removesuffix(".git") != config["repository"].rstrip("/").removesuffix(".git"):
        raise RenewalError("The GitHub repository does not match the local renewal settings.")
    sha = git("rev-parse", "HEAD")
    if github_branch_head(branch) != sha:
        raise RenewalError("Local HEAD differs from GitHub. Review and synchronize this branch first.")
    return sha


def profile_matches(profile, config):
    return (profile.get("TeamIdentifier") == [config["teamID"]]
            and profile.get("Entitlements", {}).get("application-identifier") == config["teamID"] + "." + config["bundleID"]
            and config["deviceUDID"] in profile.get("ProvisionedDevices", []))


def read_profile(path):
    return plistlib.loads(command(["/usr/bin/security", "cms", "-D", "-i", str(path)]).encode())


def validate_profile(profile, config, previous_expiry=None, now=None, started=None):
    now = now or datetime.now(UTC)
    if not profile_matches(profile, config):
        raise RenewalError("The signed profile does not match the expected team, app and iPhone.")
    expiry = date(profile["ExpirationDate"])
    if expiry < now + timedelta(days=6):
        raise RenewalError("The signed profile has less than six days remaining. Renewal was not completed.")
    if previous_expiry and expiry <= date(previous_expiry):
        raise RenewalError("Apple reused the existing profile; its expiration did not extend.")
    if started and date(profile["CreationDate"]) < started - timedelta(minutes=5):
        raise RenewalError("Xcode did not issue a fresh provisioning profile.")
    return expiry


class ProfileRefresh:
    """Back up only this app's cached profile; restore it on any failed build."""
    def __init__(self, config, run, previous_expiry=None, directories=None):
        self.config, self.run = config, run
        self.previous = date(previous_expiry) if previous_expiry else None
        self.directories = directories if directories is not None else [
            Path.home() / "Library/Developer/Xcode/UserData/Provisioning Profiles",
            Path.home() / "Library/MobileDevice/Provisioning Profiles"]
        self.manifest = run / "profile-refresh.json"
        self.entries = []

    @staticmethod
    def restore(manifest):
        data = json.loads(manifest.read_text())
        for entry in data["profiles"]:
            original, backup = Path(entry["original"]), Path(entry["backup"])
            blob = backup.read_bytes()
            if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
                raise RenewalError("A profile backup failed its integrity check; inspect the saved run.")
            # Never overwrite a newly generated profile or another process's file.
            if not original.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                with original.open("xb") as output:
                    output.write(blob)
        data["status"] = "restored"
        save_json(manifest, data)

    def __enter__(self):
        backup_dir = self.run / "profile-backups"
        backup_dir.mkdir()
        for directory in self.directories:
            for path in sorted(directory.glob("*.mobileprovision")):
                profile = read_profile(path)
                if not profile_matches(profile, self.config):
                    continue
                expiry = date(profile["ExpirationDate"])
                self.previous = max(self.previous, expiry) if self.previous else expiry
                blob = path.read_bytes()
                backup = backup_dir / f"{len(self.entries)}.mobileprovision"
                backup.write_bytes(blob)
                if backup.read_bytes() != blob:
                    raise RenewalError("Could not verify the original profile backup.")
                self.entries.append(dict(original=str(path), backup=str(backup),
                                         sha256=hashlib.sha256(blob).hexdigest()))
        # Persist every recovery location before removing any cached profile.
        save_json(self.manifest, dict(status="pending", profiles=self.entries))
        try:
            for entry in self.entries:
                path = Path(entry["original"])
                if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                    raise RenewalError("The signing profile changed during preparation. Try again after Xcode is idle.")
                path.unlink()
        except BaseException:
            self.restore(self.manifest)
            raise
        return self

    def __exit__(self, kind, value, traceback):
        if kind is not None:
            self.restore(self.manifest)
        else:
            save_json(self.manifest, dict(status="completed", profiles=self.entries))


def wait_for_fresh_profile(refresh, started, timeout=180):
    # Xcode starts signing preparation asynchronously when the project opens.
    # A Build before this completes can reference its now-removed cached file.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for directory in refresh.directories:
            for path in directory.glob("*.mobileprovision"):
                try:
                    profile = read_profile(path)
                    validate_profile(profile, refresh.config, refresh.previous, started=started)
                except (RenewalError, OSError, ValueError, KeyError):
                    continue
                return
        time.sleep(1)
    raise RenewalError("Xcode did not finish preparing a new signing profile. Check Signing & Capabilities; no build was started.")


def recover_interrupted(state):
    pending = [p for p in state.glob("*/profile-refresh.json")
               if json.loads(p.read_text()).get("status") == "pending"]
    for path in pending:
        ProfileRefresh.restore(path)
    if pending:
        raise RenewalError("Restored signing profiles from an interrupted run. Check that Xcode is idle before running again.")


class Renewal:
    def __init__(self, config, run):
        self.config = config
        self.run = run
    def preflight(self):
        if Path("/dev/console").stat().st_uid != os.getuid():
            raise RenewalError("Sign in to the Mac desktop with this SSH account before renewing signing.")
        if not (ROOT / "ios/Signing.local.xcconfig").is_file():
            raise RenewalError("Configure ios/Signing.local.xcconfig in Xcode first.")
        for key in ("teamID", "bundleID", "deviceUDID"):
            if not isinstance(self.config.get(key), str) or not self.config[key].strip():
                raise RenewalError("The saved signing identity is incomplete. Configure the existing app and registered iPhone first.")

    def build(self, sha, previous_expiry):
        source = self.run / "source"
        source.mkdir()
        archive = self.run / "source.tar"
        command(["/usr/bin/git", "archive", "--format=tar", "--output", str(archive), sha])
        command(["/usr/bin/tar", "-xf", str(archive), "-C", str(source)])
        signing = ROOT / "ios/Signing.local.xcconfig"
        if not signing.is_file():
            raise RenewalError("Configure ios/Signing.local.xcconfig in Xcode first.")
        # Xcode's scripting results identify a workspace by its filename.
        # Give this isolated copy a unique name so an open developer project
        # cannot capture the Build result reference.
        project = source / "ios" / f"WheelRenewal-{self.run.name}.xcodeproj"
        (source / "ios/Wheel.xcodeproj").rename(project)
        for scheme in (project / "xcshareddata/xcschemes").glob("*.xcscheme"):
            scheme.write_text(scheme.read_text().replace("container:Wheel.xcodeproj", "container:" + project.name))
        local_signing = source / "ios/Signing.local.xcconfig"
        products = self.run / "Products"
        intermediates = self.run / "Intermediates"
        local_signing.write_text(signing.read_text() +
                                f'\nSYMROOT = {products}\nOBJROOT = {intermediates}\n')
        local_signing.chmod(0o600)
        started = datetime.now(UTC)
        with ProfileRefresh(self.config, self.run, previous_expiry) as refresh:
            action = ["/usr/bin/osascript", str(source / "ios/renew_signing.applescript"),
                      str(project), str(self.run / "build.log")]
            command([*action, "prepare"], timeout=180, log=self.run / "xcode-prepare.log")
            wait_for_fresh_profile(refresh, started)
            command([*action, "build"], timeout=1320, log=self.run / "xcode-action.log")
            app = products / "Debug-iphoneos/Wheel.app"
            command(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
            profile = read_profile(app / "embedded.mobileprovision")
            expiry = validate_profile(profile, self.config, refresh.previous, started=started)
            info = plistlib.loads((app / "Info.plist").read_bytes())
            if info["CFBundleIdentifier"] != self.config["bundleID"]:
                raise RenewalError("The built application has a different bundle identifier.")
            save_json(self.run / "signing-verification.json", {
                "created": date(profile["CreationDate"]).isoformat(), "expires": expiry.isoformat(),
                "previousExpires": refresh.previous.isoformat() if refresh.previous else None,
                "profileUUID": profile["UUID"], "codesignVerified": True})
        return app, expiry, info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Read-only GitHub and Mac readiness check (default)")
    modes.add_argument("--build-only", action="store_true", help="Build and validate signing without installing")
    modes.add_argument("--renew", action="store_true", help="Renew and build a signed package; installation remains manual")
    args = parser.parse_args(argv)
    os.umask(0o077)
    run = None
    try:
        config = json.loads((ROOT / "ios/Renew.local.json").read_text())
        state = ROOT / "ios/.renewal"
        state.mkdir(exist_ok=True)
        with (state / "renew.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RenewalError("Another renewal is already running.") from exc
            run = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=state))
            if args.renew or args.build_only:
                recover_interrupted(state)
            sha = github_revision(config)
            print(f"GitHub verified: {config['branch']} @ {sha}", flush=True)
            renewal = Renewal(config, run)
            if not (args.renew or args.build_only):
                renewal.preflight()
                print("Ready. No signing, installation, or app launch was performed.")
                return 0
            renewal.preflight()
            receipt_path = state / "last-build.json"
            previous = config.get("baselineProfileExpires")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if any(receipt.get(key) != config[key] for key in ("bundleID", "teamID", "deviceUDID")):
                    raise RenewalError("The previous build receipt belongs to a different app or device.")
                previous = receipt["profileExpires"]
            print("Refreshing signing through Xcode Build and verifying the new expiration...", flush=True)
            app, expiry, info = renewal.build(sha, previous)
            details = {"commit": sha, "branch": config["branch"], "profileExpires": expiry.isoformat(),
                       "bundleID": config["bundleID"], "teamID": config["teamID"],
                       "deviceUDID": config["deviceUDID"], "builtApp": str(app),
                       "builtAt": datetime.now(UTC).isoformat()}
            save_json(run / "build-receipt.json", details)
            save_json(receipt_path, details)
            print(f"Signing renewed. No iPhone installation.\n"
                  f"Signature expires: {expiry.astimezone():%Y-%m-%d %H:%M %Z}\n"
                  f"Commit: {sha}\nSigned app: {app}\nInstall the app manually when ready.")
            return 0
    except (RenewalError, OSError, ValueError, KeyError) as exc:
        print(f"Renewal stopped: {exc}", file=sys.stderr)
        if run:
            print(f"Run logs: {run}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
