"""AR01I task contracts, strictly parsed, feature-off and side-effect free."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re

VERSION = "1.0.0"
UTC = dt.timezone.utc
HEX = re.compile(r"^[0-9a-f]{64}$")
SECRET_KEYS = ("password", "secret", "api_key", "access_token", "private_key", "credential")

class ContractError(ValueError):
    """Fail-closed contract boundary."""

def require(ok, reason):
    if not ok:
        raise ContractError(reason)

def fields(obj, required, optional=()):
    require(type(obj) is dict, "expected object")
    require(set(required) <= set(obj), "missing fields: " + ",".join(sorted(set(required)-set(obj))))
    require(not (set(obj)-set(required)-set(optional)), "unsupported fields")
    return obj

def string(v, *, nullable=False, maxlen=16000):
    if v is None and nullable:
        return
    require(type(v) is str and 0 < len(v) <= maxlen, "invalid string")

def integer(v, minimum=0):
    require(type(v) is int and v >= minimum, "invalid integer")

def enum(v, options):
    require(type(v) is str and v in options, "unsupported enum")

def timestamp(v, nullable=False):
    if v is None and nullable:
        return None
    string(v)
    require(v.endswith("Z"), "timestamp must use UTC Z")
    try:
        result = dt.datetime.fromisoformat(v[:-1]+"+00:00")
    except (ValueError, TypeError) as exc:
        raise ContractError("invalid UTC timestamp") from exc
    require(result.utcoffset() == dt.timedelta(0), "non UTC")
    return result

def digest(v, nullable=False):
    if v is None and nullable:
        return
    require(type(v) is str and HEX.fullmatch(v) is not None, "invalid sha256 digest")

def version(obj):
    require(obj.get("schema_version") == VERSION, "unsupported schema version")

def tenant(obj, expected):
    require(obj.get("tenant_id") == expected, "tenant mismatch")

def array(v, *, minimum=0, maximum=1024):
    require(type(v) is list and minimum <= len(v) <= maximum, "invalid array")

def refs(v, minimum=0):
    array(v, minimum=minimum)
    for ref in v:
        string(ref, maxlen=512)

def safe(obj):
    """Disallow inline credentials and arbitrary security controls in metadata."""
    if type(obj) is dict:
        for key, value in obj.items():
            string(key, maxlen=128)
            require(not any(s in key.lower() for s in SECRET_KEYS), "secret-like field")
            safe(value)
    elif type(obj) is list:
        for value in obj:
            safe(value)
    else:
        require(obj is None or type(obj) in (str, int, float, bool), "unsupported metadata value")

def canonical(obj):
    safe(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def outcome_spec(o):
    fields(o, ["outcome_id","kind","artifact_media_type","expected_uri_scope","validator_refs","required"])
    string(o["outcome_id"])
    enum(o["kind"], ("answer","file","patch","report","remote_state"))
    for k in ("artifact_media_type","expected_uri_scope"):
        string(o[k], nullable=True)
    refs(o["validator_refs"], minimum=1)
    require(type(o["required"]) is bool, "required must be boolean")
    if o["kind"] == "remote_state":
        require(any("external_state" in x or "remote_state" in x for x in o["validator_refs"]), "remote outcome needs external state validator")
    return o

def task_contract(o, now=None):
    fields(o, ["schema_version","task_id","task_version","tenant_id","actor","authority","workload_kind","goal","constraints","deadline_at","context_scopes","output_specs","definition_of_done","budget","privacy","created_at"], ["metadata"])
    version(o)
    for k in ("task_id","tenant_id"): string(o[k])
    integer(o["task_version"],1)
    a = fields(o["actor"], ["principal_id","principal_type","delegated_by","auth_context_ref","auth_expires_at"])
    string(a["principal_id"]); enum(a["principal_type"],("human","service"))
    string(a["delegated_by"], nullable=True); string(a["auth_context_ref"])
    expires=timestamp(a["auth_expires_at"])
    at=now or dt.datetime.now(UTC)
    require(expires > at, "expired actor auth")
    auth=fields(o["authority"], ["policy_ref","policy_version","allowed_capability_ids","max_side_effect","approval_policy_ref"])
    for k in ("policy_ref","policy_version","approval_policy_ref"): string(auth[k])
    refs(auth["allowed_capability_ids"])
    enum(auth["max_side_effect"], ("none","read","reversible_write","irreversible"))
    enum(o["workload_kind"], ("qa","research","coding","browser","ops","custom"))
    goal=fields(o["goal"], ["text","language"]); string(goal["text"]); string(goal["language"],nullable=True)
    refs(o["constraints"]); array(o["constraints"],maximum=128)
    deadline=timestamp(o["deadline_at"],nullable=True)
    if deadline is not None: require(deadline > at, "expired deadline")
    array(o["context_scopes"])
    for s in o["context_scopes"]:
        fields(s,["provider_kind","scope_id","access"])
        enum(s["provider_kind"],("knowledge","memory","skill","workspace","tool"))
        string(s["scope_id"])
        enum(s["access"],("read","propose_write","execute_write"))
        if s["access"]=="execute_write": require(auth["max_side_effect"] in ("reversible_write","irreversible"), "scope exceeds authority")
    array(o["output_specs"],minimum=1)
    for x in o["output_specs"]: outcome_spec(x)
    require(len(set(x["outcome_id"] for x in o["output_specs"]))==len(o["output_specs"]), "duplicate outcome")
    done=fields(o["definition_of_done"], ["predicate_refs","mode","independent_verification_required"])
    refs(done["predicate_refs"],minimum=1); enum(done["mode"],("all","any"))
    require(type(done["independent_verification_required"]) is bool, "invalid verification flag")
    b=fields(o["budget"], ["max_tokens","max_wall_ms","max_cost_microunits","currency","max_tool_calls","max_attempts"])
    for k in ("max_tokens","max_cost_microunits","max_tool_calls"): integer(b[k])
    for k in ("max_wall_ms","max_attempts"): integer(b[k],1)
    require(type(b["currency"]) is str and re.fullmatch(r"[A-Z]{3}",b["currency"]) is not None,"invalid ISO currency")
    p=fields(o["privacy"],["classification","residency","retention_ttl_seconds","allow_memory_promotion","consent_ref"])
    enum(p["classification"],("public","internal","confidential","restricted"))
    string(p["residency"],nullable=True); integer(p["retention_ttl_seconds"])
    require(type(p["allow_memory_promotion"]) is bool,"invalid memory flag")
    string(p["consent_ref"],nullable=True)
    if p["allow_memory_promotion"]: require(p["consent_ref"] is not None, "memory consent required")
    timestamp(o["created_at"])
    if "metadata" in o:
        require(type(o["metadata"]) is dict, "metadata object")
        require(all(":" in k for k in o["metadata"]), "metadata must be namespaced")
        safe(o["metadata"])
    return o

def outcome_receipt(o):
    fields(o,["schema_version","tenant_id","outcome_id","run_id","artifact_refs","verification_result_ids","fulfilled","observed_at","supersedes_receipt_id","created_at"])
    version(o)
    for k in ("tenant_id","outcome_id","run_id"): string(o[k])
    refs(o["artifact_refs"]); refs(o["verification_result_ids"])
    require(type(o["fulfilled"]) is bool,"invalid fulfilled")
    if o["fulfilled"]: require(bool(o["verification_result_ids"]), "cannot fulfill without verification")
    timestamp(o["observed_at"]); timestamp(o["created_at"])
    string(o["supersedes_receipt_id"],nullable=True)
    return o
