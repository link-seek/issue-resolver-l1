"""Regression test: rollback-frontend heredoc in deploy.yml must use real
oss2 2.x API names (verified against oss2/models.py ListObjectVersionsResult
+ Bucket.list_object_versions signature), not boto3-style names.

oss2 ground truth (2.19.1):
  result.versions / result.delete_marker / result.next_key_marker /
  result.next_versionid_marker / kwarg versionid_marker=
boto3-style names that MUST NOT appear:
  result.object_versions / result.delete_marker_versions /
  result.next_version_id_marker / kwarg version_id_marker=

Pure static check (no oss2 import): runs in the existing unit-test job
which only installs pytest+pyyaml.
"""
import pathlib

WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github" / "workflows" / "deploy.yml"
)

REQUIRED = [
    "result.versions",
    "result.delete_marker",
    "result.next_versionid_marker",
    "versionid_marker=",
    "oss2==2.19.1",
]

BANNED = [
    "result.object_versions",
    "result.delete_marker_versions",
    "result.next_version_id_marker",
    "version_id_marker=",
]


def _rollback_section():
    text = WORKFLOW.read_text()
    # start at the oss2 install step (holds the version pin), which sits
    # just above the rollback step
    start = text.find("Install oss2 SDK")
    if start == -1:
        start = text.find("Rollback frontend to previous OSS version")
    assert start != -1, "rollback-frontend steps not found in deploy.yml"
    # section runs until the next top-level job/step marker; take a wide window
    return text[start:start + 16000]


def test_no_boto3_style_oss_names():
    section = _rollback_section()
    for name in BANNED:
        assert name not in section, f"boto3-style name still present: {name}"


def test_oss2_api_names_and_pin():
    section = _rollback_section()
    for name in REQUIRED:
        assert name in section, f"expected oss2 name/pin missing: {name}"
