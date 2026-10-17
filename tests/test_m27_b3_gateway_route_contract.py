"""B3-01 offline fixtures only, never real Gateway calls."""
import importlib.util
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "src/knowledge_engine/m27_b3_gateway_route_spec.py"
spec = importlib.util.spec_from_file_location("m27_b3_gateway_route_spec", p)
m = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = m
spec.loader.exec_module(m)

def registry():
    return dict(
        primary_kind=m.PRIMARY, fallback_kind=m.FALLBACK,
        route_id="OWNER-NONSECRET-FIXTURE-ONLY", gateway_hostname="fixture-gateway.example", config_sha256="a"*64,
        deployment_label="fixture-not-real", endpoint_class="owner_custom_worker_hostname",
        worker_gateway_deployed=True, upstream_model_id="provider/model-fixture",
        request_schema_id="req.v1", response_schema_id="resp.v1",
        sse_schema_id="sse.v1", principal_propagation="asserted-not-proven",
        source_rights_check="asserted-not-proven",
        timeout_policy="bounded", quota_policy="bounded",
        rate_error_mapping="declared", owner_custodian="fixture-owner",
        config_authority_ref="fixture-reference", feature_flag="fixture-flag",
        fallback_on_auth_failure=False, fallback_after_answer_text=False,
        upstream_identity_origin="custodian_verified_nonsecret",
    )

def fixture_trace():
    base=dict(provider=m.PRIMARY,upstream_model_id="provider/model-fixture",
              tenant="tenant-fixture",principal="principal-fixture")
    items=[
      ("provider_open",{}),
      ("provider_text_delta",{"text":"fixture generated text only"}),
      ("claim_verified",{"claim_id":"a","rights_valid":True,"source_sha256_valid":True}),
      ("answer_text",{"claim_id":"a","text_sha256":"b"*64}),
      ("client_ack",{"claim_id":"a","http_status":200}),
      ("claim_verified",{"claim_id":"b","rights_valid":True,"source_sha256_valid":True}),
      ("answer_text",{"claim_id":"b","text_sha256":"c"*64}),
      ("client_ack",{"claim_id":"b","http_status":200}),
      ("provider_done",{}),
      ("terminal",{"answer_complete":True,"status":"answered"}),
    ]
    return [dict(base,kind=kind,t_ns=i+1,**rest) for i,(kind,rest) in enumerate(items)]

def trace_result(events):
    return m.audit_client_trace_shape(
        events,expected_claim_ids=("a","b"),
        expected_upstream_model_id="provider/model-fixture",
        expected_tenant="tenant-fixture",expected_principal="principal-fixture"
    )

def test_good_registry_is_only_offline_shape():
    x=m.audit_route_registry(registry())
    assert x.shape_valid and not x.product_admitted and x.evidence_scope.startswith("OFFLINE")

def test_direct_workers_ai_not_custom_gateway():
    r=registry();r["endpoint_class"]="cloudflare_account_workers_ai_direct"
    assert "NOT_OWNER_CUSTOM_WORKER_ENDPOINT" in m.audit_route_registry(r).problems

def test_minimax_cannot_be_primary():
    r=registry();r["primary_kind"]="minimax"
    assert "PRIMARY_MUST_BE_OWNER_CUSTOM_WORKER_GATEWAY" in m.audit_route_registry(r).problems

def test_no_model_identity_not_admitted():
    r=registry();r["upstream_model_id"]="unknown"
    assert not m.audit_route_registry(r).shape_valid

def test_unauthorized_upstream_identity():
    r=registry();r["upstream_identity_origin"]="guessed_from_brand"
    assert "UPSTREAM_MODEL_NOT_CUSTODIAN_VERIFIED" in m.audit_route_registry(r).problems

def test_no_gateway_deployment_evidence():
    r=registry();r["worker_gateway_deployed"]=False
    assert "NO_DEPLOYMENT_EVIDENCE" in m.audit_route_registry(r).problems

def test_no_auth_fallback_bypass():
    r=registry();r["fallback_on_auth_failure"]=True
    assert "AUTH_FAILURE_FALLBACK_FORBIDDEN" in m.audit_route_registry(r).problems

def test_no_partial_stream_fallback_bypass():
    r=registry();r["fallback_after_answer_text"]=True
    assert "POST_ANSWER_FAILOVER_FORBIDDEN" in m.audit_route_registry(r).problems

def test_no_credential_values_in_contract():
    r=registry();r["credential_value"]="DO_NOT_RECORD"
    assert "CREDENTIAL_VALUE_MUST_NEVER_ENTER_REGISTRY" in m.audit_route_registry(r).problems

def test_trace_good_fixture_still_not_product():
    x=trace_result(fixture_trace())
    assert x.shape_valid and not x.product_admitted

def test_http200_done_no_delta_fails():
    events=[e for e in fixture_trace() if e["kind"]!="provider_text_delta"]
    assert "NO_PROVIDER_TEXT_DELTA" in trace_result(events).problems

def test_wrong_actual_model_fails():
    events=fixture_trace();events[1]["upstream_model_id"]="wrong-model"
    assert "ACTUAL_UPSTREAM_MISMATCH" in trace_result(events).problems

def test_wrong_principal_fails():
    events=fixture_trace();events[2]["principal"]="other"
    assert "TENANT_PRINCIPAL_MISMATCH" in trace_result(events).problems

def test_source_revoked_fails():
    events=fixture_trace();events[2]["rights_valid"]=False
    assert "UNVERIFIED_SOURCE_RIGHTS" in trace_result(events).problems

def test_missing_obligation_fails():
    events=[e for e in fixture_trace() if e.get("claim_id")!="b"]
    assert "VERIFIED_OBLIGATIONS_INCOMPLETE_OR_OUT_OF_ORDER" in trace_result(events).problems

def test_missing_ack_fails():
    events=[e for e in fixture_trace() if not (e["kind"]=="client_ack" and e["claim_id"]=="b")]
    assert "ACKED_OBLIGATIONS_INCOMPLETE_OR_OUT_OF_ORDER" in trace_result(events).problems

def test_publish_before_verify_fails():
    events=fixture_trace();events[2],events[3]=events[3],events[2]
    assert "PUBLISH_BEFORE_VERIFICATION" in trace_result(events).problems

def test_late_ack_after_terminal_fails():
    events=fixture_trace();events[-1],events[-2]=events[-2],events[-1]
    assert not trace_result(events).shape_valid

def test_fake_ack_fails():
    events=fixture_trace();events[4]["http_status"]=0
    assert "INVALID_CLIENT_ACK" in trace_result(events).problems

def test_nonmonotonic_fails():
    events=fixture_trace();events[5]["t_ns"]=2
    assert "TIMESTAMPS_NOT_STRICT_MONOTONIC" in trace_result(events).problems

def test_unverified_final_answer_fails():
    events=fixture_trace();events[-1]["answer_complete"]=False
    assert "FULL_ANSWER_NOT_PROVEN" in trace_result(events).problems

def test_product_gates_always_hold():
    assert len(m.product_acceptance_matrix())==4
    assert all(v.startswith("HOLD_") for v in m.product_acceptance_matrix().values())

def test_direct_api_hostname_spoofed_custom_class_fails():
    r=registry();r["gateway_hostname"]="api.cloudflare.com"
    assert "GATEWAY_HOSTNAME_INVALID_OR_VENDOR_DIRECT" in m.audit_route_registry(r).problems

def test_vendor_minimax_hostname_not_gateway():
    r=registry();r["gateway_hostname"]="api.minimax.io"
    assert not m.audit_route_registry(r).shape_valid

def test_gateway_hostname_with_embedded_auth_rejected():
    r=registry();r["gateway_hostname"]="user@demo.example"
    assert not m.audit_route_registry(r).shape_valid

def test_empty_provider_delta_fails():
    events=fixture_trace();events[1]["text"]=""
    assert "NO_SUBSTANTIVE_PROVIDER_DELTA" in trace_result(events).problems

def test_progress_only_delta_fails():
    events=fixture_trace();events[1]["kind"]="progress"
    assert "NO_PROVIDER_TEXT_DELTA" in trace_result(events).problems

def test_duplicate_terminal_fails():
    events=fixture_trace(); events.insert(-1,dict(events[-1],t_ns=9))
    assert "PROVIDER_EVENT_CARDINALITY_INVALID" in trace_result(events).problems

def test_duplicate_provider_done_fails():
    events=fixture_trace();events.insert(-1,dict(events[-2],t_ns=9))
    assert "PROVIDER_EVENT_CARDINALITY_INVALID" in trace_result(events).problems

def test_delta_after_provider_done_fails():
    events=fixture_trace();events.insert(-1,dict(events[1],t_ns=9))
    assert "DELTA_AFTER_PROVIDER_DONE" in trace_result(events).problems

def test_true_model_identity_never_inferred_from_cloudflare_brand():
    r=registry();r["upstream_identity_origin"]="inferred_cloudflare_is_a_model"
    assert "UPSTREAM_MODEL_NOT_CUSTODIAN_VERIFIED" in m.audit_route_registry(r).problems


def test_b302_published_provider_constant_agrees():
    # Published B3-02 ABI m27.b3.provider-router/v1.
    assert m.PRIMARY == "cloudflare_custom_worker_gateway"
    assert m.FALLBACK == "minimax"

def test_missing_gateway_hostname_fails_closed():
    r=registry();r.pop("gateway_hostname")
    assert not m.audit_route_registry(r).shape_valid
