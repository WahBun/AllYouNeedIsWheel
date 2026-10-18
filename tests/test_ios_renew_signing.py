"""Renewal guards use synthetic identities and never contact an iPhone or Apple."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
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
                           deviceIdentifier="PHONE-ID", branch="test", repository="https://github.com/test/wheel")
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

    def test_no_fallback_to_another_device(self):
        device = {"identifier": "PHONE-ID", "properties": {
            "hardware": {"deviceType": "iPhone", "udid": "PHONE-UDID", "reality": "physical"},
            "connection": {"pairingState": "paired"}}}
        self.assertEqual(renew.select_device([device], self.config), device)
        with self.assertRaises(renew.RenewalError):
            renew.select_device([device], dict(self.config, deviceIdentifier="OTHER"))
        device["properties"]["hardware"]["reality"] = "simulated"
        with self.assertRaises(renew.RenewalError):
            renew.select_device([device], self.config)

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
