"""Unit tests for src/bin/catstar-backup.sh."""

import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_SCRIPT = REPO_ROOT / "src" / "bin" / "catstar-backup.sh"


class TestCatstarBackupScript(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            BACKUP_SCRIPT.exists(), f"Backup script not found at {BACKUP_SCRIPT}"
        )

    def run_backup_script(self, env_override: dict):
        env = os.environ.copy()
        env.update(env_override)
        result = subprocess.run(
            ["bash", str(BACKUP_SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result

    def test_backup_success_logs_preserved(self):
        env = {
            "BACKUP_TEST": "0",
            "NOTIFY_SEND_SUMMARY": "1",
            "NOTIFY_DEBUG": "1",
            "MACHINE_NAME": "TestHost",
        }
        res = self.run_backup_script(env)
        self.assertEqual(
            res.returncode, 0, f"Script failed with output:\n{res.stdout}\n{res.stderr}"
        )
        self.assertIn("TestHost 备份完成✅", res.stdout)
        self.assertIn("Catstar - 喵星备份日志", res.stdout)
        self.assertIn("开始备份时间", res.stdout)
        self.assertIn("结束备份时间", res.stdout)

    def test_backup_failure_logs_preserved(self):
        env = {
            "BACKUP_TEST": "42",
            "NOTIFY_DEBUG": "1",
            "MACHINE_NAME": "TestHost",
        }
        res = self.run_backup_script(env)
        self.assertEqual(
            res.returncode, 0
        )  # Script handles failure and sends notification
        self.assertIn("TestHost 备份失败❌！", res.stdout)
        self.assertIn("错误码：42", res.stdout)
        self.assertIn("Catstar - 喵星备份日志", res.stdout)
        self.assertIn("开始备份：测试，只输出消息", res.stdout)
        self.assertNotIn("结束备份时间", res.stdout)

    def test_verbose_logging_output(self):
        env = {
            "BACKUP_TEST": "0",
            "NOTIFY_SEND_VERBOSE": "1",
            "NOTIFY_DEBUG": "1",
            "MACHINE_NAME": "TestHost",
        }
        res = self.run_backup_script(env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("*** TestHost 开始备份时间:", res.stdout)
        self.assertIn("发送通知：TestHost 开始备份时间:", res.stdout)


if __name__ == "__main__":
    unittest.main()
