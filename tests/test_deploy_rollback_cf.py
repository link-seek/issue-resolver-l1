"""Static checks for the CF-Pages-anchored frontend baseline/rollback in deploy.yml.

Topology: frontend = Cloudflare Pages (main = production), backend = ECS.

Key finding (EAP drill 2026-09-22): EAP frontend uses ad_hoc direct-upload
deployments whose trigger metadata has NO commit_hash — matching Pages
deployments by release commit SHA can never hit. So:

- cf-wait job: record the current latest successful production deployment
  (id/url) BEFORE the release as rollback baseline; fail only when no
  successful production deployment exists or the API is unreachable.
- rollback-frontend job: on failure, POST the CF rollback endpoint for the
  recorded baseline id (no-op if frontend unchanged, correct restore if broken).
- handle-failure: cf-pages type means "baseline missing", not "SHA not ready".

Pure static check (no network): runs in the existing unit-test job
which only installs pytest+pyyaml.
"""
import pathlib

WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github" / "workflows" / "deploy.yml"
)


def _section(marker: str, window: int = 12000) -> str:
    text = WORKFLOW.read_text()
    start = text.find(marker)
    assert start != -1, f"marker not found in deploy.yml: {marker}"
    return text[start:start + window]


def test_cf_inputs_and_secret_declared():
    text = WORKFLOW.read_text()
    for name in ("cf-account-id:", "cf-project:", "CLOUDFLARE_API_TOKEN:"):
        assert name in text, f"cf input/secret missing: {name}"
    # OSS inputs must be gone (topology anchored, no multi-target compat)
    for name in ("oss-bucket:", "oss-region:"):
        assert name not in text, f"oss input still present: {name}"


def test_cf_baseline_recorded():
    section = _section("Record current production deployment")
    for s in (
        'environment == "production"',
        "latest_stage.status",
        "baseline-id=",
        "No successful CF Pages production deployment found",
    ):
        assert s in section, f"cf baseline piece missing: {s}"


def test_cf_baseline_does_not_match_sha():
    """Regression: ad_hoc deployments carry no commit_hash — SHA matching
    can never hit and stalls the pipeline (EAP drill 2026-09-22)."""
    section = _section("Record current production deployment")
    assert "commit_hash" not in section, \
        "cf baseline must not match deployments by commit SHA"


def test_rollback_api_present():
    section = _section("Rollback CF Pages to baseline deployment")
    for s in (
        "/pages/projects/",
        "/deployments/",
        "/rollback",
        "Authorization: Bearer",
    ):
        assert s in section, f"cf rollback API piece missing: {s}"


def test_rollback_uses_baseline_id():
    section = _section("Rollback CF Pages to baseline deployment")
    assert "BASELINE_ID" in section, \
        "rollback must target the recorded baseline deployment id"
    assert "commit_hash" not in section, \
        "rollback must not pick target by commit SHA (ad_hoc has none)"


def test_rollback_graceful_when_unconfigured():
    section = _section("Rollback CF Pages to baseline deployment")
    assert "result=skipped" in section, \
        "rollback must report skipped (not fail) when CF token/account unset"


def test_failure_classifier_reports_baseline():
    text = WORKFLOW.read_text()
    assert "FAILURE_DETAIL=\"CF Pages baseline missing" in text, \
        "cf-pages failure type must describe missing baseline, not SHA timeout"


def test_no_oss_remnants():
    text = WORKFLOW.read_text()
    for s in ("oss2", "OSS_BUCKET", "Rollback frontend to previous OSS version",
              "match OSS origin", "oss-bucket"):
        assert s not in text, f"oss remnant still present: {s}"
