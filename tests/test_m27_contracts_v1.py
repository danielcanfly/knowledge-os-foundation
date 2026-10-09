"""Pure offline contract tests. Runtime-only N-cases remain NOT IMPLEMENTED."""

import copy

import pytest

from knowledge_engine import m27_action_contracts_v1 as a
from knowledge_engine import m27_context_contracts_v1 as c
from knowledge_engine import m27_run_contracts_v1 as r
from knowledge_engine import m27_task_contracts_v1 as t
from knowledge_engine import m27_verification_contracts_v1 as v

FUTURE = "2099-01-01T00:00:00Z"
EARLY = "2020-01-01T00:00:00Z"
D = "a" * 64


def task():
    return dict(
        schema_version="1.0.0",
        task_id="t",
        task_version=1,
        tenant_id="A",
        actor=dict(
            principal_id="u",
            principal_type="human",
            delegated_by=None,
            auth_context_ref="auth:1",
            auth_expires_at=FUTURE,
        ),
        authority=dict(
            policy_ref="p",
            policy_version="v1",
            allowed_capability_ids=[],
            max_side_effect="none",
            approval_policy_ref="approval-policy",
        ),
        workload_kind="qa",
        goal=dict(text="answer", language=None),
        constraints=[],
        deadline_at=FUTURE,
        context_scopes=[],
        output_specs=[
            dict(
                outcome_id="o",
                kind="answer",
                artifact_media_type=None,
                expected_uri_scope=None,
                validator_refs=["claim"],
                required=True,
            )
        ],
        definition_of_done=dict(
            predicate_refs=["pass"], mode="all", independent_verification_required=True
        ),
        budget=dict(
            max_tokens=0,
            max_wall_ms=10,
            max_cost_microunits=0,
            currency="USD",
            max_tool_calls=0,
            max_attempts=1,
        ),
        privacy=dict(
            classification="internal",
            residency=None,
            retention_ttl_seconds=0,
            allow_memory_promotion=False,
            consent_ref=None,
        ),
        created_at=EARLY,
    )


def intent():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        intent_id="i",
        run_id="r",
        principal_id="model",
        capability_id="cap",
        capability_version="v1",
        operation="read",
        resource_id="x",
        arguments_ref="opaque:args",
        arguments_digest=D,
        precondition=dict(resource_version=None, expected_state_digest=None),
        idempotency_key="tenant-A-key",
        side_effect="read",
        approval_id=None,
        requested_at=EARLY,
        expires_at=FUTURE,
        policy_version="p1",
        lease_epoch=1,
        attempt=1,
        created_at=EARLY,
    )


def cap():
    return dict(
        schema_version="1.0.0",
        capability_id="cap",
        version="v1",
        provider_id="provider",
        operation="read",
        tenant_binding="A",
        principal_scope=["model"],
        resource_scope=["x"],
        privilege="read",
        side_effect="read",
        credential_ref=None,
        egress_allowlist=[],
        sandbox_scope=["resource:x"],
        input_schema_digest=D,
        output_schema_digest=D,
        timeout_ms=100,
        rate_limit_ref=None,
        idempotency_support="read_reconcile",
        reconciliation_method_ref=None,
        compensation_method_ref=None,
        requires_approval=False,
        expires_at=FUTURE,
    )


def item():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        item_id="item",
        kind="evidence",
        source_id="s",
        source_revision="rev",
        source_locator="source://s/rev",
        source_digest=D,
        acl_decision_ref="acl:1",
        trust="governed",
        retrieved_at=EARLY,
        expires_at=FUTURE,
        content_ref="opaque:data",
        citation_eligible=True,
        taint_labels=["untrusted-text"],
        consent_ref=None,
        created_at=EARLY,
    )


def bundle():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        bundle_id="b",
        request_id="req",
        run_id="r",
        provider_versions=[],
        items=[item()],
        token_count=0,
        cost_microunits=0,
        created_at=EARLY,
        expires_at=FUTURE,
        policy_decision_ref="policy:yes",
        omissions=[],
    )


def request():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        request_id="req",
        run_id="r",
        task_version=1,
        principal_id="u",
        scopes=[],
        max_tokens=0,
        max_latency_ms=10,
        max_cost_microunits=0,
        required_freshness_seconds=None,
        trust_floor="governed",
        purpose="answer",
        policy_version="p1",
        created_at=EARLY,
    )


def receipt():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        receipt_id="rr",
        intent_id="i",
        idempotency_key="key",
        attempt=1,
        provider_request_id=None,
        dispatched_at=None,
        observed_at=EARLY,
        status="not_dispatched",
        external_resource_id=None,
        external_version=None,
        observation_ref=None,
        observation_digest=None,
        compensation_intent_id=None,
        verified_by=None,
        error_code=None,
        created_at=EARLY,
    )


def verification():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        verification_id="v",
        run_id="r",
        outcome_id="o",
        kind="policy",
        verifier_id="p",
        verifier_version="1",
        input_digests=[D],
        result="pass",
        hard_gate=True,
        score=None,
        evidence_refs=["policy:1"],
        limitations=[],
        checked_at=EARLY,
        expires_at=FUTURE,
        created_at=EARLY,
    )


def publication():
    return dict(
        schema_version="1.0.0",
        tenant_id="A",
        publication_id="pub",
        run_id="r",
        outcome_id="o",
        revision=1,
        segment_id="seg",
        kind="verified_segment",
        supersedes_segment_ids=[],
        content_digest=D,
        verification_ids=["v"],
        published_at=EARLY,
        first_payload_byte_at=EARLY,
        terminal_at=None,
        created_at=EARLY,
    )


def mutate(obj, path, value):
    x = copy.deepcopy(obj)
    node = x
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return x


# 33 distinct contract-level negative adversarial fixtures (not runtime simulations).
NEG = [
    ("N03 missing delegation expiry", task, ("actor", "auth_expires_at"), None, t.task_contract),
    ("N04 unknown major", task, ("schema_version",), "2.0.0", t.task_contract),
    ("N04 unsupported privilege", task, ("authority", "max_side_effect"), "root", t.task_contract),
    ("N13 negative tokens", task, ("budget", "max_tokens"), -1, t.task_contract),
    ("N13 negative cost", task, ("budget", "max_cost_microunits"), -1, t.task_contract),
    ("N13 negative tools", task, ("budget", "max_tool_calls"), -1, t.task_contract),
    ("N13 zero wall", task, ("budget", "max_wall_ms"), 0, t.task_contract),
    ("N13 deadline expired", task, ("deadline_at",), EARLY, t.task_contract),
    (
        "N14 promotion without consent",
        task,
        ("privacy", "allow_memory_promotion"),
        True,
        t.task_contract,
    ),
    (
        "N02 metadata privilege injection",
        task,
        ("metadata",),
        {"max_side_effect": "irreversible"},
        t.task_contract,
    ),
    ("N02 inline secret", task, ("metadata",), {"example:api_key": "x"}, t.task_contract),
    ("unknown workload", task, ("workload_kind",), "supervisor", t.task_contract),
    ("invalid actor type", task, ("actor", "principal_type"), "root", t.task_contract),
    (
        "scope privilege escalation",
        task,
        ("context_scopes",),
        [{"provider_kind": "tool", "scope_id": "x", "access": "execute_write"}],
        t.task_contract,
    ),
    ("missing outcome", task, ("output_specs",), [], t.task_contract),
    (
        "N24 remote validator missing",
        task,
        ("output_specs",),
        [
            {
                "outcome_id": "o",
                "kind": "remote_state",
                "artifact_media_type": None,
                "expected_uri_scope": None,
                "validator_refs": ["tool_string"],
                "required": True,
            }
        ],
        t.task_contract,
    ),
    ("unknown policy field", task, ("evil_policy",), True, t.task_contract),
    ("unsupported currency", task, ("budget", "currency"), "usd", t.task_contract),
    ("N01 cross tenant", bundle, ("items", 0, "tenant_id"), "B", c.context_bundle),
    ("N16 source revision missing", item, ("source_revision",), "", c.context_item),
    ("N16 source locator missing", item, ("source_locator",), None, c.context_item),
    ("N14 stale memory consent", item, ("kind",), "memory", c.context_item),
    ("context expiry", item, ("expires_at",), EARLY, c.context_item),
    ("source digest invalid", item, ("source_digest",), "wrong", c.context_item),
    ("N07 irreversible without approval", cap, ("side_effect",), "irreversible", a.tool_capability),
    ("N05 argument digest invalid", intent, ("arguments_digest",), "bad", a.action_intent),
    ("N06 expired intent", intent, ("expires_at",), EARLY, a.action_intent),
    ("side effect enum escalation", intent, ("side_effect",), "admin", a.action_intent),
    ("N23 compensation unverified", receipt, ("status",), "compensated", a.action_receipt),
    ("unobserved confirmed write", receipt, ("status",), "confirmed_applied", a.action_receipt),
    ("N28 policy hard downgraded", verification, ("hard_gate",), False, v.verification_result),
    ("N27 provisional first text", publication, ("kind",), "provisional", v.publication_event),
    ("N18 correction no supersedes", publication, ("kind",), "correction", v.publication_event),
    (
        "publication absent verification",
        publication,
        ("verification_ids",),
        [],
        v.publication_event,
    ),
]


@pytest.mark.parametrize("label,factory,path,value,validate", NEG, ids=[x[0] for x in NEG])
def test_fail_closed(label, factory, path, value, validate):
    with pytest.raises(t.ContractError):
        validate(mutate(factory(), path, value))


def test_positive_serialization_and_zero_budget():
    obj = t.task_contract(task())
    assert t.canonical(obj) == t.canonical(copy.deepcopy(obj))
    assert t.sha256(obj) == t.sha256(copy.deepcopy(obj))
    assert obj["budget"]["max_tokens"] == 0
    assert a.action_intent(intent()) and a.tool_capability(cap())
    assert c.context_bundle(bundle(), request())
    assert v.verification_result(verification())
    assert v.publication_event(publication())


def test_source_reference_retained():
    result = c.context_item(item())
    assert (
        result["source_id"],
        result["source_revision"],
        result["source_locator"],
        result["source_digest"],
    ) == ("s", "rev", "source://s/rev", D)


def test_N08_key_digest_conflict():
    x = intent()
    y = mutate(x, ("arguments_digest",), "b" * 64)
    with pytest.raises(t.ContractError):
        a.idempotency_compatible(x, y)


def test_N07_action_denied_without_approval():
    with pytest.raises(t.ContractError):
        a.authorize(intent(), cap(), policy_max="none")


def test_N20_capability_tenant_mismatch():
    with pytest.raises(t.ContractError):
        a.authorize(intent(), mutate(cap(), ("tenant_id",), "B"), policy_max="read")


def test_N22_approval_stale_and_N05_digest_binding():
    i = intent()
    i["approval_id"] = "app"
    approval = dict(
        schema_version="1.0.0",
        tenant_id="A",
        approval_id="app",
        intent_digest=t.sha256(i),
        approver_principal="human",
        approver_authority_ref="authority",
        decision="approved",
        decided_at=EARLY,
        expires_at=EARLY,
        one_time=True,
        policy_version="p1",
        created_at=EARLY,
    )
    with pytest.raises(t.ContractError):
        a.authorize(i, cap(), approval, policy_max="read")
    approval["expires_at"] = FUTURE
    approval["intent_digest"] = "b" * 64
    with pytest.raises(t.ContractError):
        a.authorize(i, cap(), approval, policy_max="read")


def test_N09_unknown_not_confirmed():
    x = receipt()
    x["status"] = "unknown"
    assert a.action_receipt(x)["status"] == "unknown"


def test_N12_cancel_unresolved_rejected():
    state = dict(
        schema_version="1.0.0",
        run_id="r",
        task_id="t",
        task_version=1,
        tenant_id="A",
        state="cancelled",
        seq=1,
        attempt=1,
        lease=None,
        checkpoint_ref=None,
        deadline_at=None,
        cancel_requested=True,
        active_action_ids=["uncertain"],
        spent=dict(tokens=0, cost_microunits=0, tool_calls=0, elapsed_ms=0),
        last_event_hash=None,
        updated_at=EARLY,
        ttl_expires_at=FUTURE,
        created_at=EARLY,
    )
    with pytest.raises(t.ContractError):
        r.run_state(state)


def test_N10_N25_transition_and_chain():
    with pytest.raises(t.ContractError):
        r.transition_allowed("succeeded", "running")
    with pytest.raises(t.ContractError):
        r.transition_allowed("unknown_effect", "cancelled")
    with pytest.raises(t.ContractError):
        r.transition_allowed("waiting_approval", "running")


def test_N17_hard_gate_blocks_soft_pass():
    hard = mutate(verification(), ("result",), "fail")
    soft = mutate(verification(), ("kind",), "semantic_claim")
    soft["hard_gate"] = False
    assert v.verification_result(hard)["result"] == "fail"
    assert v.verification_result(soft)["result"] == "pass"
    assert not all(q["result"] == "pass" for q in (hard, soft) if q["hard_gate"])


def test_N13_context_budget():
    b = bundle()
    b["token_count"] = 1
    with pytest.raises(t.ContractError):
        c.context_bundle(b, request())


def test_unknown_enum_compatibility():
    with pytest.raises(t.ContractError):
        v.verification_result(mutate(verification(), ("kind",), "model_override"))


def test_checkpoint_canonical():
    x = dict(
        schema_version="1.0.0",
        checkpoint_id="cp",
        run_id="r",
        seq=1,
        attempt=1,
        lease_epoch=1,
        workspace_snapshot_ref="ws",
        planner_state_digest=D,
        pending_action_ids=[],
        provider_version_refs=[],
        created_at=EARLY,
        expires_at=FUTURE,
        digest=D,
    )
    assert r.checkpoint(x) == x
    with pytest.raises(t.ContractError):
        r.checkpoint({**x, "state_digest": D})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_boundaries(bad):
    with pytest.raises(t.ContractError):
        t.task_contract(mutate(task(), ("metadata",), {"measure": bad}))
    for k in ("value", "scale_max"):
        x = verification()
        x["score"] = {"value": 1, "scale_max": 5, "rubric_version": "v1"}
        x["score"][k] = bad
        with pytest.raises(t.ContractError):
            v.verification_result(x)


def test_capability_scope_and_deny():
    assert a.tool_capability(cap()) == cap()
    with pytest.raises(t.ContractError):
        a.tool_capability({**cap(), "operations": ["read"]})
    with pytest.raises(t.ContractError):
        a.tool_capability({**cap(), "tenant_binding": "*", "privilege": "write"})
    with pytest.raises(t.ContractError):
        a.authorize(intent(), cap(), policy_max="read")
