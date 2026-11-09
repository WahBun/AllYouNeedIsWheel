import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import sync_pro_xcode as sync


class ProXcodeSyncTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.git("init", "-q", "-b", sync.BRANCH)
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("remote", "add", "origin", "https://github.com/" + sync.REPOSITORY)
        project = self.root / "ios/Wheel.xcodeproj"
        project.mkdir(parents=True)
        (project / "project.pbxproj").write_text("project")
        (self.root / "catalog").write_text("original")
        (self.root / "source").write_text("old")
        (self.root / ".gitignore").write_text("local.settings\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.old = self.git("rev-parse", "HEAD")
        self.git("switch", "-qc", "fixture-merged")
        (self.root / "source").write_text("merged")
        (self.root / "local.settings").write_text("official")
        self.git("add", "-f", "local.settings", "source")
        self.git("commit", "-qm", "merged PR")
        self.tip = self.git("rev-parse", "HEAD")
        self.git("switch", "-q", sync.BRANCH)
        self.pr = {"merged_at": "2026-11-09", "merge_commit_sha": self.tip, "number": 15,
                   "base": {"ref": sync.BRANCH, "repo": {"full_name": sync.REPOSITORY}}}
        self.github = self.enter_patch("github", side_effect=lambda path:
                                      [self.pr] if path.endswith("/pulls") else {"object":{"sha":self.tip}})
        self.build = self.enter_patch("build_active", return_value=False)

    def enter_patch(self, name, **kwargs):
        p = patch.object(sync, name, **kwargs)
        self.addCleanup(p.stop)
        return p.start()

    def git(self, *args):
        return subprocess.check_output(["/usr/bin/git", *args], cwd=self.root, text=True).strip()

    def test_merge_advances_and_preserves_staged_and_unstaged_catalog(self):
        catalog = self.root / "catalog"
        catalog.write_text("staged")
        self.git("add", "catalog")
        catalog.write_text("more local edits")
        result = sync.sync(self.root)
        self.assertEqual(result, {"state":"updated", "head":self.tip, "pr":15})
        self.assertEqual(self.git("show", ":catalog"), "staged")
        self.assertEqual(catalog.read_text(), "more local edits")
        self.assertEqual((self.root/"source").read_text(), "merged")
        self.assertEqual(sync.sync(self.root)["state"], "current")

    def test_overlapping_and_ignored_changes_are_preserved(self):
        source = self.root / "source"
        source.write_text("my edits")
        self.assertEqual(sync.sync(self.root)["state"], "blocked")
        self.assertEqual(source.read_text(), "my edits")
        self.git("restore", "source")
        ignored = self.root/"local.settings"
        ignored.write_text("private")
        self.assertEqual(sync.sync(self.root)["state"], "blocked")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(ignored.read_text(), "private")

    def test_build_git_operation_and_unmerged_head_defer(self):
        self.build.return_value = True
        self.assertEqual(sync.sync(self.root)["state"], "busy")
        self.build.return_value = False
        marker = self.root/".git"/"rebase-merge"
        marker.mkdir()
        self.assertEqual(sync.sync(self.root)["state"], "busy")
        marker.rmdir()
        self.pr["merged_at"] = None
        self.assertEqual(sync.sync(self.root)["state"], "waiting")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)

    def test_divergence_and_other_branch_do_not_move(self):
        self.git("commit", "--allow-empty", "-qm", "local only")
        own = self.git("rev-parse", "HEAD")
        self.assertEqual(sync.sync(self.root)["state"], "blocked")
        self.assertEqual(self.git("rev-parse", "HEAD"), own)
        self.git("switch", "-qc", "feature")
        self.github.reset_mock()
        self.assertEqual(sync.sync(self.root)["state"], "paused")
        self.github.assert_not_called()
