# 数据区解析:显式 > 环境变量 > 仓库配置 > 拒绝。不猜位置。
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_root as D


class DataRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cfg_patch = mock.patch.object(D, "REPO_ROOT", self.tmp)
        self._cfg_patch.start()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(D.ENV_VAR, None)

    def tearDown(self):
        self._env.stop()
        self._cfg_patch.stop()
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
        with self.assertRaises(SystemExit) as cm:
            D.resolve_or_exit(None)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
