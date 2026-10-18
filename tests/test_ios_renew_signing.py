"""Renewal guards use synthetic identities and never contact an iPhone or Apple."""
from datetime import datetime, timedelta, timezone
import importlib.util
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
                        "ExpirationDate": self.now + timedelta(days=7)}

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
        for hours in (-1, 24, 47):
            with self.subTest(hours=hours), self.assertRaisesRegex(renew.RenewalError, "48 hours"):
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

    def test_running_detection_uses_exact_installed_app_path(self):
        app = {"url": "file:///Applications/UUID/Wheel.app/"}
        self.assertTrue(renew.app_running([{"executable": app["url"] + "Wheel"}], app))
        self.assertFalse(renew.app_running([{"executable": "file:///Applications/OTHER/Wheel.app/Wheel"}], app))

    def test_install_rechecks_phone_and_does_not_retry_unknown_outcome(self):
        instance = renew.Renewal(self.config, Path("/unused"))
        with patch.object(instance, "preflight"), patch.object(instance, "device", side_effect=renew.RenewalError("timeout")) as device:
            with self.assertRaisesRegex(renew.RenewalError, "timeout"):
                instance.install(Path("Wheel.app"), {})
            self.assertEqual(device.call_count, 1)
        with patch.object(instance, "preflight", side_effect=renew.RenewalError("Wheel is running")), patch.object(instance, "device") as device:
            with self.assertRaises(renew.RenewalError):
                instance.install(Path("Wheel.app"), {})
            device.assert_not_called()

    def test_install_verifies_read_back_version(self):
        instance = renew.Renewal(self.config, Path("/unused"))
        info = {"CFBundleVersion": "2", "CFBundleShortVersionString": "0.2"}
        with patch.object(instance, "preflight"), patch.object(instance, "device"), patch.object(instance, "installed", return_value={"bundleVersion": "1", "version": "0.2"}):
            with self.assertRaisesRegex(renew.RenewalError, "could not be confirmed"):
                instance.install(Path("Wheel.app"), info)

    def test_dirty_checkout_or_different_remote_commit_is_rejected(self):
        with patch.object(renew, "command", return_value=" M file"):
            with self.assertRaisesRegex(renew.RenewalError, "uncommitted"):
                renew.github_revision(self.config)
        with patch.object(renew, "command", side_effect=["", "test", self.config["repository"], "local", "remote refs/heads/test"]):
            with self.assertRaisesRegex(renew.RenewalError, "differs"):
                renew.github_revision(self.config)

    def test_check_and_build_only_never_install(self):
        import json
        for mode in ("--check", "--build-only"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "ios").mkdir()
                (root / "ios/Renew.local.json").write_text(json.dumps(self.config))
                with patch.object(renew, "ROOT", root), patch.object(renew, "github_revision", return_value="sha"), patch.object(renew.Renewal, "preflight"), patch.object(renew.Renewal, "build", return_value=(Path("Wheel.app"), self.profile["ExpirationDate"], {})), patch.object(renew.Renewal, "install") as install:
                    self.assertEqual(renew.main([mode]), 0)
                    install.assert_not_called()
                self.assertFalse((root / "ios/.renewal/last-install.json").exists())


if __name__ == "__main__":
    unittest.main()
