"""AR01I verification and publication envelopes; no grader or transport."""

import math

from .m27_task_contracts_v1 import (
    digest,
    enum,
    fields,
    integer,
    refs,
    require,
    string,
    timestamp,
    version,
)


def verification_result(o):
    fields(
        o,
        [
            "schema_version",
            "tenant_id",
            "verification_id",
            "run_id",
            "outcome_id",
            "kind",
            "verifier_id",
            "verifier_version",
            "input_digests",
            "result",
            "hard_gate",
            "score",
            "evidence_refs",
            "limitations",
            "checked_at",
            "expires_at",
            "created_at",
        ],
    )
    version(o)
    for k in (
        "tenant_id",
        "verification_id",
        "run_id",
        "outcome_id",
        "verifier_id",
        "verifier_version",
    ):
        string(o[k])
    enum(
        o["kind"],
        (
            "policy",
            "provenance",
            "semantic_claim",
            "citation",
            "artifact_functional",
            "remote_state",
            "human",
        ),
    )
    for d in o["input_digests"]:
        digest(d)
    refs(o["input_digests"])
    enum(o["result"], ("pass", "fail", "indeterminate", "requires_approval"))
    require(type(o["hard_gate"]) is bool, "invalid hard gate")
    if o["kind"] in ("policy", "remote_state"):
        require(o["hard_gate"], "hard gate cannot be downgraded")
    if o["score"] is not None:
        s = fields(o["score"], ["value", "scale_max", "rubric_version"])
        require(
            type(s["value"]) in (int, float)
            and type(s["scale_max"]) in (int, float)
            and math.isfinite(s["value"])
            and math.isfinite(s["scale_max"])
            and 0 <= s["value"] <= s["scale_max"]
            and s["scale_max"] > 0,
            "invalid score",
        )
        string(s["rubric_version"])
    refs(o["evidence_refs"])
    refs(o["limitations"])
    if o["kind"] == "remote_state" and o["result"] == "pass":
        require(bool(o["evidence_refs"]), "remote pass requires independent evidence")
    timestamp(o["checked_at"])
    timestamp(o["expires_at"], nullable=True)
    timestamp(o["created_at"])
    return o


def publication_event(o):
    fields(
        o,
        [
            "schema_version",
            "tenant_id",
            "publication_id",
            "run_id",
            "outcome_id",
            "revision",
            "segment_id",
            "kind",
            "supersedes_segment_ids",
            "content_digest",
            "verification_ids",
            "published_at",
            "first_payload_byte_at",
            "terminal_at",
            "created_at",
        ],
    )
    version(o)
    for k in ("tenant_id", "publication_id", "run_id", "outcome_id", "segment_id"):
        string(o[k])
    integer(o["revision"], 1)
    enum(o["kind"], ("provisional", "verified_segment", "correction", "retraction", "final"))
    refs(o["supersedes_segment_ids"])
    digest(o["content_digest"])
    refs(o["verification_ids"])
    timestamp(o["published_at"])
    timestamp(o["first_payload_byte_at"], nullable=True)
    timestamp(o["terminal_at"], nullable=True)
    timestamp(o["created_at"])
    if o["kind"] in ("verified_segment", "final"):
        require(bool(o["verification_ids"]), "publication requires verification")
    if o["kind"] in ("correction", "retraction"):
        require(bool(o["supersedes_segment_ids"]), "correction needs superseded segment")
    require(o["segment_id"] not in o["supersedes_segment_ids"], "self supersede forbidden")
    if o["first_payload_byte_at"] is not None:
        require(o["kind"] in ("verified_segment", "final"), "text byte needs verified publication")
    return o
