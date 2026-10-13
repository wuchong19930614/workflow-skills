# 数据区解析:显式 > 环境变量 > 仓库配置 > 拒绝。不猜位置。
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_root as D
import init_workspace


class DataRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cfg = mock.patch.object(D, "REPO_ROOT", self.tmp)
        self._cfg.start()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(D.ENV_VAR, None)

    def tearDown(self):
        self._env.stop()
        self._cfg.stop()
        self._tmp.cleanup()

    def test_explicit_wins(self):
        os.environ[D.ENV_VAR] = "/env/root"
        D.save("/cfg/root")
        self.assertEqual(D.resolve("/explicit"), Path("/explicit"))

    def test_env_over_config(self):
        os.environ[D.ENV_VAR] = "/env/root"
        D.save("/cfg/root")
        self.assertEqual(D.resolve(), Path("/env/root"))

    def test_config_when_nothing_else(self):
        D.save(self.tmp / "data")
        self.assertEqual(D.resolve(), (self.tmp / "data").resolve())

    def test_refuses_to_guess(self):
        with self.assertRaises(D.DataRootNotConfigured):
            D.resolve()

    def test_cli_exit_code_2_when_unconfigured(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            D.resolve_or_exit(None)
        self.assertEqual(cm.exception.code, 2)

    def test_init_no_save_leaves_pointer_alone(self):
        target = self.tmp / "ws"
        with contextlib.redirect_stdout(io.StringIO()):
            init_workspace.main(["--data-root", str(target), "--no-save"])
        self.assertFalse(D.config_path().exists())
        self.assertTrue((target / "账本" / "方向账本.json").is_file())

    def test_init_is_idempotent_and_creates_all(self):
        target = self.tmp / "ws"
        first = init_workspace.init_workspace(target)
        self.assertEqual(init_workspace.init_workspace(target), [])
        for sub in init_workspace.SUBDIRS:
            self.assertTrue((target / sub).is_dir(), sub)
        self.assertTrue(any(p.endswith("淘汰索引/域名.json") for p in first))


if __name__ == "__main__":
    unittest.main()
