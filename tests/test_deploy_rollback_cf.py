"""Static checks for the CF-Pages-anchored frontend gate/rollback in deploy.yml.

Topology: frontend = Cloudflare Pages (main = production), backend = ECS.
- cf-wait job: poll Pages production deployments for this release commit SHA,
  success gates smoke-test, failure/cancelled fails fast.
- rollback-frontend job: on failure, roll back via CF API to the previous
  successful production deployment (skipping the current release SHA).

Pure static check (no network): runs in the existing unit-test job
which only installs pytest+pyyaml.
"""
import pathlib
import re

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


def test_cf_wait_gate_present():
    section = _section("Wait for production deployment of this commit")
    for s in (
        "deployment_trigger.metadata.commit_hash == $sha",
        'environment == "production"',
        "latest_stage.status",
        "not ready within 10 minutes",
    ):
        assert s in section, f"cf-wait piece missing: {s}"


def test_cf_wait_fails_fast_on_broken_build():
    section = _section("Wait for production deployment of this commit")
    assert '"failure"' in section and '"cancelled"' in section, \
        "cf-wait must fail fast on failure/cancelled, not poll to timeout"


def test_rollback_api_present():
    section = _section("Rollback CF Pages to previous production deployment")
    for s in (
        "/pages/projects/",
        "/deployments/",
        "/rollback",
        "Authorization: Bearer",
    ):
        assert s in section, f"cf rollback API piece missing: {s}"


def test_rollback_skips_current_sha():
    section = _section("Rollback CF Pages to previous production deployment")
    assert ".deployment_trigger.metadata.commit_hash != $sha" in section, \
        "rollback must skip the current release commit when picking target"
    assert 'latest_stage.status == "success"' in section, \
        "rollback target must be a successful production deployment"


def test_rollback_graceful_when_unconfigured():
    section = _section("Rollback CF Pages to previous production deployment")
    assert "result=skipped" in section, \
        "rollback must report skipped (not fail) when CF token/account unset"


def test_no_oss_remnants():
    text = WORKFLOW.read_text()
    for s in ("oss2", "OSS_BUCKET", "Rollback frontend to previous OSS version",
              "match OSS origin", "oss-bucket"):
        assert s not in text, f"oss remnant still present: {s}"


def test_tag_sha_extraction():
    """Functional check of the commit-SHA extraction both CF steps rely on."""
    tag = "20260918170352-2f501eda0672be8ae09f32c975268ef05109e32a"
    m = re.search(r"[0-9a-f]{40}", tag)
    assert m and len(m.group(0)) == 40, "tag SHA format changed?"
    assert re.search(r"[0-9a-f]{40}", "latest") is None, \
        "non-SHA tags must yield no match (steps skip gracefully)"
