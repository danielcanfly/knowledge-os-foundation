"""Q33 local-only boundary tests: citation count never substitutes for claim diversity."""
from knowledge_engine.m27_agent_product_runtime import build_agent_native_product_answer
from knowledge_engine.m27_semantic_entailment import EntailmentVerdict, SupportLabel

QUESTION = "How does Kubernetes schedule inference containers?"
FIRST = (
    "Kubernetes schedules model inference containers across compute nodes and coordinates "
    "deployment health across multiple services. It can restart failed application pods "
    "after health probes detect issues, distribute workloads with scheduler constraints, "
    "and let operators specify resource requests and limits. These controls support "
    "service operations but do not automatically guarantee zero downtime or unrestricted "
    "GPU sharing."
)
SECOND = (
    "Kubernetes uses a scheduler to place inference pods onto suitable nodes after "
    "considering requested CPU and memory resources. Cluster operators can configure "
    "node selectors, tolerations, affinity constraints, and quotas for competing "
    "workloads. Deployments and health probes then provide separate operational "
    "mechanisms for recovering unhealthy replicas and controlling rollout changes."
)


def evidence(second=SECOND):
    return (
        {"source_id": "one", "section_id": "k8s-1", "evidence_id": "one-1", "passage_text": FIRST},
        {"source_id": "two", "section_id": "k8s-2", "evidence_id": "two-2", "passage_text": second},
    )


class Provider:
    def __init__(self, unsupported_source=None, empty_reference=False):
        self.unsupported_source = unsupported_source
        self.empty_reference = empty_reference
        self.calls = 0

    def verify(self, claim, passages):
        self.calls += 1
        denied = passages[0].source_id == self.unsupported_source
        label = SupportLabel.UNSUPPORTED if denied else SupportLabel.DIRECT
        ids = () if denied or self.empty_reference else (passages[0].passage_id,)
        return EntailmentVerdict(label, not denied, ids, "Q33-offline-mock", "fixture")


def build(items, provider):
    return build_agent_native_product_answer(
        question=QUESTION, intent_class="factual", evidence=items, semantic_provider=provider
    )


def test_duplicate_claims_from_distinct_sources_fail_closed():
    provider = Provider()
    result = build(evidence(FIRST), provider)
    assert provider.calls == 2
    assert result.publishable is False
    assert "PRODUCT_THIN_SURFACE" in result.gap_taxonomy
    assert "stream_publishable" not in [x["type"] for x in result.state_events]


def test_case_and_whitespace_variant_claims_are_not_distinct():
    result = build(evidence(FIRST.upper().replace(" ", "  ")), Provider())
    assert result.publishable is False
    assert "PRODUCT_THIN_SURFACE" in result.gap_taxonomy


def test_two_independent_substantive_verified_claims_still_publish():
    provider = Provider()
    result = build(evidence(), provider)
    assert provider.calls == 2
    assert result.publishable is True
    assert len(result.answer["citations"]) == 2
    assert result.answer["semantic_verification_receipts"][0]["publication_accepted"] is True
    assert "stream_publishable" in [x["type"] for x in result.state_events]


def test_partial_citation_cannot_rescue_thin_answer():
    first, second = evidence()
    thin_first = dict(first, passage_text="Kubernetes schedules inference pods.")
    result = build((thin_first, second), Provider(unsupported_source="two"))
    assert result.publishable is False
    assert "PRODUCT_THIN_SURFACE" in result.gap_taxonomy
    assert "stream_publishable" not in [x["type"] for x in result.state_events]


def test_rejected_candidate_is_never_cited_in_valid_strong_answer():
    result = build(evidence(), Provider(unsupported_source="two"))
    # Stage30G specifically excludes rejected candidates from final citations.
    assert result.publishable is True
    assert len(result.answer["citations"]) == 1
    assert all(c["source_id"] == "one" for c in result.answer["citations"])


def test_fake_positive_provider_without_bound_reference_is_rejected():
    result = build(evidence(), Provider(empty_reference=True))
    assert result.publishable is False
    assert "UNSUPPORTED_CLAIM_SPAN" in result.gap_taxonomy
    assert "stream_publishable" not in [x["type"] for x in result.state_events]
