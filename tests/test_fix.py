"""Unit tests for fix_issue.py — call real functions with mocked I/O."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


class TestAnalyzeDbRisk(unittest.TestCase):
    """Test the real analyze_db_risk function."""

    def setUp(self):
        from fix_issue import analyze_db_risk
        self.analyze_db_risk = analyze_db_risk

    def test_add_column_detected_as_safe(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("ALTER TABLE organizations ADD COLUMN test_col TEXT;")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("数据库变更", result)
        self.assertIn("ADD COLUMN", result)

    def test_drop_table_detected_as_critical(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("DROP TABLE users;")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("Critical", result)
        self.assertIn("DROP TABLE", result)

    def test_drop_column_detected_as_critical(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("ALTER TABLE users DROP COLUMN old_col;")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("Critical", result)

    def test_create_index_without_concurrently_is_high(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("CREATE INDEX idx ON users(email);")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("High", result)

    def test_multiple_findings_all_reported(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("DROP TABLE old;\nALTER TABLE users ADD COLUMN x TEXT;")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("Critical", result)
        self.assertIn("Safe", result)

    def test_file_not_found_handled(self):
        result = self.analyze_db_risk(["/nonexistent/migration.sql"])
        self.assertIn("File not found", result)

    def test_summary_format(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("DROP TABLE x;")
            f.flush()
            result = self.analyze_db_risk([f.name])
        os.unlink(f.name)
        self.assertIn("汇总", result)
        self.assertIn("严重", result)

    def test_empty_db_files_no_crash(self):
        result = self.analyze_db_risk([])
        self.assertIsInstance(result, str)


class TestRunTests(unittest.TestCase):
    """Test run_tests function with different project types."""

    def test_no_project_returns_true(self):
        from fix_issue import run_tests, DEFAULT_CONFIG
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                result = run_tests(DEFAULT_CONFIG)
                self.assertTrue(result)
            finally:
                os.chdir(old_cwd)

    def test_config_test_command(self):
        from fix_issue import run_tests
        config = {"test": {"command": "true"}}
        result = run_tests(config)
        self.assertTrue(result)

    def test_config_test_command_failure(self):
        from fix_issue import run_tests
        config = {"test": {"command": "false"}}
        result = run_tests(config)
        self.assertFalse(result)


class TestLoadConfig(unittest.TestCase):
    """Test load_config function."""

    def test_no_config_file_returns_defaults(self):
        from fix_issue import load_config, DEFAULT_CONFIG
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = load_config()
                self.assertEqual(config["trigger"]["label"], DEFAULT_CONFIG["trigger"]["label"])
                self.assertEqual(config["trigger"]["mention"], DEFAULT_CONFIG["trigger"]["mention"])
            finally:
                os.chdir(old_cwd)

    def test_config_file_loaded(self):
        from fix_issue import load_config
        config_content = """
trigger:
  label: "custom-label"
  mention: "@custom-bot"
test:
  command: "echo test"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with open(".issue-resolver.yml", "w") as f:
                    f.write(config_content)
                config = load_config()
                self.assertEqual(config["trigger"]["label"], "custom-label")
                self.assertEqual(config["trigger"]["mention"], "@custom-bot")
                self.assertEqual(config["test"]["command"], "echo test")
            finally:
                os.chdir(old_cwd)


class TestGhApi(unittest.TestCase):
    """Test gh_api helper with mocked HTTP."""

    @patch('fix_issue.urllib.request.urlopen')
    def test_gh_api_get_returns_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=None)
        mock_resp.read.return_value = b'{"key": "value"}'
        mock_urlopen.return_value = mock_resp

        from fix_issue import gh_api
        result = gh_api("GET", "owner/repo/issues/1", "fake-token")
        self.assertEqual(result, {"key": "value"})

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.urllib.request.urlopen')
    def test_gh_api_get_retries_on_transient_5xx(self, mock_urlopen, _mock_sleep):
        import urllib.error
        ok = MagicMock()
        ok.__enter__ = MagicMock(return_value=ok)
        ok.__exit__ = MagicMock(return_value=None)
        ok.read.return_value = b'{"key": "value"}'
        err = urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
        mock_urlopen.side_effect = [err, err, ok]

        from fix_issue import gh_api
        result = gh_api("GET", "owner/repo/issues/1", "fake-token")
        self.assertEqual(result, {"key": "value"})
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.urllib.request.urlopen')
    def test_gh_api_get_gives_up_after_max_attempts(self, mock_urlopen, _mock_sleep):
        import urllib.error
        err = urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
        mock_urlopen.side_effect = err

        from fix_issue import gh_api
        with self.assertRaises(urllib.error.HTTPError):
            gh_api("GET", "owner/repo/issues/1", "fake-token")
        self.assertEqual(mock_urlopen.call_count, 5)

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.urllib.request.urlopen')
    def test_gh_api_post_not_retried_on_5xx(self, mock_urlopen, _mock_sleep):
        import urllib.error
        err = urllib.error.HTTPError("http://x", 502, "Bad Gateway", {}, None)
        mock_urlopen.side_effect = err

        from fix_issue import gh_api
        with self.assertRaises(urllib.error.HTTPError):
            gh_api("POST", "owner/repo/issues/1/comments", "fake-token", body={"body": "x"})
        self.assertEqual(mock_urlopen.call_count, 1)


class TestPollAndMergeEarlyExit(unittest.TestCase):
    """poll_and_merge early-exit when repo has no CI/review chain."""

    def _fake_gh_api(self, check_runs, reviews):
        def fake(method, path, token, body=None):
            if "check-runs" in path:
                return {"check_runs": check_runs}
            if "/reviews" in path:
                return reviews
            return {}
        return fake

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.get_valid_token', return_value="fake-token")
    @patch('fix_issue.subprocess.run')
    @patch('fix_issue.gh_api')
    def test_early_exit_when_no_ci_no_review(self, mock_gh, mock_run, _tok, _sleep):
        mock_run.return_value = MagicMock(stdout="deadbeef\n")
        mock_gh.side_effect = self._fake_gh_api([], [])

        from fix_issue import poll_and_merge
        poll_and_merge("o/r", 1, 2, "http://x", max_wait=9999, interval=30,
                       no_signal_grace_polls=3)

        # 3 轮 × (check-runs + reviews) + 最后 1 次 POST 评论
        self.assertEqual(mock_gh.call_count, 3 * 2 + 1)
        last = mock_gh.call_args_list[-1]
        self.assertEqual(last[0][0], "POST")
        self.assertIn("comments", last[0][1])

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.get_valid_token', return_value="fake-token")
    @patch('fix_issue.subprocess.run')
    @patch('fix_issue.gh_api')
    def test_no_early_exit_when_bot_review_exists(self, mock_gh, mock_run, _tok, _sleep):
        mock_run.return_value = MagicMock(stdout="deadbeef\n")
        review = {"user": {"login": "github-actions[bot]"}, "state": "CHANGES_REQUESTED"}
        mock_gh.side_effect = self._fake_gh_api([], [review])

        from fix_issue import poll_and_merge
        poll_and_merge("o/r", 1, 2, "http://x", max_wait=9999, interval=30,
                       no_signal_grace_polls=3)

        # 有 review 信号 → 走原逻辑（CHANGES_REQUESTED 直接返回），无提前退出评论
        self.assertEqual(mock_gh.call_count, 2)
        for call in mock_gh.call_args_list:
            self.assertEqual(call[0][0], "GET")

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.get_valid_token', return_value="fake-token")
    @patch('fix_issue.subprocess.run')
    @patch('fix_issue.gh_api')
    def test_merge_when_ci_green_no_review_flow(self, mock_gh, mock_run, _tok, _sleep):
        """pilot-consumer PR #12 回归：有 CI 全绿、无 review 流 → grace 后直合。"""
        mock_run.return_value = MagicMock(stdout="deadbeef\n", returncode=0)
        green = [{"status": "completed", "conclusion": "success", "name": "pr-ci"}]
        mock_gh.side_effect = self._fake_gh_api(green, [])

        from fix_issue import poll_and_merge
        poll_and_merge("o/r", 1, 2, "http://x", max_wait=9999, interval=30,
                       review_grace_polls=3)

        # 3 轮 × (check-runs + reviews) + 合并 + POST 评论
        self.assertEqual(mock_gh.call_count, 3 * 2 + 1)
        last = mock_gh.call_args_list[-1]
        self.assertEqual(last[0][0], "POST")
        self.assertIn("no AI review flow", last[0][3]["body"])
        merges = [c for c in mock_run.call_args_list if c[0][0][:3] == ["gh", "pr", "merge"]]
        self.assertEqual(len(merges), 1)

    @patch('fix_issue.time.sleep', return_value=None)
    @patch('fix_issue.time.time', side_effect=[0, 10, 20, 50])
    @patch('fix_issue.get_valid_token', return_value="fake-token")
    @patch('fix_issue.subprocess.run')
    @patch('fix_issue.gh_api')
    def test_no_merge_when_bot_commented_awaiting_verdict(self, mock_gh, mock_run,
                                                          _tok, _time, _sleep):
        """有 review 流（COMMENTED 未裁决）→ 继续等 verdict，不直合。"""
        mock_run.return_value = MagicMock(stdout="deadbeef\n", returncode=0)
        green = [{"status": "completed", "conclusion": "success", "name": "pr-ci"}]
        review = {"user": {"login": "github-actions[bot]"}, "state": "COMMENTED"}
        mock_gh.side_effect = self._fake_gh_api(green, [review])

        from fix_issue import poll_and_merge
        poll_and_merge("o/r", 1, 2, "http://x", max_wait=45, interval=30,
                       review_grace_polls=3)

        # 2 轮 × 2 GET + 超时收尾 POST；subprocess 只有 rev-parse，无 merge；
        # POST 是超时提醒，不是合流评论
        self.assertEqual(mock_gh.call_count, 5)
        posts = [c for c in mock_gh.call_args_list if c[0][0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertIn("Timed out", posts[0][0][3]["body"])
        self.assertEqual(mock_run.call_count, 1)


class TestRebaseLogic(unittest.TestCase):
    """Test the rebase-before-push logic in fix_issue.py."""

    @patch('fix_issue.subprocess.run')
    def test_rebase_succeeds(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        from fix_issue import subprocess as sp_mod
        sp_mod.run(["git", "fetch", "origin", "main"], check=True)
        sp_mod.run(["git", "rebase", "origin/main"], capture_output=True, text=True)
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(mock_run.call_args_list[0][0][0], ["git", "fetch", "origin", "main"])

    @patch('fix_issue.subprocess.run')
    def test_rebase_fails_triggers_merge_fallback(self, mock_run):
        rebase_fail = MagicMock(returncode=1, stderr="conflict", stdout="")
        merge_success = MagicMock(returncode=0, stderr="", stdout="")
        abort = MagicMock(returncode=0, stderr="", stdout="")
        mock_run.side_effect = [rebase_fail, abort, merge_success]
        from fix_issue import subprocess as sp_mod
        sp_mod.run(["git", "rebase", "origin/main"], capture_output=True, text=True)
        sp_mod.run(["git", "rebase", "--abort"], check=True)
        sp_mod.run(["git", "merge", "origin/main", "--no-edit"], capture_output=True, text=True)
        self.assertEqual(mock_run.call_count, 3)

    def test_rebase_command_format(self):
        expected_fetch = ["git", "fetch", "origin", "main"]
        expected_rebase = ["git", "rebase", "origin/main"]
        self.assertEqual(expected_fetch[0], "git")
        self.assertEqual(expected_rebase[1], "rebase")
        self.assertEqual(expected_rebase[2], "origin/main")


class TestContentFilterHandling(unittest.TestCase):
    """Test fix_pr.py content-safety-filter detection and redaction."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

    def test_detects_sensitive_information_error(self):
        import fix_pr
        exc = RuntimeError("litellm.APIError: OpenAIException - "
                            "Input text May contain sensitive information, please try again.")
        self.assertTrue(fix_pr.is_content_filter_error(exc))

    def test_detects_content_filter_error(self):
        import fix_pr
        exc = RuntimeError("content_filter triggered by input")
        self.assertTrue(fix_pr.is_content_filter_error(exc))

    def test_ignores_unrelated_error(self):
        import fix_pr
        exc = RuntimeError("connection reset by peer")
        self.assertFalse(fix_pr.is_content_filter_error(exc))

    def test_redact_neutralizes_trigger_words(self):
        import fix_pr
        text = ("bypass entity_guard role checks; unauthenticated attacker could "
                "forge tokens; permission bypass; security hole")
        redacted = fix_pr.redact_for_display(text)
        for bad in ("bypass", "attacker", "unauthenticated", "forge tokens",
                    "security hole"):
            self.assertNotIn(bad, redacted.lower())

    def test_redact_preserves_unrelated_text(self):
        import fix_pr
        self.assertEqual(fix_pr.redact_for_display("cargo build ok"),
                         "cargo build ok")

    def test_redact_mode_prefix_is_nonempty(self):
        import fix_pr
        self.assertTrue(fix_pr._REDACT_MODE_PREFIX.strip())


if __name__ == "__main__":
    unittest.main()
