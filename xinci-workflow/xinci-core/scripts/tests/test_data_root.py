"""数据区定位的回归测试。

核心要守住的一条:**没有静默回退**。2026-08-24 之前 DEFAULT_DATA_ROOT 会在环境变量
缺失时回退到同级 keywords-macdownds,后果是换机器/换用户第一次跑时,脚本会在一个他
从没同意过的位置直接建账本且不报错。下面的测试就是拦住这条回退被重新引入。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_root  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]


class DataRootResolveTest(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop(data_root.ENV_VAR, None)
        self._cfg = data_root.config_path()
        self._backup = self._cfg.read_text(encoding="utf-8") if self._cfg.is_file() else None
        if self._cfg.is_file():
            self._cfg.unlink()

    def tearDown(self):
        if self._env is not None:
            os.environ[data_root.ENV_VAR] = self._env
        else:
            os.environ.pop(data_root.ENV_VAR, None)
        if self._backup is not None:
            self._cfg.write_text(self._backup, encoding="utf-8")
        elif self._cfg.is_file():
            self._cfg.unlink()

    def test_no_silent_fallback_when_nothing_configured(self):
        """三条来源全空时必须抛,不许猜出一个路径来。"""
        with self.assertRaises(data_root.DataRootNotConfigured):
            data_root.resolve()

    def test_refusal_message_tells_you_to_ask_the_user(self):
        """异常文案必须把「先问用户」和可照做的下一步写进去——
        它是执行者唯一会读到的东西。"""
        try:
            data_root.resolve()
        except data_root.DataRootNotConfigured as e:
            msg = str(e)
        self.assertIn("先问用户", msg)
        self.assertIn("init_workspace.py", msg)
        self.assertIn(data_root.ENV_VAR, msg)

    def test_precedence_explicit_over_env_over_config(self):
        # save() 会 resolve(),macOS 上 /tmp 是 /private/tmp 的符号链接,
        # 所以拿 resolve 后的值做断言,别写死字面量。
        saved = Path("/tmp/xinci-from-config").resolve()
        data_root.save(saved)
        self.assertEqual(data_root.resolve(), saved)

        os.environ[data_root.ENV_VAR] = "/tmp/xinci-from-env"
        self.assertEqual(data_root.resolve(), Path("/tmp/xinci-from-env"))

        self.assertEqual(data_root.resolve("/tmp/xinci-explicit"),
                         Path("/tmp/xinci-explicit"))

    def test_empty_env_var_does_not_count_as_configured(self):
        """空字符串是常见的误设,不能当成已配置——否则会退化成写到 cwd。"""
        os.environ[data_root.ENV_VAR] = ""
        with self.assertRaises(data_root.DataRootNotConfigured):
            data_root.resolve()

    def test_blank_config_file_does_not_count_as_configured(self):
        data_root.config_path().write_text("  \n", encoding="utf-8")
        with self.assertRaises(data_root.DataRootNotConfigured):
            data_root.resolve()

    def test_save_records_absolute_path(self):
        with tempfile.TemporaryDirectory() as d:
            data_root.save(Path(d) / "数据" / "新词工作流")
            got = data_root.read_config()
        self.assertTrue(got.is_absolute())


class CliRefusalTest(unittest.TestCase):
    """六个入口脚本在未配置时都必须以 2 退出并给出指引,
    不许其中任何一个漏掉这道检查。"""

    ENTRIES = [
        ("data_root.py", []),
        ("validate_ledger.py", []),
        ("report_status.py", []),
        ("init_workspace.py", []),
        ("screen_index.py", ["stats"]),
        ("run_controller.py", ["list"]),
        ("registrar.py", ["register", "--slug", "x", "--term", "x",
                          "--source-url", "https://e.com", "--task", "t",
                          "--evidence", "e", "--by", "user"]),
    ]

    def setUp(self):
        self._cfg = data_root.config_path()
        self._backup = self._cfg.read_text(encoding="utf-8") if self._cfg.is_file() else None
        if self._cfg.is_file():
            self._cfg.unlink()

    def tearDown(self):
        if self._backup is not None:
            self._cfg.write_text(self._backup, encoding="utf-8")
        elif self._cfg.is_file():
            self._cfg.unlink()

    def test_every_entry_point_refuses(self):
        env = {k: v for k, v in os.environ.items() if k != data_root.ENV_VAR}
        for script, args in self.ENTRIES:
            with self.subTest(script=script):
                r = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                                   capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 2, f"{script} 未拒绝: {r.stdout}{r.stderr}")
                self.assertIn("先问用户", r.stderr)

    def test_data_root_cli_prints_resolved_path(self):
        """data_root.py 的 CLI 形态供命令模板以 $(...) 取路径:已配置时只打印路径本身。"""
        env = {k: v for k, v in os.environ.items() if k != data_root.ENV_VAR}
        r = subprocess.run([sys.executable, str(SCRIPTS / "data_root.py"),
                            "--data-root", "/tmp/某数据区"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "/tmp/某数据区")

    def test_init_workspace_does_not_create_anything_when_unconfigured(self):
        """最关键的一条:拒绝时不能已经把目录建出来了。"""
        env = {k: v for k, v in os.environ.items() if k != data_root.ENV_VAR}
        with tempfile.TemporaryDirectory() as d:
            probe = Path(d) / "不该被创建"
            r = subprocess.run([sys.executable, str(SCRIPTS / "init_workspace.py")],
                               capture_output=True, text=True, env=env, cwd=d)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(probe.exists())
            self.assertEqual(list(Path(d).iterdir()), [])


class InitWorkspaceSavesChoiceTest(unittest.TestCase):
    """显式给了 --data-root 才落盘:那一次调用就是用户做出决定的时刻。"""

    def setUp(self):
        self._cfg = data_root.config_path()
        self._backup = self._cfg.read_text(encoding="utf-8") if self._cfg.is_file() else None
        if self._cfg.is_file():
            self._cfg.unlink()

    def tearDown(self):
        if self._backup is not None:
            self._cfg.write_text(self._backup, encoding="utf-8")
        elif self._cfg.is_file():
            self._cfg.unlink()

    def _run(self, extra, d):
        env = {k: v for k, v in os.environ.items() if k != data_root.ENV_VAR}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "init_workspace.py"),
             "--data-root", str(d), *extra],
            capture_output=True, text=True, env=env)

    def test_explicit_root_is_saved_and_workspace_created(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "数据" / "新词工作流"
            r = self._run([], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(data_root.read_config(), root.resolve())
            self.assertTrue((root / "账本" / "候选账本.json").is_file())
            self.assertTrue((root / "淘汰方向.jsonl").is_file())

    def test_no_save_creates_workspace_without_recording_choice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "数据" / "新词工作流"
            r = self._run(["--no-save"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((root / "账本" / "候选账本.json").is_file())
            self.assertIsNone(data_root.read_config())


if __name__ == "__main__":
    unittest.main()
