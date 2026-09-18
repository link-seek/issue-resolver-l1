"""Regression test: fix.yml must dedupe superseded runs for the same
issue/PR instead of letting queued runs redo finished work.

Background (EAP #691, 2026-09-18): callers queue with cancel:false, so a
later run often starts after the previous one already delivered (PR pushed
/ fail-closed) and can only spin idly or be cancelled (26 cancelled runs
in 48h).

Design: a `dedupe` job runs before `resolve`. It skips (green exit) when a
bot result comment exists NEWER than the trigger comment with no human
follow-up. Dedupe errors fail OPEN (never block real fixes).

Pure static check (no gh api): runs in the existing unit-test job
which only installs pytest+pyyaml.
"""
import pathlib

WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github" / "workflows" / "fix.yml"
)


def _text():
    return WORKFLOW.read_text()


def test_dedupe_job_exists_with_skip_output():
    text = _text()
    assert "dedupe:" in text
    assert "skip: ${{ steps.check.outputs.skip }}" in text


def test_resolve_gated_on_dedupe_fail_open():
    text = _text()
    assert "needs: [dedupe]" in text
    # dedupe itself erroring must NOT block the real fix
    assert "needs.dedupe.result != 'success'" in text
    assert "needs.dedupe.outputs.skip != 'true'" in text


def test_skip_note_excluded_from_future_checks():
    text = _text()
    # skip notes must carry the marker AND be in the noise list,
    # otherwise one skip would cascade-skip legitimate reruns
    assert "dedupe-skip" in text
    assert '"dedupe-skip"' in text or "'dedupe-skip'" in text or "dedupe-skip" in text
    noise_section = text[text.find("NOISE_KEYS"):text.find("NOISE_KEYS") + 300]
    assert "dedupe-skip" in noise_section
    assert "已开始处理" in noise_section


def test_trigger_fallback_to_run_created_at():
    text = _text()
    # labeled events have no comment id; fall back to run creation time
    assert "actions/runs/$RUN_ID" in text
    assert "COMMENT_ID" in text
