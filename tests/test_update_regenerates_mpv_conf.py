"""`update` regenerates mpv.conf from the template (audit 2026-11-20, finding 3.6).

The old update kept mpv.conf verbatim, so template fixes never reached an
existing install. Personal settings live in mpv.conf.user, which is never
touched. The install-time choices are read back from the old file, and any
old line the new file lacks is listed and saved next to the backup.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import deployer
from deploy.detector import Environment

USER_LINE = "sub-delay                 = 0.2"
STALE_COND = (
    "profile-cond              = (p.path or \"\"):lower():match('anime') ~= nil"
    " or (p.path or \"\"):lower():match('cartoon') ~= nil"
)
CHOICES = {
    "anime_preset": "B",
    "scaler_tier": "quality",
    "display_mode": "vrr",
    "dither_depth": "10",
}


def _env(config_dir="", **extra):
    fields = dict(
        os="linux", distro="arch", platform_key="arch", display="wayland", gpu_vendor="nvidia"
    )
    fields.update(extra)
    return Environment(config_dir=str(config_dir), **fields)


def _render(env, profile=deployer.MPV_PROFILE_DEFAULT, choices=CHOICES):
    return deployer._render_mpv_conf_text(env, profile, choices)


def _personalized(text):
    """A rendered conf plus one hand-added line and one line from an older template."""
    lines = text.splitlines()
    lines.insert(
        lines.index(next(line for line in lines if line.startswith("volume "))) + 1, USER_LINE
    )
    cond = next(i for i, line in enumerate(lines) if "match('donghua')" in line)
    lines[cond] = STALE_COND
    return "\n".join(lines) + "\n"


class QuietDeployerTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mpv-regen-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config_dir = self.root / "mpv"
        self.config_dir.mkdir()
        self.backup_dir = self.root / "mpv.backup.test"
        self.backup_dir.mkdir()
        for patcher in (
            mock.patch.object(deployer, "_resolve_preferred_font", return_value="Tahoma"),
            mock.patch.object(deployer, "ui"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.env = _env(self.config_dir)


class RegenerateMpvConfTests(QuietDeployerTestCase):
    def write_conf(self, text):
        (self.config_dir / "mpv.conf").write_text(text, encoding="utf-8")

    def test_the_new_file_is_a_fresh_render_with_the_old_choices(self):
        self.write_conf(_personalized(_render(self.env)))
        deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir)
        new = (self.config_dir / "mpv.conf").read_text(encoding="utf-8")
        self.assertEqual(_render(self.env), new)
        self.assertIn("video-sync                = audio", new)  # VRR install stays VRR

    def test_lines_not_from_the_template_are_listed_and_saved(self):
        self.write_conf(_personalized(_render(self.env)))
        foreign, report = deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir)
        self.assertEqual([USER_LINE, STALE_COND], foreign)
        self.assertEqual(self.backup_dir / deployer.MPV_CONF_NOT_IN_TEMPLATE, report)
        saved = report.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [USER_LINE, STALE_COND], [line for line in saved if not line.startswith("#")]
        )

    def test_mpv_conf_user_is_never_touched(self):
        user = self.config_dir / "mpv.conf.user"
        user.write_bytes(b"# mine\nvolume=55\n")
        before = user.stat().st_mtime_ns
        self.write_conf(_personalized(_render(self.env)))
        deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir)
        self.assertEqual(b"# mine\nvolume=55\n", user.read_bytes())
        self.assertEqual(before, user.stat().st_mtime_ns)

    def test_a_current_file_is_left_alone_and_reports_nothing(self):
        self.write_conf(_render(self.env))
        foreign, report = deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir)
        self.assertEqual(([], None), (foreign, report))
        self.assertEqual([], list(self.backup_dir.iterdir()))

    def test_the_mpv_profile_chosen_at_install_is_kept(self):
        native = _render(self.env, profile="native")
        self.assertIn("gpu-context               = waylandvk", native)
        self.write_conf(native)
        deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir)
        self.assertEqual(native, (self.config_dir / "mpv.conf").read_text(encoding="utf-8"))

    def test_choices_are_read_back_from_the_rendered_file(self):
        for choices in (
            CHOICES,
            {
                "anime_preset": "A+A",
                "scaler_tier": "light",
                "display_mode": "fixed",
                "dither_depth": "auto",
            },
        ):
            with self.subTest(choices=choices):
                text = _render(self.env, choices=choices)
                self.assertEqual(choices, deployer._infer_mpv_conf_choices(text, self.env))

    def test_no_mpv_conf_means_nothing_to_do(self):
        self.assertIsNone(deployer._regenerate_mpv_conf(self.config_dir, self.env, self.backup_dir))
        self.assertFalse((self.config_dir / "mpv.conf").exists())


class UpdateCommandTests(QuietDeployerTestCase):
    """deployer.main(["--update", ...]) with only network, detection and asset swap mocked."""

    def setUp(self):
        super().setUp()
        self.old_conf = _personalized(_render(self.env))
        (self.config_dir / "mpv.conf").write_text(self.old_conf, encoding="utf-8")
        (self.config_dir / "mpv.conf.user").write_text("volume=55\n", encoding="utf-8")
        results = [{"name": s["name"], "status": "ok"} for s in deployer.SCRIPTS]
        results.append({"name": deployer.SHADERS["name"], "status": "ok"})

        def update_assets(config_dir, staging, repo_dir, lockfile, prepare_hook=None):
            shutil.copytree(config_dir, self.backup_dir, dirs_exist_ok=True)
            return str(self.backup_dir)

        self.audit_log = mock.MagicMock()
        for patcher in (
            mock.patch.object(deployer, "detect", return_value=self.env),
            mock.patch.object(deployer, "fetch_all", return_value=(results, {})),
            mock.patch.object(deployer.tx, "update_assets", side_effect=update_assets),
            mock.patch.object(deployer, "_audit_log_for", return_value=self.audit_log),
            mock.patch.object(deployer, "display_plan"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def conf(self):
        return (self.config_dir / "mpv.conf").read_text(encoding="utf-8")

    def test_update_backs_up_regenerates_and_reports(self):
        self.assertEqual(0, deployer.main(["--update", "--yes"]))
        self.assertEqual(_render(self.env), self.conf())
        self.assertEqual(self.old_conf, (self.backup_dir / "mpv.conf").read_text(encoding="utf-8"))
        self.assertTrue((self.backup_dir / deployer.MPV_CONF_NOT_IN_TEMPLATE).is_file())
        warned = " ".join(str(c.args[0]) for c in deployer.ui.warn.call_args_list)
        self.assertIn("2 line(s) of your previous mpv.conf", warned)
        shown = [str(c.args[0]).strip() for c in deployer.ui.info.call_args_list]
        self.assertIn(USER_LINE, shown)
        self.assertEqual(
            "volume=55\n", (self.config_dir / "mpv.conf.user").read_text(encoding="utf-8")
        )

    def test_keep_conf_leaves_mpv_conf_exactly_as_it_was(self):
        self.assertEqual(0, deployer.main(["--update", "--yes", "--keep-conf"]))
        self.assertEqual(self.old_conf, self.conf())
        self.assertFalse((self.backup_dir / deployer.MPV_CONF_NOT_IN_TEMPLATE).exists())

    def test_the_plan_says_what_happens_to_mpv_conf(self):
        for argv, action, detail in (
            (["--update", "--dry-run"], "deploy", "regenerate from template"),
            (["--update", "--dry-run", "--keep-conf"], "skip", "--keep-conf"),
        ):
            with self.subTest(argv=argv):
                deployer.display_plan.reset_mock()
                self.assertEqual(0, deployer.main(argv))
                plan = deployer.display_plan.call_args.args[0]
                entry = next(e for e in plan if e.target.endswith("mpv.conf"))
                self.assertEqual(action, entry.action)
                self.assertIn(detail, entry.detail)
        self.assertEqual(self.old_conf, self.conf())


if __name__ == "__main__":
    unittest.main()
