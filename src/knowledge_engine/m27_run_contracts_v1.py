"""AR01I pure run journal envelope checks. No journal or transition executor."""

from .m27_task_contracts_v1 import (
    digest,
    enum,
    fields,
    integer,
    refs,
    require,
    sha256,
    string,
    timestamp,
    version,
)

STATES = (
    "created",
    "planning",
    "running",
    "waiting_approval",
    "paused",
    "recovering",
    "succeeded",
    "failed",
    "cancelled",
    "unknown_effect",
)
TERMINAL = ("succeeded", "failed", "cancelled")
TRANSITIONS = {
    "created": ("planning", "cancelled", "failed"),
    "planning": ("running", "waiting_approval", "paused", "failed", "cancelled"),
    "running": (
        "waiting_approval",
        "paused",
        "recovering",
        "succeeded",
        "failed",
        "cancelled",
        "unknown_effect",
    ),
    "waiting_approval": ("running", "paused", "failed", "cancelled"),
    "paused": ("recovering", "cancelled", "failed"),
    "recovering": (
        "planning",
        "running",
        "waiting_approval",
        "unknown_effect",
        "failed",
        "cancelled",
    ),
    "unknown_effect": ("recovering", "failed", "cancelled"),
}


def run_state(o):
    fields(
        o,
        [
            "schema_version",
            "run_id",
            "task_id",
            "task_version",
            "tenant_id",
            "state",
            "seq",
            "attempt",
            "lease",
            "checkpoint_ref",
            "deadline_at",
            "cancel_requested",
            "active_action_ids",
            "spent",
            "last_event_hash",
            "updated_at",
            "ttl_expires_at",
            "created_at",
        ],
    )
    version(o)
    for k in ("run_id", "task_id", "tenant_id"):
        string(o[k])
    integer(o["task_version"], 1)
    enum(o["state"], STATES)
    integer(o["seq"])
    integer(o["attempt"])
    if o["lease"] is not None:
        lease = fields(o["lease"], ["holder_id", "epoch", "expires_at"])
        string(lease["holder_id"])
        integer(lease["epoch"], 1)
        timestamp(lease["expires_at"])
    string(o["checkpoint_ref"], nullable=True)
    timestamp(o["deadline_at"], nullable=True)
    require(type(o["cancel_requested"]) is bool, "invalid cancel flag")
    refs(o["active_action_ids"])
    spent = fields(o["spent"], ["tokens", "cost_microunits", "tool_calls", "elapsed_ms"])
    for v in spent.values():
        integer(v)
    digest(o["last_event_hash"], nullable=True)
    timestamp(o["updated_at"])
    timestamp(o["ttl_expires_at"])
    timestamp(o["created_at"])
    if o["state"] == "cancelled":
        require(not o["active_action_ids"], "unresolved action forbids cancelled certainty")
    return o


def run_event(o):
    fields(
        o,
        [
            "schema_version",
            "event_id",
            "run_id",
            "tenant_id",
            "seq",
            "prev_hash",
            "event_hash",
            "type",
            "version",
            "occurred_at",
            "recorded_at",
            "actor_ref",
            "payload_ref",
            "payload_digest",
            "lease_epoch",
            "attempt",
            "causation_id",
            "created_at",
        ],
    )
    version(o)
    for k in ("event_id", "run_id", "tenant_id", "type", "actor_ref"):
        string(o[k])
    integer(o["seq"], 1)
    integer(o["version"], 1)
    integer(o["attempt"])
    digest(o["prev_hash"], nullable=True)
    digest(o["event_hash"])
    timestamp(o["occurred_at"])
    timestamp(o["recorded_at"])
    timestamp(o["created_at"])
    string(o["payload_ref"], nullable=True)
    digest(o["payload_digest"], nullable=True)
    if o["payload_ref"] is not None:
        require(o["payload_digest"] is not None, "payload must have digest")
    if o["lease_epoch"] is not None:
        integer(o["lease_epoch"], 1)
    string(o["causation_id"], nullable=True)
    require(
        o["event_hash"] == sha256({k: v for k, v in o.items() if k != "event_hash"}),
        "event hash mismatch",
    )
    return o


def transition_allowed(before, after, *, reconciled=False, approval_valid=False):
    enum(before, STATES)
    enum(after, STATES)
    require(after in TRANSITIONS.get(before, ()), "illegal transition")
    if before == "unknown_effect":
        require(reconciled, "unknown effect requires reconciliation")
    if before == "waiting_approval" and after == "running":
        require(approval_valid, "approval required")
    return True


def checkpoint(o):
    fields(
        o,
        [
            "schema_version",
            "checkpoint_id",
            "run_id",
            "seq",
            "attempt",
            "lease_epoch",
            "workspace_snapshot_ref",
            "planner_state_digest",
            "pending_action_ids",
            "provider_version_refs",
            "created_at",
            "expires_at",
            "digest",
        ],
    )
    version(o)
    for k in ("checkpoint_id", "run_id", "workspace_snapshot_ref"):
        string(o[k])
    for k in ("seq", "attempt", "lease_epoch"):
        integer(o[k], 1)
    digest(o["planner_state_digest"])
    digest(o["digest"])
    refs(o["pending_action_ids"])
    refs(o["provider_version_refs"])
    timestamp(o["created_at"])
    timestamp(o["expires_at"])
    require(timestamp(o["expires_at"]) > timestamp(o["created_at"]), "invalid checkpoint TTL")
    return o
