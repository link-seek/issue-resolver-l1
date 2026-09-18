"""Regression test: fix.yml start-e2e must fail fast when E2E services never
become healthy, instead of reporting e2e_ready=true unconditionally.

Background (EAP #691, 2026-09-18): ghcr pull denied -> backend never came
up -> start-e2e still wrote e2e_ready=true -> agent burned ~40min + 3 LLM
re-runs on E2E 2/104 x4 -> fail-closed. The wait loops must record success
explicitly and exit 1 with an infra notify when unhealthy.

Pure static check (no docker): runs in the existing unit-test job
which only installs pytest+pyyaml.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "fix.yml"

REQUIRED_IN_START_E2E = [
    "BACKEND_OK=false",
    "BACKEND_OK=true",
    "FRONTEND_OK=false",
    "FRONTEND_OK=true",
    "exit 1",
    "Failing fast without burning agent tokens",
]

REQUIRED_NOTIFY = [
    "Notify infra failure",
    "steps.start-e2e.conclusion == 'failure'",
    "needs-human",
]

# The old e2e-gate print implied env health; it only checks spec tags/files.
REQUIRED_GATE_WORDING = "NOT service health"


def _start_e2e_section():
    text = WORKFLOW.read_text()
    start = text.find("Start E2E services (hot-reload env for agent verification)")
    assert start != -1, "start-e2e step not found in fix.yml"
    return text[start:start + 6000]


def test_start_e2e_fails_fast_when_unhealthy():
    section = _start_e2e_section()
    for s in REQUIRED_IN_START_E2E:
        assert s in section, f"start-e2e missing fail-fast piece: {s}"


def test_infra_failure_notifies_issue():
    text = WORKFLOW.read_text()
    for s in REQUIRED_NOTIFY:
        assert s in text, f"infra notify piece missing: {s}"


def test_gate_print_does_not_imply_health():
    for name in ("scripts/fix_issue.py", "scripts/fix_pr.py"):
        text = (REPO / name).read_text()
        assert REQUIRED_GATE_WORDING in text, f"{name}: gate print still implies env health"
        assert 'print("e2e-gate passed ✓")' not in text, f"{name}: old misleading print remains"
