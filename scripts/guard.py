#!/usr/bin/env python3
"""
Guard: L1 hard limit — detect and revert .github/workflows/ changes.

Called by fix_issue.py and fix_pr.py before commit to ensure the agent
didn't modify the consumer repo's thin shell (workflow files).
"""

from __future__ import annotations

import subprocess


WORKFLOW_DIR = ".github/workflows/"


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def detect(commit_before: str) -> list[str]:
    """Detect all .github/workflows/ changes since commit_before.

    Includes committed, staged, unstaged, and untracked changes.
    """
    changed: set[str] = set()

    # Committed changes (commit_before..HEAD)
    for line in _run(["git", "diff", "--name-only", commit_before, "HEAD", "--", WORKFLOW_DIR]).splitlines():
        if line.strip():
            changed.add(line.strip())

    # Uncommitted changes (HEAD..working tree)
    for line in _run(["git", "diff", "--name-only", "HEAD", "--", WORKFLOW_DIR]).splitlines():
        if line.strip():
            changed.add(line.strip())

    # Untracked files
    for line in _run(["git", "ls-files", "--others", "--exclude-standard", WORKFLOW_DIR]).splitlines():
        if line.strip():
            changed.add(line.strip())

    return sorted(changed)


def revert(commit_before: str) -> list[str]:
    """Revert all .github/workflows/ changes to commit_before state.

    Returns list of reverted file paths.
    """
    changed = detect(commit_before)
    if not changed:
        return []

    for filepath in changed:
        # Check if file existed in commit_before
        check = subprocess.run(
            ["git", "cat-file", "-e", f"{commit_before}:{filepath}"],
            capture_output=True,
        )
        if check.returncode == 0:
            # File existed before — restore to commit_before version
            subprocess.run(
                ["git", "checkout", commit_before, "--", filepath],
                capture_output=True, text=True,
            )
        else:
            # File is new (created by agent) — remove it
            subprocess.run(["rm", "-f", filepath], capture_output=True)
            subprocess.run(
                ["git", "rm", "--cached", "-f", filepath],
                capture_output=True, text=True,
            )

    # Stage all reverts
    subprocess.run(["git", "add", WORKFLOW_DIR], capture_output=True, text=True)

    return changed


def guard(
    commit_before: str,
    repo_name: str,
    target_number: int,
    github_token: str,
    gh_api_fn,
    is_pr: bool = False,
) -> list[str]:
    """Run guard: detect + revert + notify.

    Returns list of reverted file paths (empty if guard not triggered).
    """
    reverted = revert(commit_before)
    if not reverted:
        print("[guard] ✓ No workflow file changes detected")
        return []

    print(f"[guard] ⚠ Reverted {len(reverted)} workflow file change(s):")
    for f in reverted:
        print(f"  - {f}")

    # Notify via issue/PR comment
    files_list = "\n".join(f"- `{f}`" for f in reverted)
    body = (
        "⚠️ **Guard: L1 硬限制触发**\n\n"
        "L1 agent 尝试修改 `.github/workflows/` 下的文件（薄壳），已自动撤回：\n\n"
        f"{files_list}\n\n"
        "这些文件属于消费仓的薄壳层，L1 无权修改。如需修改 workflow，请人工处理。"
    )
    try:
        gh_api_fn(
            "POST",
            f"{repo_name}/issues/{target_number}/comments",
            github_token,
            {"body": body},
        )
    except Exception as e:
        print(f"[guard] Failed to post notification: {e}")

    return reverted
