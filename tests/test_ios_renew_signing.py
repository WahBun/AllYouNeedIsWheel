"""Renewal guards use synthetic identities and never contact an iPhone or Apple."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
import shutil
import subprocess
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("renew", Path(__file__).parents[1] / "ios/renew_signing.py")
renew = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renew)


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(teamID="TESTTEAM", bundleID="test.wheel", deviceUDID="PHONE-UDID",
                           branch="test", repository="https://github.com/test/wheel")
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.profile = {"TeamIdentifier": ["TESTTEAM"], "ProvisionedDevices": ["PHONE-UDID"],
                        "Entitlements": {"application-identifier": "TESTTEAM.test.wheel"},
                        "ExpirationDate": self.now + timedelta(days=7), "CreationDate": self.now}

    def test_renewed_profile_matches_identity_and_extends_expiry(self):
        self.assertEqual(renew.validate_profile(self.profile, self.config, self.now + timedelta(days=1), self.now),
                         self.now + timedelta(days=7))

    def test_wrong_team_bundle_or_device_stops_renewal(self):
        for key, value in (("teamID", "OTHER"), ("bundleID", "test.other"), ("deviceUDID", "OTHER")):
            with self.subTest(key=key), self.assertRaises(renew.RenewalError):
                renew.validate_profile(self.profile, dict(self.config, **{key: value}), now=self.now)

    def test_old_short_lived_or_expired_profile_is_not_renewal(self):
        with self.assertRaisesRegex(renew.RenewalError, "did not extend"):
            renew.validate_profile(self.profile, self.config, self.profile["ExpirationDate"], self.now)
        for hours in (-1, 24, 143):
            with self.subTest(hours=hours), self.assertRaisesRegex(renew.RenewalError, "six days"):
                renew.validate_profile(dict(self.profile, ExpirationDate=self.now + timedelta(hours=hours)),
                                       self.config, now=self.now)

    def test_mac_preflight_does_not_query_a_connected_phone(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "ios").mkdir()
            (root / "ios/Signing.local.xcconfig").write_text("// local test signing")
            original_stat = Path.stat
            def host_stat(path, *args, **kwargs):
                return SimpleNamespace(st_uid=501) if path == Path("/dev/console") else original_stat(path, *args, **kwargs)
            with patch.object(Path, "stat", host_stat), patch.object(renew, "ROOT", root), patch.object(renew.os, "getuid", return_value=501), patch.object(renew, "command") as command:
                renew.Renewal(self.config, root).preflight()
                command.assert_not_called()
                with self.assertRaisesRegex(renew.RenewalError, "incomplete"):
                    renew.Renewal(dict(self.config, deviceUDID=""), root).preflight()
            with patch.object(Path, "stat", host_stat), patch.object(renew.os, "getuid", return_value=-1):
                with self.assertRaisesRegex(renew.RenewalError, "Mac desktop"):
                    renew.Renewal(self.config, root).preflight()

    @unittest.skipUnless(Path("/bin/zsh").is_file(), "The SSH entry requires macOS zsh")
    def test_ssh_entry_allows_only_check_and_renew(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entry = root / "renew_signing_ssh.sh"
            shutil.copyfile(Path(__file__).parents[1] / "ios/renew_signing_ssh.sh", entry)
            (root / "renew_signing.py").write_text("import sys; print(sys.argv[1:])")
            for original, mode in (("check", "--check"), ("renew", "--build-only")):
                result = subprocess.run(["/bin/zsh", str(entry)], capture_output=True, text=True,
                                        env=dict(os.environ, SSH_ORIGINAL_COMMAND=original))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), repr([mode]))
            marker = root / "injected"
            for original in ("", " check", "renew now", "check\nrenew", f"check; touch {marker}", f"$(touch {marker})"):
                with self.subTest(original=original):
                    result = subprocess.run(["/bin/zsh", str(entry)], capture_output=True, text=True,
                                            env=dict(os.environ, SSH_ORIGINAL_COMMAND=original))
                    self.assertEqual(result.returncode, 64)
            self.assertFalse(marker.exists())

    def test_cached_profile_must_have_been_issued_during_this_run(self):
        with self.assertRaisesRegex(renew.RenewalError, "fresh"):
            renew.validate_profile(dict(self.profile, CreationDate=self.now - timedelta(hours=1)),
                                   self.config, now=self.now, started=self.now)

    def test_profile_refresh_is_scoped_and_failure_restores_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache, run = root / "cache", root / "run"
            cache.mkdir(); run.mkdir()
            original, other = cache / "wheel.mobileprovision", cache / "other.mobileprovision"
            original.write_bytes(b"original"); other.write_bytes(b"other")
            def profile(path):
                return self.profile if path == original else dict(self.profile, TeamIdentifier=["OTHER"])
            with patch.object(renew, "read_profile", side_effect=profile):
                with self.assertRaisesRegex(renew.RenewalError, "build failed"):
                    with renew.ProfileRefresh(self.config, run, directories=[cache]) as refresh:
                        self.assertEqual(refresh.previous, self.profile["ExpirationDate"])
                        self.assertFalse(original.exists())
                        self.assertEqual(other.read_bytes(), b"other")
                        raise renew.RenewalError("build failed")
            self.assertEqual(original.read_bytes(), b"original")
            self.assertEqual(json.loads((run / "profile-refresh.json").read_text())["status"], "restored")

    def test_success_keeps_new_profile_and_does_not_restore_old_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache, run = root / "cache", root / "run"
            cache.mkdir(); run.mkdir()
            original = cache / "wheel.mobileprovision"
            original.write_bytes(b"original")
            with patch.object(renew, "read_profile", return_value=self.profile):
                with renew.ProfileRefresh(self.config, run, directories=[cache]):
                    (cache / "new.mobileprovision").write_bytes(b"new")
            self.assertFalse(original.exists())
            self.assertEqual((cache / "new.mobileprovision").read_bytes(), b"new")
            self.assertEqual(json.loads((run / "profile-refresh.json").read_text())["status"], "completed")

    def test_interrupted_run_restores_profile_and_stops_before_another_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache, run = root / "cache", root / "run"
            cache.mkdir(); run.mkdir()
            original = cache / "wheel.mobileprovision"
            original.write_bytes(b"original")
            with patch.object(renew, "read_profile", return_value=self.profile):
                renew.ProfileRefresh(self.config, run, directories=[cache]).__enter__()
            with self.assertRaisesRegex(renew.RenewalError, "interrupted"):
                renew.recover_interrupted(root)
            self.assertEqual(original.read_bytes(), b"original")

    def test_build_waits_for_a_genuinely_new_cached_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "profile.mobileprovision").write_bytes(b"profile")
            refresh = renew.ProfileRefresh(self.config, root, self.now, directories=[root])
            old = dict(self.profile, ExpirationDate=self.now)
            with patch.object(renew, "read_profile", side_effect=[old, self.profile]) as read, patch.object(renew.time, "sleep"), patch.object(renew, "datetime") as clock:
                clock.now.return_value = self.now
                renew.wait_for_fresh_profile(refresh, self.now)
                self.assertEqual(read.call_count, 2)
            with self.assertRaisesRegex(renew.RenewalError, "no build was started"):
                renew.wait_for_fresh_profile(refresh, self.now, timeout=0)

    def test_dirty_checkout_or_different_remote_commit_is_rejected(self):
        with patch.object(renew, "command", return_value=" M file"):
            with self.assertRaisesRegex(renew.RenewalError, "uncommitted"):
                renew.github_revision(self.config)
        with patch.object(renew, "command", side_effect=["", "test", self.config["repository"], "local", "remote refs/heads/test"]):
            with self.assertRaisesRegex(renew.RenewalError, "differs"):
                renew.github_revision(self.config)

    def test_all_modes_produce_only_a_local_build_receipt(self):
        for mode in ("--check", "--build-only", "--renew"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "ios").mkdir()
                (root / "ios/Renew.local.json").write_text(json.dumps(self.config))
                with patch.object(renew, "ROOT", root), patch.object(renew, "github_revision", return_value="sha"), patch.object(renew.Renewal, "preflight"), patch.object(renew.Renewal, "build", return_value=(Path("Wheel.app"), self.profile["ExpirationDate"], {})) as build:
                    self.assertEqual(renew.main([mode]), 0)
                    self.assertEqual(build.call_count, 0 if mode == "--check" else 1)
                self.assertFalse((root / "ios/.renewal/last-install.json").exists())


if __name__ == "__main__":
    unittest.main()
