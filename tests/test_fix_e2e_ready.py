"""Regression test: fix.yml start-e2e must report E2E health honestly, and the
verifier must re-check live health instead of trusting a stale flag.

Background (EAP #691, 2026-09-18): ghcr pull denied -> backend never came
up -> start-e2e still wrote e2e_ready=true -> agent burned ~40min + 3 LLM
re-runs on E2E 2/104 x4 before fail-closed.

Design (agent CAN recover infra itself, so no fail-fast exit):
  - start-e2e records BACKEND_OK/FRONTEND_OK; unhealthy -> e2e_ready=false
    + e2e_unhealthy="backend=.. frontend=.. compose=.." (job continues)
  - prompt tells agent to recover env first (E2E_UNHEALTHY)
  - run_e2e_verification re-checks LIVE health when startup was unhealthy:
    recovered -> run suite; still down -> infra failure dict (never silent
    skip, never blind push)

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
    "e2e_unhealthy=",
    "E2E_UNHEALTHY",
]

REQUIRED_PROMPT = [
    "E2E_UNHEALTHY",
    "先恢复环境",
]

REQUIRED_VERIFIER = [
    "_e2e_services_healthy",
    "E2E_UNHEALTHY",
    "infra failure",
]

# The old e2e-gate print implied env health; it only checks spec tags/files.
REQUIRED_GATE_WORDING = "NOT service health"


def _start_e2e_section():
    text = WORKFLOW.read_text()
    start = text.find("Start E2E services (hot-reload env for agent verification)")
    assert start != -1, "start-e2e step not found in fix.yml"
    return text[start:start + 6000]


def test_start_e2e_reports_health_honestly():
    section = _start_e2e_section()
    for s in REQUIRED_IN_START_E2E:
        assert s in section, f"start-e2e missing honest-signal piece: {s}"
    # v2: job must continue so the agent can recover infra itself
    assert "exit 1" not in section, "start-e2e must not fail the job (agent recovers infra)"


def test_unhealthy_env_passed_to_agent():
    text = WORKFLOW.read_text()
    assert text.count("E2E_UNHEALTHY: ${{ steps.start-e2e.outputs.e2e_unhealthy }}") >= 2, \
        "E2E_UNHEALTHY must reach both Run-fix steps (issue + PR mode)"


def test_prompt_tells_agent_to_recover_first():
    for name in ("scripts/fix_issue.py", "scripts/fix_pr.py"):
        text = (REPO / name).read_text()
        for s in REQUIRED_PROMPT:
            assert s in text, f"{name}: prompt missing recovery-first piece: {s}"


def test_verifier_rechecks_live_health():
    for name in ("scripts/fix_issue.py", "scripts/fix_pr.py"):
        text = (REPO / name).read_text()
        for s in REQUIRED_VERIFIER:
            assert s in text, f"{name}: verifier missing live re-check piece: {s}"


def test_gate_print_does_not_imply_health():
    for name in ("scripts/fix_issue.py", "scripts/fix_pr.py"):
        text = (REPO / name).read_text()
        assert REQUIRED_GATE_WORDING in text, f"{name}: gate print still implies env health"
        assert 'print("e2e-gate passed ✓")' not in text, f"{name}: old misleading print remains"
