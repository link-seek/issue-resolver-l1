"""Static test: every L1 scripts checkout must be followed by a SHA log step.

Policy (see README 版本政策): workflows are pinned by tag, scripts float on
main by design. Each run must print `L1 scripts SHA=<commit>` so behavior is
traceable.
"""

import os
import unittest

WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows")

# workflow file -> checkout path whose SHA must be logged
CHECKS = {
    "fix.yml": "issue-resolver-scripts",
    "discuss.yml": "issue-resolver-scripts",
    "pr-ci.yml": "_issue-resolver",
}


class TestScriptsVersionLog(unittest.TestCase):
    def test_log_step_follows_checkout(self):
        for wf, path in CHECKS.items():
            with self.subTest(workflow=wf):
                with open(os.path.join(WORKFLOWS_DIR, wf), encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("name: Log L1 scripts version", text,
                              f"{wf} 缺少 Log L1 scripts version 步骤")
                self.assertIn(f"git -C {path} rev-parse HEAD", text,
                              f"{wf} 未记录 {path} 的 SHA")

    def test_log_step_after_checkout(self):
        """Log 步骤必须出现在 checkout 之后（顺序即执行顺序）。"""
        for wf, path in CHECKS.items():
            with self.subTest(workflow=wf):
                with open(os.path.join(WORKFLOWS_DIR, wf), encoding="utf-8") as f:
                    text = f.read()
                co = text.find("Checkout issue-resolver scripts" if path == "issue-resolver-scripts" else "path: _issue-resolver")
                lo = text.find("name: Log L1 scripts version")
                self.assertGreater(co, -1, f"{wf} 找不到 scripts checkout")
                self.assertGreater(lo, co, f"{wf} 的 Log 步骤不在 checkout 之后")


if __name__ == "__main__":
    unittest.main()
