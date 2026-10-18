#!/usr/bin/env python3
"""User-triggered Xcode signing renewal. Default mode performs read-only checks."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

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
    rows = git("ls-remote", "--exit-code", "origin", "refs/heads/" + branch).split()
    if not rows or rows[0] != sha:
        raise RenewalError("Local HEAD differs from GitHub. Review and synchronize this branch first.")
    return sha


def select_device(devices, config):
    found = [d for d in devices if d.get("identifier") == config["deviceIdentifier"]]
    if len(found) != 1:
        raise RenewalError("The configured iPhone is unavailable. Connect it to this Mac and unlock it.")
    device = found[0]
    properties = device.get("properties", {})
    hardware = properties.get("hardware", device.get("hardwareProperties", {}))
    connection = properties.get("connection", device.get("connectionProperties", {}))
    if (hardware.get("udid") != config["deviceUDID"]
            or hardware.get("deviceType", "").lower() != "iphone"
            or hardware.get("reality", "physical") != "physical"
            or connection.get("pairingState") != "paired"):
        raise RenewalError("Device identity or pairing does not match the configured physical iPhone.")
    return device


def app_running(processes, installed):
    app_path = unquote(urlparse(installed["url"]).path).rstrip("/") + "/"
    return any(unquote(urlparse(p.get("executable", "")).path).startswith(app_path)
               for p in processes)


def validate_profile(profile, config, previous_expiry=None, now=None):
    now = now or datetime.now(UTC)
    entitlements = profile.get("Entitlements", {})
    if (profile.get("TeamIdentifier") != [config["teamID"]]
            or entitlements.get("application-identifier") != config["teamID"] + "." + config["bundleID"]
            or config["deviceUDID"] not in profile.get("ProvisionedDevices", [])):
        raise RenewalError("The signed profile does not match the expected team, app and iPhone.")
    expiry = date(profile["ExpirationDate"])
    expiry_text = expiry.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if expiry < now + timedelta(hours=48):
        raise RenewalError("Xcode did not produce a profile with at least 48 hours remaining. "
                           f"Built profile expires: {expiry_text}. No app was installed. "
                           "Try closer to expiry or open Xcode Signing & Capabilities to refresh signing.")
    if previous_expiry and expiry <= date(previous_expiry):
        raise RenewalError("Apple reused the existing profile; its expiration did not extend. "
                           f"Built profile expires: {expiry_text}. No app was installed. "
                           "Try closer to expiry or refresh signing in Xcode.")
    return expiry


class Renewal:
    def __init__(self, config, run):
        self.config = config
        self.run = run
        self.counter = 0

    def device(self, *args):
        self.counter += 1
        result_path = self.run / f"device-{self.counter}.json"
        command(["/usr/bin/xcrun", "devicectl", *args, "--json-output", str(result_path),
                 "--timeout", "90"], timeout=105, log=self.run / f"device-{self.counter}.log")
        result = json.loads(result_path.read_text())
        if result.get("info", {}).get("outcome") != "success":
            raise RenewalError("The iPhone command did not confirm success. Check the run log.")
        return result["result"]

    def installed(self):
        result = self.device("device", "info", "apps", "--device", self.config["deviceIdentifier"],
                             "--bundle-id", self.config["bundleID"])
        apps = [a for a in result.get("apps", []) if a.get("bundleIdentifier") == self.config["bundleID"]]
        if len(apps) != 1 or not apps[0].get("builtByDeveloper"):
            raise RenewalError("The expected developer-installed Wheel app was not found on this iPhone.")
        return apps[0]

    def preflight(self):
        select_device(self.device("list", "devices").get("devices", []), self.config)
        lock = self.device("device", "info", "lockState", "--device", self.config["deviceIdentifier"])
        if lock.get("passcodeRequired") is not False or lock.get("unlockedSinceBoot") is not True:
            raise RenewalError("Unlock the iPhone and keep it connected while renewal runs.")
        installed = self.installed()
        processes = self.device("device", "info", "processes", "--device", self.config["deviceIdentifier"])
        if not isinstance(processes.get("runningProcesses"), list) or not installed.get("url"):
            raise RenewalError("The iPhone did not provide enough information to verify that Wheel is closed.")
        if app_running(processes["runningProcesses"], installed):
            raise RenewalError("Wheel is running on the iPhone. Close Wheel in the app switcher, then run again.")
        return installed

    def build(self, sha, previous_expiry):
        source = self.run / "source"
        source.mkdir()
        archive = self.run / "source.tar"
        command(["/usr/bin/git", "archive", "--format=tar", "--output", str(archive), sha])
        command(["/usr/bin/tar", "-xf", str(archive), "-C", str(source)])
        signing = ROOT / "ios/Signing.local.xcconfig"
        if not signing.is_file():
            raise RenewalError("Configure ios/Signing.local.xcconfig in Xcode first.")
        shutil.copyfile(signing, source / "ios/Signing.local.xcconfig")
        (source / "ios/Signing.local.xcconfig").chmod(0o600)
        derived = self.run / "DerivedData"
        command(["/usr/bin/xcodebuild", "-project", "ios/Wheel.xcodeproj", "-scheme", "Wheel",
                 "-configuration", "Debug", "-jobs", "2", "-destination", "generic/platform=iOS",
                 "-derivedDataPath", str(derived), "-allowProvisioningUpdates", "build"],
                cwd=source, timeout=1200, log=self.run / "build.log")
        app = derived / "Build/Products/Debug-iphoneos/Wheel.app"
        command(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
        profile = plistlib.loads(command(["/usr/bin/security", "cms", "-D", "-i",
                                         str(app / "embedded.mobileprovision")]).encode())
        expiry = validate_profile(profile, self.config, previous_expiry)
        info = plistlib.loads((app / "Info.plist").read_bytes())
        if info["CFBundleIdentifier"] != self.config["bundleID"]:
            raise RenewalError("The built application has a different bundle identifier.")
        return app, expiry, info

    def install(self, app, info):
        self.preflight()
        # One install request. A failed or timed-out request is never replayed.
        self.device("device", "install", "app", "--device", self.config["deviceIdentifier"], str(app))
        installed = self.installed()
        if (installed.get("bundleVersion") != str(info["CFBundleVersion"])
                or installed.get("version") != str(info["CFBundleShortVersionString"])):
            raise RenewalError("Installation returned, but the app version could not be confirmed. Check the iPhone.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Read-only GitHub and iPhone readiness check (default)")
    modes.add_argument("--build-only", action="store_true", help="Build and validate signing without installing")
    modes.add_argument("--renew", action="store_true", help="Build, validate, and install on the configured iPhone")
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
            sha = github_revision(config)
            print(f"GitHub verified: {config['branch']} @ {sha}", flush=True)
            renewal = Renewal(config, run)
            if not (args.renew or args.build_only):
                renewal.preflight()
                print("Ready. No signing, installation, or app launch was performed.")
                return 0
            if args.renew:
                renewal.preflight()
            receipt_path = state / "last-install.json"
            previous = config.get("baselineProfileExpires")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if any(receipt.get(key) != config[key] for key in ("bundleID", "teamID", "deviceUDID")):
                    raise RenewalError("The previous installation receipt belongs to a different app or device.")
                previous = receipt["profileExpires"]
            print("Building and checking the actual signing expiration...", flush=True)
            app, expiry, info = renewal.build(sha, previous)
            details = {"commit": sha, "branch": config["branch"], "profileExpires": expiry.isoformat(),
                       "bundleID": config["bundleID"], "teamID": config["teamID"],
                       "deviceUDID": config["deviceUDID"], "builtApp": str(app),
                       "builtAt": datetime.now(UTC).isoformat()}
            save_json(run / "build-receipt.json", details)
            if args.build_only:
                print(f"Build verified. No phone installation.\nSignature expires: {expiry.astimezone():%Y-%m-%d %H:%M %Z}")
                return 0
            print("Installing the verified build...", flush=True)
            renewal.install(app, info)
            details["installedAt"] = datetime.now(UTC).isoformat()
            save_json(receipt_path, details)
            save_json(run / "install-receipt.json", details)
            print(f"Wheel renewal completed.\nSignature expires: {expiry.astimezone():%Y-%m-%d %H:%M %Z}\n"
                  f"Commit: {sha}\nOpen Wheel on the iPhone when ready.")
            return 0
    except (RenewalError, OSError, ValueError, KeyError) as exc:
        print(f"Renewal stopped: {exc}", file=sys.stderr)
        if run:
            print(f"Run logs: {run}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
