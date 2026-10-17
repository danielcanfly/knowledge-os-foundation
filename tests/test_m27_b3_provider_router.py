"""B3-02 deterministic policy acceptance. No actual provider, model, key, or Production test."""
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

try:
    import pytest
except ImportError:  # deterministic stdlib-only runner for isolated MacBook runtime
    import re
    from contextlib import contextmanager
    from types import SimpleNamespace
    @contextmanager
    def _raises(exc, match=None):
        try:
            yield
        except exc as e:
            if match and not re.search(match, str(e)):
                raise AssertionError("wrong exception message") from e
        else:
            raise AssertionError(f"expected {exc.__name__}")
    class _Approx:
        def __init__(self, value): self.value = value
        def __eq__(self, actual):
            import math
            return math.isclose(self.value, actual, rel_tol=1e-9, abs_tol=1e-9)
    def _parametrize(names, values):
        def decorate(fn):
            fn._fixture_params = (names.split(","), values)
            return fn
        return decorate
    pytest = SimpleNamespace(raises=_raises, approx=_Approx,
                             mark=SimpleNamespace(parametrize=_parametrize))

p = Path(__file__).parents[1] / "src" / "knowledge_engine" / "m27_b3_provider_router.py"
spec = importlib.util.spec_from_file_location("m27_b3_provider_router", p)
import sys
router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = router
spec.loader.exec_module(router)

CF, MM = router.PRIMARY, router.FALLBACK
DIGEST = "a" * 64
SRC = "b" * 64


def task(**kw):
    d = dict(request_id="case-1", task_sha256=DIGEST, tenant="t", principal="p",
             acl_epoch="epoch-1", source_sha256=SRC, source_rights="approved",
             source_region="TW", obligation_ids=("claim_a", "claim_b"),
             citation_ids=("citation-a", "citation-b"),
             estimated_input_tokens=50, max_output_tokens=64,
             fallback_consent=True, fallback_regions=("TW",),
             fallback_terms_approved=True, cache_mode="BYPASS")
    d.update(kw)
    return router.Task(**d)


def meta(name):
    return router.WireEvent(kind="meta", model_id="fixture-CF-upstream" if name == CF else "fixture-MM-upstream")


def claim(ob="claim_a", text="Externally verified synthetic sample.", cite=None):
    return router.WireEvent(kind="claim", obligation_id=ob, text=text,
                            citation_ids=(cite or ("citation-a" if ob == "claim_a" else "citation-b"),))


def done(**kw):
    return router.WireEvent(kind="done", **kw)


def successful(name):
    return [meta(name), claim("claim_a"), claim("claim_b"), done()]


def error(http=0, code="", retry=None):
    return [router.WireEvent(kind="error", http_status=http, error_code=code,
                             retry_after_s=retry)]


class Clock:
    t = 100.0
    def now(self):
        return self.t
    def sleep(self, sec):
        self.t += sec


class FakeTransport:
    def __init__(self, cf=None, mm=None):
        self.responses = {CF: list(cf or []), MM: list(mm or [])}
        self.calls = []
        self.lock = Lock()
    def stream(self, request, timeout_s):
        with self.lock:
            self.calls.append((request, timeout_s))
            if not self.responses[request.provider]:
                raise ConnectionError("fixture no response")
            events = self.responses[request.provider].pop(0)
        if isinstance(events, Exception):
            raise events
        for event in events:
            yield event


class Gate:
    def __init__(self):
        self.allowed = True
        self.reason = ""
        self.epoch = "epoch-1"
        self.source = SRC
        self.rights = "approved"
        self.reads = 0
        self.revoke_at = 0
    def check(self, _task):
        self.reads += 1
        if self.revoke_at and self.reads >= self.revoke_at:
            self.allowed = False
            self.reason = "REVOKED"
        return router.Rights(self.allowed, self.reason, self.epoch, self.source, self.rights)


class Verifier:
    def __init__(self, accepted=True, changed_hash=None, changed_cite=None):
        self.accepted = accepted
        self.changed_hash = changed_hash
        self.changed_cite = changed_cite
        self.calls = []
    def verify(self, task, event, provider, upstream_model):
        self.calls.append((provider, upstream_model, event.obligation_id))
        return router.Proof(self.accepted, "fixture_only", event.obligation_id,
                            self.changed_hash or task.source_sha256,
                            self.changed_cite or event.citation_ids, False)


def setup(cf=None, mm=None, config=None, gate=None, verifier=None, publish=None):
    clock = Clock()
    trans = FakeTransport(cf, mm)
    gate = gate or Gate()
    verifier = verifier or Verifier()
    ctl = router.Router(config or router.RouteConfig(), trans, gate, verifier,
                        now=clock.now, sleep=clock.sleep, publish=publish)
    return ctl, trans, gate, verifier, clock


def used(trans):
    return [p.provider for p, _ in trans.calls]


def test_route_contract_fixed_primary_and_fallback():
    assert router.ABI == "m27.b3.provider-router/v1"
    with pytest.raises(ValueError, match="PROVIDER_ORDER"):
        router.RouteConfig(primary=MM, fallback=CF)
    with pytest.raises(ValueError, match="UNBOUNDED_ATTEMPTS"):
        router.RouteConfig(max_fallback_attempts=2)


def test_default_route_unverified_and_product_denied():
    ctl, trans, *_ = setup([successful(CF)])
    out = ctl.route(task())
    assert out.status == "answered" and out.route_provenance == "UNVERIFIED_TEST_ONLY"
    assert out.attempted[0].actual_upstream_model_id == "fixture-CF-upstream"
    assert out.actual_cost_usd is None and out.actual_input_tokens is None
    ctl2, trans2, *_ = setup([successful(CF)], config=router.RouteConfig(mode="product",
                                      provenance_verified=True, signed_policy_digest=DIGEST))
    out2 = ctl2.route(task())
    assert out2.reason == "CONFIG" and not trans2.calls


def test_primary_healthy_never_uses_fallback():
    ctl, trans, gate, verifier, clock = setup([successful(CF)], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "answered"
    assert used(trans) == [CF]
    assert out.fallback_reason is None
    assert out.text.count("Externally verified") == 2
    assert out.first_text_monotonic <= out.terminal_monotonic
    assert verifier.calls[0][1] == "fixture-CF-upstream"


@pytest.mark.parametrize("problem,reason", [
    (ConnectionError("offline"), "UNAVAILABLE"),
    (TimeoutError("timed out"), "TIMEOUT"),
    (error(502), "UPSTREAM_5XX"),
    (error(429, retry=0.5), "QUOTA"),
])
def test_approved_operational_failover(problem, reason):
    ctl, trans, *_ = setup([problem, problem], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "answered"
    assert used(trans) == [CF, CF, MM]
    assert out.primary_error_class == reason
    assert out.fallback_reason == reason


@pytest.mark.parametrize("problem,reason", [
    (error(401), "AUTH"),
    (error(403), "AUTH"),
    (error(400), "CONFIG"),
    (error(422), "CONFIG"),
    (error(0, "ACL_DENIED"), "ACL"),
    (error(0, "SOURCE_REVOKED"), "REVOKED"),
    (error(0, "RIGHTS_DENIED"), "RIGHTS"),
    (error(0, "PRIVACY_DENIED"), "PRIVACY"),
    (error(0, "VERIFICATION_FAILED"), "VERIFIER"),
    (error(418), "UNKNOWN"),
])
def test_security_and_configuration_fail_closed(problem, reason):
    ctl, trans, *_ = setup([problem], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "safe_abstention" and out.reason == reason
    assert used(trans) == [CF]


@pytest.mark.parametrize("kw", [
    dict(fallback_consent=False), dict(fallback_terms_approved=False),
    dict(fallback_regions=("EU",)), dict(cancelled=True),
    dict(source_region=""), dict(has_side_effects=True),
])
def test_no_fallback_without_scope_and_no_side_effect_replay(kw):
    ctl, trans, *_ = setup([error(503)] * 2, [successful(MM)])
    out = ctl.route(task(**kw))
    assert out.status == "safe_abstention"
    assert MM not in used(trans)


def test_healthy_gateway_even_if_minimax_also_configured():
    ctl, trans, *_ = setup([successful(CF)], [error(503)])
    assert ctl.route(task()).status == "answered"
    assert used(trans) == [CF]


def test_fake_200_done_without_text_is_not_generated_answer():
    ctl, trans, *_ = setup([[meta(CF), done()]], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "safe_abstention" and out.reason == "EMPTY_GENERATION"
    assert used(trans) == [CF] and out.emitted == []


@pytest.mark.parametrize("events,reason", [
    ([meta(CF), claim("claim_a"), done()], "OBLIGATION"),
    ([meta(CF), claim("claim_a"), claim("claim_a"), done()], "OBLIGATION"),
    ([meta(CF), claim("claim_a", cite="invalid-id"), done()], "VERIFIER"),
    ([claim("claim_a"), done()], "PROVIDER_PROTOCOL"),
    ([meta(CF), claim("claim_a"), error(502)[0]], "UPSTREAM_5XX"),
])
def test_partial_verified_first_text_never_fails_over(events, reason):
    ctl, trans, *_ = setup([events], [successful(MM)])
    out = ctl.route(task())
    assert out.status in ("safe_abstention", "partial_terminated")
    assert out.reason == reason
    assert used(trans) == [CF]


def test_invalid_semantic_claim_refused_no_provider_laundering():
    v = Verifier(accepted=False)
    ctl, trans, _, _, _ = setup([successful(CF)], [successful(MM)], verifier=v)
    out = ctl.route(task())
    assert out.reason == "VERIFIER" and out.emitted == []
    assert used(trans) == [CF]


def test_source_citation_or_entailment_mismatch_refused():
    for verifier in [Verifier(changed_hash="x" * 64), Verifier(changed_cite=("citation-b",))]:
        ctl, trans, *_ = setup([successful(CF)], [successful(MM)], verifier=verifier)
        assert ctl.route(task()).reason == "VERIFIER"
        assert used(trans) == [CF]


def test_preflight_acl_source_tenant_isolation():
    for attr, val in [("epoch", "new-epoch"), ("source", "z" * 64),
                      ("rights", "expired"), ("allowed", False)]:
        gate = Gate()
        setattr(gate, attr, val)
        ctl, trans, *_ = setup([successful(CF)], [successful(MM)], gate=gate)
        assert ctl.route(task()).status == "safe_abstention"
        assert used(trans) == []


def test_revocation_midstream_after_first_answer_aborts_no_fallback():
    gate = Gate()
    gate.revoke_at = 6
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], gate=gate)
    out = ctl.route(task())
    assert out.status == "partial_terminated"
    assert out.reason == "REVOKED"
    assert used(trans) == [CF]


def test_bad_retry_after_over_cap_does_not_sleep_unbounded():
    ctl, trans, _, _, clock = setup([error(429, retry=999)], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "answered"
    assert used(trans) == [CF, MM]
    assert clock.t == 100.0


def test_retry_after_within_cap_observed():
    ctl, trans, _, _, clock = setup([error(429, retry=0.8), successful(CF)], [successful(MM)])
    out = ctl.route(task())
    assert out.status == "answered"
    assert used(trans) == [CF, CF]
    assert clock.t == pytest.approx(100.8)


def test_quota_circuit_opens_and_cooldown_one_probe():
    c = router.RouteConfig(max_primary_attempts=1, circuit_threshold=2, circuit_cooldown_s=10)
    ctl, trans, _, _, clock = setup([error(502), error(502), successful(CF)], [successful(MM)] * 4, config=c)
    assert ctl.route(task()).status == "answered"
    assert ctl.route(task(request_id="case-2")).status == "answered"
    assert ctl.route(task(request_id="case-3")).primary_error_class == "CIRCUIT_OPEN"
    assert used(trans) == [CF, MM, CF, MM, MM]
    clock.t += 11
    assert ctl.route(task(request_id="case-4")).status == "answered"
    assert used(trans)[-1] == CF


def test_both_providers_offline_truthful_abstain():
    ctl, trans, *_ = setup([ConnectionError(), ConnectionError()], [TimeoutError()])
    out = ctl.route(task())
    assert out.status == "safe_abstention" and out.reason == "TIMEOUT"
    assert out.fallback_reason == "UNAVAILABLE"
    assert used(trans) == [CF, CF, MM]


def test_cache_bypass_preserved_on_failover_request():
    ctl, trans, *_ = setup([error(503), error(503)], [successful(MM)])
    out = ctl.route(task(cache_mode="BYPASS"))
    assert out.status == "answered"
    assert all(request.cache_mode == "BYPASS" for request, _ in trans.calls)


def test_model_identity_pinning_mismatch_is_fatal_config():
    conf = router.RouteConfig(approved_model_ids={CF: ("approved-model-from-verified-nonsecret-config",)})
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], config=conf)
    out = ctl.route(task())
    assert out.reason == "CONFIG" and used(trans) == [CF]


def test_actual_usage_observed_not_estimated_and_cost_telemetry():
    cf = [[meta(CF), claim("claim_a"), claim("claim_b"),
           done(input_tokens=120, output_tokens=40, cost_usd=0.004)]]
    ctl, trans, *_ = setup(cf, [])
    out = ctl.route(task())
    assert out.status == "answered" and out.actual_input_tokens == 120
    assert out.actual_output_tokens == 40 and out.actual_cost_usd == 0.004


def test_token_budget_fail_closed_before_calls():
    conf = router.RouteConfig(max_total_attempt_tokens=50)
    ctl, trans, *_ = setup([successful(CF)], config=conf)
    out = ctl.route(task())
    assert out.reason == "BUDGET" and not trans.calls


def test_attempt_timeout_deadline_stops_before_fallback():
    clock = Clock()
    class Slow:
        calls = []
        def stream(self, request, timeout_s):
            self.calls.append(request.provider)
            clock.t += 100
            yield meta(request.provider)
    trans = Slow()
    ctl = router.Router(router.RouteConfig(total_deadline_s=10), trans, Gate(), Verifier(),
                        now=clock.now, sleep=clock.sleep)
    out = ctl.route(task())
    assert out.status == "safe_abstention"
    assert trans.calls == [CF] and out.reason == "TIMEOUT"


def test_capability_gap_only_when_explicitly_approved_and_authorized():
    conf = router.RouteConfig(allow_approved_capability_gap=True)
    ctl, trans, *_ = setup([], [successful(MM)], config=conf)
    out = ctl.route(task(requested_capability_gap=True))
    assert out.status == "answered" and out.fallback_reason == "CAPABILITY_APPROVED"
    assert used(trans) == [MM]
    ctl2, trans2, *_ = setup([], [successful(MM)])
    assert ctl2.route(task(requested_capability_gap=True)).reason == "CONFIG"
    assert not trans2.calls


def test_unknown_exception_never_authorizes_fallback():
    class BuggyVerifier(Verifier):
        def verify(self, *args):
            raise RuntimeError("not a transport outage")
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], verifier=BuggyVerifier())
    out = ctl.route(task())
    assert out.reason == "UNKNOWN" and used(trans) == [CF]


def test_publish_error_prevents_replay_and_double_delivery():
    published = []
    def callback(ob, text):
        published.append(ob)
        if ob == "claim_b":
            raise RuntimeError("client disconnected")
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], publish=callback)
    out = ctl.route(task())
    assert out.status == "partial_terminated" and used(trans) == [CF]
    assert published == ["claim_a", "claim_b"]


def test_concurrent_half_open_circuit_single_probe():
    circuit = router.Circuit(threshold=1, cooldown=0.1)
    circuit.failure(1.0)
    barrier = Barrier(8)
    def contender(_):
        barrier.wait()
        return circuit.enter(2.0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(contender, range(8)))
    assert sum(results) == 1
    circuit.failure(2.0)
    assert circuit.enter(2.05) is False
    assert circuit.enter(2.11) is True


def test_two_claims_publish_once_per_claim():
    records = []
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)],
                            publish=lambda ob, t: records.append((ob, t)))
    out = ctl.route(task())
    assert out.status == "answered"
    assert [x[0] for x in records] == ["claim_a", "claim_b"]
    assert len(out.emitted) == 2




def test_cancelled_during_stream_no_replay():
    delivered = []
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)],
                            publish=lambda ob, val: delivered.append(ob))
    ctl.cancelled = lambda: bool(delivered)
    out = ctl.route(task())
    assert out.status == "partial_terminated" and out.reason == "CANCELLED"
    assert delivered == ["claim_a"] and used(trans) == [CF]


def test_rights_ledger_exception_denies_before_provider():
    class BrokenGate(Gate):
        def check(self, task):
            raise ConnectionError("rights ledger offline")
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], gate=BrokenGate())
    assert ctl.route(task()).reason == "RIGHTS"
    assert used(trans) == []


def test_billing_idempotency_per_provider_and_retry():
    ctl, trans, *_ = setup([error(503), error(503)], [successful(MM)])
    assert ctl.route(task()).status == "answered"
    keys = [req.billing_idempotency_key for req, _ in trans.calls]
    assert keys[0] == keys[1] and keys[0] != keys[2]
    assert len(keys[0]) == 64


def test_observed_cost_over_limit_terminates_not_replays():
    conf = router.RouteConfig(max_known_cost_usd=0.003)
    ctl, trans, *_ = setup([[meta(CF), claim("claim_a"), claim("claim_b"),
                             done(input_tokens=10, output_tokens=20, cost_usd=0.004)]],
                            [successful(MM)], config=conf)
    out = ctl.route(task())
    assert out.status == "partial_terminated" and out.reason == "BUDGET"
    assert out.actual_cost_usd == 0.004 and used(trans) == [CF]


def test_failed_first_publish_never_replays_due_to_uncertain_delivery():
    delivered = []
    def flaky(ob, text):
        delivered.append(ob)
        raise ConnectionError("possibly delivered to client")
    ctl, trans, *_ = setup([successful(CF)], [successful(MM)], publish=flaky)
    out = ctl.route(task())
    assert out.status == "partial_terminated"
    assert out.client_notified_status == "partial_terminated"
    assert used(trans) == [CF] and len(delivered) == 1




def test_provider_specific_canonicalizers_do_not_conflate_workers_ai():
    good = dict(carrier="custom_cloudflare_worker_gateway", route_id="verified-route-fixture",
                kind="meta", actual_upstream_model_id="fixture-upstream-unverified")
    assert router.canonicalize_custom_cloudflare_gateway(
        good, required_route_id="verified-route-fixture").model_id == "fixture-upstream-unverified"
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        router.canonicalize_custom_cloudflare_gateway(
            dict(good, carrier="workers_ai_direct"), required_route_id="verified-route-fixture")
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        router.canonicalize_custom_cloudflare_gateway(good, required_route_id="other-route")
    with pytest.raises(ValueError, match="NOT_MINIMAX"):
        router.canonicalize_minimax(good)


def test_minimax_output_canonicalizer_does_not_grant_verification():
    provider_text = dict(carrier="minimax", protocol="anthropic_messages",
                         kind="candidate_claim", obligation_id="claim_a",
                         citation_ids=["citation-a"], text="Model produced a candidate")
    event = router.canonicalize_minimax(provider_text)
    assert event.kind == "claim"
    bad = [meta(CF), event, claim("claim_b"), done()]
    ctl, trans, *_ = setup([bad], [successful(MM)], verifier=Verifier(accepted=False))
    out = ctl.route(task())
    assert out.reason == "VERIFIER" and used(trans) == [CF]


def test_canonicalizer_requires_true_model_identity_and_actual_usage_only():
    with pytest.raises(ValueError, match="MISSING_ACTUAL"):
        router.canonicalize_minimax(dict(carrier="minimax", protocol="anthropic_messages",
                                          kind="meta"))
    with pytest.raises(ValueError, match="BAD_OBSERVED_USAGE"):
        router.canonicalize_minimax(dict(carrier="minimax", protocol="anthropic_messages",
                                          kind="done", observed_output_tokens=-1))
    with pytest.raises(ValueError, match="UNSUPPORTED_WIRE"):
        router.canonicalize_minimax(dict(carrier="minimax", protocol="anthropic_messages",
                                          kind="unknown"))
    wire = router.canonicalize_minimax(dict(carrier="minimax", protocol="anthropic_messages",
                                            kind="done"))
    assert wire.input_tokens is None and wire.cost_usd is None


def test_canonicalizer_429_error_preserves_retry_after():
    frame = dict(carrier="custom_cloudflare_worker_gateway",
                 route_id="fixture-route", kind="error", http_status=429,
                 error_code="UPSTREAM_QUOTA", retry_after_s=1.5)
    ev = router.canonicalize_custom_cloudflare_gateway(frame, required_route_id="fixture-route")
    assert router.classify(ev) == router.Failure.QUOTA and ev.retry_after_s == 1.5




def test_non_hex_task_or_source_digest_fails_closed():
    for altered in (dict(task_sha256="Z" * 64), dict(source_sha256="nonhex" * 10 + "xxxx")):
        ctl, trans, *_ = setup([successful(CF)], [successful(MM)])
        out = ctl.route(task(**altered))
        assert out.reason == "CONFIG" and not trans.calls


if __name__ == "__main__":
    import traceback
    success = failure = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        cases = getattr(fn, "_fixture_params", None)
        arguments = cases[1] if cases else [()]
        for idx, args in enumerate(arguments):
            try:
                fn(*(args if isinstance(args, tuple) else (args,)))
                success += 1
                print("PASS", name, idx if cases else "")
            except Exception:
                failure += 1
                print("FAIL", name, idx if cases else "")
                traceback.print_exc()
    print(f"RESULT: {success} passed, {failure} failed; isolated deterministic tests (not live providers)")
    raise SystemExit(1 if failure else 0)
