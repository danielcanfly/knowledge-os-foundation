"""AR01I context reference validation; no provider access."""

from .m27_task_contracts_v1 import (
    array,
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

TRUST = ("untrusted", "source_attested", "governed")
ACCESS = ("read", "propose_write", "execute_write")


def context_request(o):
    fields(
        o,
        [
            "schema_version",
            "tenant_id",
            "request_id",
            "run_id",
            "task_version",
            "principal_id",
            "scopes",
            "max_tokens",
            "max_latency_ms",
            "max_cost_microunits",
            "required_freshness_seconds",
            "trust_floor",
            "purpose",
            "policy_version",
            "created_at",
        ],
    )
    version(o)
    for k in ("tenant_id", "request_id", "run_id", "principal_id", "purpose", "policy_version"):
        string(o[k])
    integer(o["task_version"], 1)
    array(o["scopes"])
    for s in o["scopes"]:
        fields(s, ["provider_kind", "scope_id", "query_ref", "access"])
        enum(s["provider_kind"], ("knowledge", "memory", "skill", "workspace", "tool"))
        string(s["scope_id"])
        string(s["query_ref"])
        enum(s["access"], ACCESS)
    integer(o["max_tokens"])
    integer(o["max_latency_ms"], 1)
    integer(o["max_cost_microunits"])
    if o["required_freshness_seconds"] is not None:
        integer(o["required_freshness_seconds"])
    enum(o["trust_floor"], TRUST)
    timestamp(o["created_at"])
    return o


def context_item(o):
    fields(
        o,
        [
            "schema_version",
            "tenant_id",
            "item_id",
            "kind",
            "source_id",
            "source_revision",
            "source_locator",
            "source_digest",
            "acl_decision_ref",
            "trust",
            "retrieved_at",
            "expires_at",
            "content_ref",
            "citation_eligible",
            "taint_labels",
            "consent_ref",
            "created_at",
        ],
    )
    version(o)
    for k in (
        "tenant_id",
        "item_id",
        "source_id",
        "source_revision",
        "acl_decision_ref",
        "content_ref",
    ):
        string(o[k])
    enum(o["kind"], ("evidence", "memory", "skill", "workspace", "tool_observation"))
    string(o["source_locator"], nullable=True)
    digest(o["source_digest"])
    enum(o["trust"], TRUST)
    timestamp(o["retrieved_at"])
    timestamp(o["expires_at"])
    timestamp(o["created_at"])
    require(timestamp(o["expires_at"]) > timestamp(o["retrieved_at"]), "expired item at retrieval")
    require(type(o["citation_eligible"]) is bool, "invalid citation flag")
    refs(o["taint_labels"])
    string(o["consent_ref"], nullable=True)
    if o["citation_eligible"]:
        require(o["source_locator"] is not None, "citation requires source locator")
        require(o["trust"] != "untrusted", "untrusted item cannot claim governed citation")
    if o["kind"] == "memory":
        require(o["consent_ref"] is not None, "memory consent required")
    return o


def context_bundle(o, request=None, *, now=None):
    fields(
        o,
        [
            "schema_version",
            "tenant_id",
            "bundle_id",
            "request_id",
            "provider_versions",
            "items",
            "token_count",
            "cost_microunits",
            "created_at",
            "expires_at",
            "policy_decision_ref",
            "omissions",
            "run_id",
        ],
    )
    version(o)
    for k in ("tenant_id", "bundle_id", "request_id", "policy_decision_ref", "run_id"):
        string(o[k])
    array(o["provider_versions"])
    for v in o["provider_versions"]:
        fields(v, ["kind", "provider_id", "version"])
        for x in v.values():
            string(x)
    array(o["items"])
    for item in o["items"]:
        context_item(item)
        require(item["tenant_id"] == o["tenant_id"], "cross tenant context item")
        if now is not None:
            require(timestamp(item["expires_at"]) > now, "expired context item")
    integer(o["token_count"])
    integer(o["cost_microunits"])
    timestamp(o["created_at"])
    timestamp(o["expires_at"])
    require(timestamp(o["expires_at"]) > timestamp(o["created_at"]), "invalid context TTL")
    array(o["omissions"])
    for miss in o["omissions"]:
        fields(miss, ["scope_id", "reason"])
        string(miss["scope_id"])
        string(miss["reason"])
    if request is not None:
        context_request(request)
        require(
            request["tenant_id"] == o["tenant_id"]
            and request["request_id"] == o["request_id"]
            and request["run_id"] == o["run_id"],
            "request scope mismatch",
        )
        require(
            o["token_count"] <= request["max_tokens"]
            and o["cost_microunits"] <= request["max_cost_microunits"],
            "budget exceeded",
        )
    return o
