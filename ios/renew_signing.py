#!/usr/bin/env python3
"""User-triggered Xcode signing renewal. Default mode performs read-only checks."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
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


def github_command(arguments, timeout):
    # SSH Git does not inherit macOS system proxies. Apply the existing settings
    # only to this read; preserve explicit environment choices and host config.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    for scheme, proxy in urllib.request.getproxies().items():
        key = scheme + "_proxy"
        if scheme in ("http", "https", "no") and key not in env and key.upper() not in env:
            env[key] = proxy
    args = ["/usr/bin/git", "-c", "credential.interactive=false", *arguments]
    with subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        try:
            output, error = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # Git's HTTPS helper can outlive its parent and keep the SSH channel
            # open. Stop this dedicated process group, including that helper.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise RenewalError(f"GitHub check timed out after {timeout} seconds. No signing or build was started. Check the Pro's GitHub connectivity.") from exc
        if process.returncode:
            raise RenewalError(f"GitHub check failed (exit {process.returncode}). {error.strip()[-1200:]}")
    return output.strip()


def github_branch_head(branch):
    ref = "refs/heads/" + branch
    output = github_command(["ls-remote", "--exit-code", "origin", ref], timeout=20)
    fields = output.split()
    if len(fields) != 2 or fields[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise RenewalError("GitHub did not return one exact commit for the configured branch.")
    return fields[0]


def github_revision(config):
    remote = command(["/usr/bin/git", "remote", "get-url", "origin"], cwd=ROOT)
    if remote.rstrip("/").removesuffix(".git") != config["repository"].rstrip("/").removesuffix(".git"):
        raise RenewalError("The GitHub repository does not match the local renewal settings.")
    return github_branch_head(config["branch"])


def archive_revision(sha, archive):
    # A GitHub revision can be newer than every local branch. Fetch the pinned
    # object without updating the checkout, tracking refs, tags or FETCH_HEAD.
    git = ["/usr/bin/git", "--no-replace-objects"]
    exists = subprocess.run([*git, "cat-file", "-e", sha + "^{commit}"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if exists.returncode:
        github_command(["fetch", "--no-tags", "--no-write-fetch-head", "--refmap=",
                        "--no-recurse-submodules", "--no-auto-maintenance", "origin", sha], timeout=120)
    command([*git, "archive", "--format=tar", "--output", str(archive), sha], cwd=ROOT)


def profile_matches(profile, config):
    return (profile.get("TeamIdentifier") == [config["teamID"]]
            and profile.get("Entitlements", {}).get("application-identifier") == config["teamID"] + "." + config["bundleID"]
            and config["deviceUDID"] in profile.get("ProvisionedDevices", []))


def read_profile(path):
    return plistlib.loads(command(["/usr/bin/security", "cms", "-D", "-i", str(path)]).encode())


def validate_profile(profile, config, previous_expiry=None, now=None, started=None):
    now = now or datetime.now(UTC)
    if not profile_matches(profile, config):
        raise RenewalError("The signed profile does not match the expected team, app and device.")
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
    manifests = [*state.glob("*/profile-refresh.json"), *state.glob("*/watch/profile-refresh.json")]
    pending = [p for p in manifests
               if json.loads(p.read_text()).get("status") == "pending"]
    for path in pending:
        ProfileRefresh.restore(path)
    if pending:
        raise RenewalError("Restored signing profiles from an interrupted run. Check that Xcode is idle before running again.")


class Renewal:
    def __init__(self, config, run):
        self.config = config
        self.run = run
        self.watch = None
        if "watchDeviceUDID" in config:
            udid = config["watchDeviceUDID"]
            if not isinstance(udid, str) or not udid.strip() or udid == config["deviceUDID"]:
                raise RenewalError("Set watchDeviceUDID to the registered Apple Watch identifier.")
            self.watch = dict(config, deviceUDID=udid, bundleID=config["bundleID"] + ".watchkitapp")
    def preflight(self):
        if Path("/dev/console").stat().st_uid != os.getuid():
            raise RenewalError("Sign in to the Mac desktop with this SSH account before renewing signing.")
        if not (ROOT / "ios/Signing.local.xcconfig").is_file():
            raise RenewalError("Configure ios/Signing.local.xcconfig in Xcode first.")
        for key in ("teamID", "bundleID", "deviceUDID"):
            if not isinstance(self.config.get(key), str) or not self.config[key].strip():
                raise RenewalError("The saved signing identity is incomplete. Configure the existing app and registered iPhone first.")

    def build(self, sha, previous_expiry, watch_previous=None):
        source = self.run / "source"
        source.mkdir()
        archive = self.run / "source.tar"
        archive_revision(sha, archive)
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
        with ExitStack() as stack:
            phone = stack.enter_context(ProfileRefresh(self.config, self.run, previous_expiry))
            if self.watch:
                watch_dir = self.run / "watch"
                watch_dir.mkdir()
                watch = stack.enter_context(ProfileRefresh(self.watch, watch_dir, watch_previous))
            action = ["/usr/bin/osascript", str(source / "ios/renew_signing.applescript"),
                      str(project), str(self.run / "build.log")]
            command([*action, "prepare"], timeout=180, log=self.run / "xcode-prepare.log")
            wait_for_fresh_profile(phone, started)
            if self.watch:
                wait_for_fresh_profile(watch, started)
            command([*action, "build"], timeout=1320, log=self.run / "xcode-action.log")
            app = products / "Debug-iphoneos/Wheel.app"
            command(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
            expiry = verify_signed_package(app, phone, started)
            watch_receipt = {}
            if self.watch:
                embedded = app / "Watch/WheelWatch.app"
                watch_expiry = verify_signed_package(embedded, watch, started, companion=self.config["bundleID"])
                watch_receipt = {"bundleID": self.watch["bundleID"], "deviceUDID": self.watch["deviceUDID"],
                                 "builtApp": str(embedded), "profileExpires": watch_expiry.isoformat()}
        return app, expiry, watch_receipt


def verify_signed_package(app, refresh, started, companion=None):
    info = plistlib.loads((app / "Info.plist").read_bytes())
    if info["CFBundleIdentifier"] != refresh.config["bundleID"]:
        raise RenewalError("The built application has a different bundle identifier.")
    if companion and info.get("WKCompanionAppBundleIdentifier") != companion:
        raise RenewalError("The embedded Watch app belongs to a different iPhone app.")
    profile = read_profile(app / "embedded.mobileprovision")
    expiry = validate_profile(profile, refresh.config, refresh.previous, started=started)
    save_json(refresh.run / "signing-verification.json", {
        "created": date(profile["CreationDate"]).isoformat(), "expires": expiry.isoformat(),
        "previousExpires": refresh.previous.isoformat() if refresh.previous else None,
        "profileUUID": profile["UUID"], "codesignVerified": True})
    return expiry


def device_result(run, label, device, action, *options):
    output = run / f"{label}.json"
    command(["/usr/bin/xcrun", "devicectl", "device", *action, "--device", device,
             "--timeout", "90", "--json-output", str(output), *options], timeout=105)
    return json.loads(output.read_text())["result"]


def install_pair(receipt, state):
    app = Path(receipt["builtApp"])
    run = app.parents[2]
    watch = receipt["watch"]
    progress_path = run / "installation.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    targets = [("Watch", watch), ("iPhone", receipt)]
    # Check both before starting either transfer. The phone also embeds the Watch app.
    for name, target in targets:
        try:
            lock = device_result(run, name + "-lock", target["deviceUDID"], ["info", "lockState"])
        except RenewalError as exc:
            raise RenewalError(f"Signed packages saved. Connect both devices and run the shortcut again. {name}: {exc}") from exc
        if lock.get("passcodeRequired") is not False or lock.get("unlockedSinceBoot") is not True:
            raise RenewalError(f"Unlock the {name} and run the shortcut again to install the signed packages.")
    command(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    for name, target in targets:
        udid, bundle = target["deviceUDID"], target["bundleID"]
        package = Path(target["builtApp"])
        profile = read_profile(package / "embedded.mobileprovision")
        identity = dict(target, teamID=receipt["teamID"])
        if (not profile_matches(profile, identity) or date(profile["ExpirationDate"]) != date(target["profileExpires"])
                or date(target["profileExpires"]) <= datetime.now(UTC)):
            raise RenewalError(f"The signed {name} package does not match its build receipt.")
        def installed_url():
            result = device_result(run, name + "-apps", udid, ["info", "apps"], "--bundle-id", bundle)
            return next((a["url"] for a in result["apps"] if a["bundleIdentifier"] == bundle), None)
        def has_profile():
            result = device_result(run, name + "-profiles", udid, ["profile", "list"],
                                   "--type", "provisioning", "--search", profile["UUID"])
            return any(str(p.get("uuid", "")).lower() == profile["UUID"].lower()
                       for p in result["provisioningProfiles"])
        before = installed_url()
        entry = progress.setdefault(name, {"before": before})
        if not (before and (before == entry.get("verifiedURL") or before != entry["before"]) and has_profile()):
            entry["before"] = before
            save_json(progress_path, progress)
            result = device_result(run, name + "-install", udid, ["install", "app"], str(package))
            path = next((a["installationURL"] for a in result["installedApplications"] if a["bundleID"] == bundle), None)
            if not path or installed_url() != path or not has_profile():
                raise RenewalError(f"The {name} installation has not been verified. Run the shortcut again to check it.")
            before = path
        entry["verifiedURL"] = before
        save_json(progress_path, progress)
        print(f"{name} installation verified.", flush=True)
    save_json(state / "last-install.json", {"commit": receipt["commit"], "builtApp": str(app),
              "iPhoneExpires": receipt["profileExpires"], "watchExpires": watch["profileExpires"]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Read-only GitHub and Mac readiness check (default)")
    modes.add_argument("--build-only", action="store_true", help="Build and validate signing without installing")
    modes.add_argument("--renew", action="store_true", help="Renew and build a signed package; installation remains manual")
    modes.add_argument("--shortcut", action="store_true", help="Renew signing and install on the configured device pair")
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
            if args.renew or args.build_only or args.shortcut:
                recover_interrupted(state)
            sha = github_revision(config)
            print(f"GitHub verified: {config['branch']} @ {sha}", flush=True)
            renewal = Renewal(config, run)
            if not (args.renew or args.build_only or args.shortcut):
                renewal.preflight()
                print("Ready. No signing, installation, or app launch was performed.")
                return 0
            renewal.preflight()
            receipt_path = state / "last-build.json"
            previous = config.get("baselineProfileExpires")
            watch_previous = None
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if any(receipt.get(key) != config[key] for key in ("bundleID", "teamID", "deviceUDID")):
                    raise RenewalError("The previous build receipt belongs to a different app or device.")
                previous = receipt["profileExpires"]
                old_watch = receipt.get("watch", {})
                if renewal.watch and old_watch.get("deviceUDID") == renewal.watch["deviceUDID"]:
                    watch_previous = old_watch["profileExpires"]
                    if (args.shortcut and receipt.get("commit") == sha and
                            min(date(previous), date(watch_previous)) >= datetime.now(UTC) + timedelta(days=6)
                            and Path(receipt["builtApp"]).is_dir() and Path(old_watch["builtApp"]).is_dir()):
                        print("Using verified signed packages from the last build.", flush=True)
                        install_pair(receipt, state)
                        print(f"iPhone signing expires: {date(previous).astimezone():%Y-%m-%d %H:%M %Z}\n"
                              f"Apple Watch signing expires: {date(watch_previous).astimezone():%Y-%m-%d %H:%M %Z}")
                        return 0
            print("Refreshing signing through Xcode Build and verifying the new expiration...", flush=True)
            app, expiry, watch = renewal.build(sha, previous, watch_previous)
            details = {"commit": sha, "branch": config["branch"], "profileExpires": expiry.isoformat(),
                       "bundleID": config["bundleID"], "teamID": config["teamID"],
                       "deviceUDID": config["deviceUDID"], "builtApp": str(app),
                       "builtAt": datetime.now(UTC).isoformat()}
            if watch:
                details["watch"] = watch
            save_json(run / "build-receipt.json", details)
            save_json(receipt_path, details)
            print(f"iPhone signing expires: {expiry.astimezone():%Y-%m-%d %H:%M %Z}")
            if watch:
                print(f"Apple Watch signing expires: {date(watch['profileExpires']).astimezone():%Y-%m-%d %H:%M %Z}")
            print(f"Commit: {sha}\nSigned app: {app}\nReady for installation.")
            if args.shortcut and watch:
                install_pair(details, state)
            return 0
    except (RenewalError, OSError, ValueError, KeyError) as exc:
        print(f"Renewal stopped: {exc}", file=sys.stderr)
        if run:
            print(f"Run logs: {run}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
