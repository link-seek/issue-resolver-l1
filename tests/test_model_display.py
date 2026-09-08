"""Regression tests for model-name display (issue #540 in consumer repo).

Bot comments must show the real model (via ``LLM_MODEL_DISPLAY`` /
``{model_name}`` placeholder, same pattern as discuss.py) instead of a
hardcoded ``DeepSeek-V4-Flash`` string.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from templates import get_template

REAL_MODEL = "muse-spark-1.2-contributor-free"


class TestModelDisplay(unittest.TestCase):
    """Every user-visible template must render the passed-in model name."""

    def assertRendersModel(self, name: str, **kwargs):
        out = get_template(name, model_name=REAL_MODEL, **kwargs)
        self.assertIn(REAL_MODEL, out, f"{name} does not show the real model")
        self.assertNotIn("{model_name}", out, f"{name} has unreplaced placeholder")
        self.assertNotIn("DeepSeek", out, f"{name} still hardcodes DeepSeek")

    def test_issue_started(self):
        self.assertRendersModel("issue_started")

    def test_pr_created(self):
        self.assertRendersModel(
            "pr_created", emoji="✅", pr_num=1,
            pr_url="https://example.com/pr/1", test_status="通过",
        )

    def test_pr_body(self):
        self.assertRendersModel("pr_body", issue_number=1)

    def test_commit_msg(self):
        self.assertRendersModel(
            "commit_msg", issue_number=1, title="some title",
        )

    def test_issue_created_reply(self):
        self.assertRendersModel(
            "issue_created_reply", issue_number=1, issue_title="t",
            issue_url="https://example.com/i/1", issue_labels="fix-me",
        )

    def test_discussion_reply_unchanged(self):
        out = get_template(
            "discussion_reply", llm_response="hi", model_name=REAL_MODEL,
        )
        self.assertIn(REAL_MODEL, out)


if __name__ == "__main__":
    unittest.main()
