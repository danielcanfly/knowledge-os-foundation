"""Native launcher safety tests. No VM secrets, provider or Docker invocation."""
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "packaging/m27_f04_owner_native_01/launch_nonprod.py"
spec = importlib.util.spec_from_file_location("m27_mount_contract", MODULE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class LaunchContractTests(unittest.TestCase):
    def test_authorized_preprovisioned_secret_only(self):
        good = Path("/tmp/m27-preapproved-nonprod-secret")
        with mock.patch.object(Path, "lstat", return_value=SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600, st_uid=65532, st_size=60)):
            app.private_file(good)

    def test_reject_unowned_or_exposed_or_short_secret(self):
        path = Path("/tmp/m27-preapproved-nonprod-secret")
        for uid, mode, size in ((1000, 0o600, 60),
                                (65532, 0o644, 60),
                                (65532, 0o600, 0),
                                (65532, 0o600, 513)):
            with mock.patch.object(Path, "lstat", return_value=SimpleNamespace(
                    st_mode=stat.S_IFREG | mode, st_uid=uid, st_size=size)):
                with self.assertRaises(app.Denied):
                    app.private_file(path)

    def test_reject_mount_injection_and_relative_path(self):
        for path in (Path("relative-key"), Path("/tmp/key,readonly=false"),
                     Path("/tmp/key" + chr(10) + "newline")):
            with self.assertRaisesRegex(app.Denied, "SECRET_PATH_NOT_APPROVED"):
                app.private_file(path)

    def test_exact_image_and_root_lock(self):
        for root, image in ((Path("/tmp/other"), app.IMAGE),
                            (app.ROOT, "m27-owner-native-app:unqualified")):
            with self.assertRaisesRegex(app.Denied,
                                        "UNEXPECTED_NONPROD_RUNTIME_ROOT_OR_IMAGE"):
                app.build_command(approved_secret=Path("/tmp/nonsecret"),
                                  root=root, image=image)

    def test_exact_mount_args_no_env_or_key_contents(self):
        def command(*args):
            if args[0] == "git":
                if args[-2:] == ("rev-parse", "HEAD"):
                    return (app.C1_HEAD if "c1-git" in args[4] else app.G01_HEAD)
                return ""
            if args[:3] == ("docker", "image", "inspect"):
                return app.IMAGE_ID
            if args[:2] == ("docker", "ps"):
                return ""
            raise AssertionError("Unexpected command")
        with mock.patch.object(app, "private_file"), \
             mock.patch.object(app, "executable", side_effect=command), \
             mock.patch.object(Path, "is_dir", return_value=True), \
             mock.patch.object(Path, "is_symlink", return_value=False), \
             mock.patch.object(Path, "stat", return_value=SimpleNamespace(
                 st_uid=app.RUN_UID, st_mode=stat.S_IFDIR | 0o700)):
            cmd = app.build_command(
                approved_secret=Path("/runtime/provisioned/minimax-owner-key"))
        joined = " ".join(cmd)
        self.assertIn("readonly", joined)
        self.assertIn("/run/secrets/minimax_api_key", joined)
        self.assertIn(app.IMAGE, joined)
        self.assertIn("--pids-limit 64", joined)
        self.assertIn("--network bridge", joined)
        self.assertIn("--cap-drop ALL", joined)
        self.assertNotIn("--env", cmd)
        self.assertNotIn("--env-file", cmd)
        self.assertNotIn("TESTONLY", joined)
        self.assertTrue(joined.endswith("--provider-secret /run/secrets/minimax_api_key"))


if __name__ == "__main__":
    unittest.main()
