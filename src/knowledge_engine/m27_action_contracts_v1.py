"""AR01I action envelope and pure authorization predicate; no dispatch."""
from .m27_task_contracts_v1 import fields,version,string,integer,timestamp,digest,refs,enum,require,sha256
SIDES=("none","read","reversible_write","irreversible")
LEVEL={s:i for i,s in enumerate(SIDES)}
def tool_capability(o):
    fields(o,["schema_version","tenant_id","capability_id","capability_version","operations","side_effect","sandbox_scope","input_schema_digest","output_schema_digest","timeout_ms","rate_limit_ref","idempotency_support","reconciliation_method_ref","compensation_method_ref","requires_approval","expires_at","created_at"])
    version(o)
    for k in ("tenant_id","capability_id","capability_version"):string(o[k])
    refs(o["operations"],1);refs(o["sandbox_scope"])
    enum(o["side_effect"],SIDES)
    digest(o["input_schema_digest"]);digest(o["output_schema_digest"])
    integer(o["timeout_ms"],1)
    for k in ("rate_limit_ref","reconciliation_method_ref","compensation_method_ref"):string(o[k],nullable=True)
    enum(o["idempotency_support"],("provider_enforced","read_reconcile","none"))
    require(type(o["requires_approval"]) is bool,"invalid approval requirement")
    timestamp(o["expires_at"],nullable=True);timestamp(o["created_at"])
    if o["side_effect"]=="irreversible":require(o["requires_approval"],"irreversible approval required")
    return o
def action_intent(o):
    fields(o,["schema_version","tenant_id","intent_id","run_id","principal_id","capability_id","capability_version","operation","resource_id","arguments_ref","arguments_digest","precondition","idempotency_key","side_effect","approval_id","requested_at","expires_at","policy_version","lease_epoch","attempt","created_at"])
    version(o)
    for k in ("tenant_id","intent_id","run_id","principal_id","capability_id","capability_version","operation","resource_id","arguments_ref","idempotency_key","policy_version"): string(o[k])
    digest(o["arguments_digest"]);enum(o["side_effect"],SIDES)
    p=fields(o["precondition"],["resource_version","expected_state_digest"])
    string(p["resource_version"],nullable=True);digest(p["expected_state_digest"],nullable=True)
    string(o["approval_id"],nullable=True)
    timestamp(o["requested_at"]);timestamp(o["expires_at"]);timestamp(o["created_at"])
    require(timestamp(o["expires_at"])>timestamp(o["requested_at"]),"expired action")
    integer(o["lease_epoch"],1);integer(o["attempt"])
    return o
def approval_record(o):
    fields(o,["schema_version","tenant_id","approval_id","intent_digest","approver_principal","approver_authority_ref","decision","decided_at","expires_at","one_time","policy_version","created_at"])
    version(o)
    for k in ("tenant_id","approval_id","approver_principal","approver_authority_ref","policy_version"):string(o[k])
    digest(o["intent_digest"]);enum(o["decision"],("approved","rejected"))
    timestamp(o["decided_at"]);timestamp(o["expires_at"]);timestamp(o["created_at"])
    require(type(o["one_time"]) is bool,"invalid approval flag")
    return o
def action_receipt(o):
    fields(o,["schema_version","tenant_id","receipt_id","intent_id","idempotency_key","attempt","provider_request_id","dispatched_at","observed_at","status","external_resource_id","external_version","observation_ref","observation_digest","compensation_intent_id","verified_by","error_code","created_at"])
    version(o)
    for k in ("tenant_id","receipt_id","intent_id","idempotency_key"):string(o[k])
    integer(o["attempt"])
    for k in ("provider_request_id","external_resource_id","external_version","observation_ref","compensation_intent_id","verified_by","error_code"):string(o[k],nullable=True)
    timestamp(o["dispatched_at"],nullable=True);timestamp(o["observed_at"]);timestamp(o["created_at"])
    enum(o["status"],("not_dispatched","confirmed_applied","confirmed_not_applied","unknown","compensated","compensation_failed"))
    digest(o["observation_digest"],nullable=True)
    if o["status"] in ("confirmed_applied","compensated"):
        require(o["observation_ref"] is not None and o["observation_digest"] is not None and o["verified_by"] is not None,"authoritative observation required")
    if o["status"]=="not_dispatched":require(o["dispatched_at"] is None,"dispatch contradiction")
    return o
def authorize(intent,capability,approval=None,*,now=None,policy_max="none"):
    action_intent(intent);tool_capability(capability)
    require(intent["tenant_id"]==capability["tenant_id"],"capability tenant mismatch")
    require(intent["capability_id"]==capability["capability_id"] and intent["capability_version"]==capability["capability_version"],"capability mismatch")
    require(intent["operation"] in capability["operations"],"operation not allowed")
    require(intent["side_effect"]==capability["side_effect"],"side effect mismatch")
    enum(policy_max,SIDES);require(LEVEL[intent["side_effect"]]<=LEVEL[policy_max],"policy capability exceeded")
    now=now or __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    require(timestamp(intent["expires_at"])>now,"expired intent")
    if capability["expires_at"] is not None:require(timestamp(capability["expires_at"])>now,"expired capability")
    if intent["side_effect"]=="irreversible" or capability["requires_approval"]:
        require(approval is not None and intent["approval_id"] is not None,"missing approval")
    if approval is not None:
        approval_record(approval)
        require(approval["tenant_id"]==intent["tenant_id"] and approval["approval_id"]==intent["approval_id"],"approval scope mismatch")
        require(approval["intent_digest"]==sha256(intent),"approval intent digest mismatch")
        require(approval["policy_version"]==intent["policy_version"],"stale approval policy")
        require(approval["decision"]=="approved" and timestamp(approval["expires_at"])>now,"approval rejected or expired")
        require(approval["approver_principal"]!=intent["principal_id"],"self approval denied")
    return True
def idempotency_compatible(a,b):
    action_intent(a);action_intent(b)
    if a["idempotency_key"]==b["idempotency_key"]:
        require((a["tenant_id"],a["arguments_digest"],a["operation"],a["resource_id"])==(b["tenant_id"],b["arguments_digest"],b["operation"],b["resource_id"]),"idempotency conflict")
    return True
