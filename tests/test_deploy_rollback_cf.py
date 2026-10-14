"""Static checks for the CF-Pages-anchored frontend baseline/rollback in deploy.yml.

Topology: frontend = Cloudflare Pages (main = production), backend = ECS.

History:
- EAP drill 2026-09-22: ad_hoc direct-uploads carried NO commit_hash, so
  baseline recorded "latest successful production deployment".
- Production evidence 2026-10-14 (EAP #755): our uploader passes
  --commit-hash, so ad_hoc deployments DO carry commit metadata
  (e.g. 7cf26b63). And Pages rollback only repoints production without
  creating a new record, so "latest in list" is NOT the live deployment
  after any rollback. Hence:
- cf-wait job: record the LIVE production deployment (canonical_deployment
  id/url) BEFORE the release as rollback baseline; fail only when the
  canonical deployment is unknown or the API is unreachable.
- rollback-frontend job: target the recorded baseline; exclude builds
  uploaded by THIS release (commit prefix from image-tag) as fallback;
  no-op when the target is already live; treat CF 8000039 (already live)
  as idempotent success.
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
        "canonical_deployment",
        "baseline-id=",
        "No live CF Pages production deployment found",
    ):
        assert s in section, f"cf baseline piece missing: {s}"


def test_cf_baseline_is_live_not_latest():
    """Regression (EAP #755, 2026-10-14): Pages rollback only repoints
    production without creating a new record, so the list head may be an
    offline build. Baseline must be the live canonical deployment."""
    section = _section("Record current production deployment")
    assert "canonical" in section, \
        "cf baseline must record the live (canonical) deployment, not list head"


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
    # Commit metadata is used ONLY to exclude this release's own builds as
    # fallback (our uploader passes --commit-hash; verified live 2026-10-14).
    # Positive selection stays baseline-first, never SHA-first.
    assert "CANDIDATES" in section, \
        "rollback must fall back to newest non-release build when baseline is stale"


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
