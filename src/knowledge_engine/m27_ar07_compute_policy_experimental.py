"""AR07 proposal-only budget/routing proof, restricted to synthetic offline fixtures.

No provider adapter, AR02 writer, CAS reservation, real price authority, call
dispatcher, external effect, online learner, or publication authority exists here.
All positive results require a future *independent* AR02 CAS operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

POLICY_VERSION = "c07-offline-v1"
SCHEMA_VERSION = "compute-proposal-v1"
_WORKLOADS = frozenset({"QA-I", "RES-L", "CODE-L", "MOCK-T"})
_RETRY_SAFE = frozenset(
    {
        "timeout_before_dispatch",
        "transient_provider_unavailable",
        "rate_limited",
    }
)


@dataclass(frozen=True, slots=True)
class StreamFrameFixture:
    verified: bool
    substantive_text: bool
    before_terminal: bool
    pinned_citation: bool


@dataclass(frozen=True, slots=True)
class PriceSnapshotFixture:
    snapshot_id: str
    provider_id: str
    model_id: str
    model_version: str
    currency: str
    cost_per_token_microunits: int
    observed_at_ms: int
    expires_at_ms: int
    trusted_fixture: bool


@dataclass(frozen=True, slots=True)
class ProviderCatalogFixture:
    route_id: str
    provider_id: str
    model_id: str
    model_version: str
    supported_workloads: tuple[str, ...]
    residencies: tuple[str, ...]
    privacy_classes: tuple[str, ...]
    available: bool
    observed_at_ms: int
    expires_at_ms: int
    max_request_tokens: int
    supports_verified_citations: bool


@dataclass(frozen=True, slots=True)
class ComputeDecisionInput:
    tenant_id: str
    task_id: str
    run_id: str
    task_version: int
    lease_epoch: int
    workload_kind: Literal["QA-I", "RES-L", "CODE-L", "MOCK-T"]
    phase: str
    now_ms: int
    deadline_at_ms: int
    residency: str
    privacy_class: str
    currency: str
    approved_providers: tuple[str, ...]
    source_revision: str
    authorized_revision: str
    source_grant_valid: bool
    source_expires_at_ms: int
    context_expires_at_ms: int
    budget_version: int
    max_cost_microunits: int
    spent_cost_microunits: int
    reserved_cost_microunits: int
    max_tokens: int
    spent_tokens: int
    reserved_tokens: int
    max_wall_ms: int
    spent_wall_ms: int
    reserved_wall_ms: int
    max_tool_calls: int
    spent_tool_calls: int
    reserved_tool_calls: int
    max_attempts: int
    attempts_used: int
    max_retries: int
    retry_index: int
    request_tokens: int
    request_wall_ms: int
    request_tool_calls: int
    qa_verification_reserve_ms: int
    retrieval_depth: int
    max_retrieval_depth: int
    reflection_steps: int
    max_reflection_steps: int
    agent_count: int
    max_agent_count: int
    failure_class: str | None
    cancelled: bool
    unknown_effect: bool
    billing_uncertain: bool
    late_billing_overrun: bool
    actual_cost_microunits: int | None
    expected_marginal_value: int
    verified_stream_frame: StreamFrameFixture | None


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    schema_version: str
    policy_version: str
    status: str
    reason_codes: tuple[str, ...]
    rejected_routes: tuple[tuple[str, str], ...]
    selected_route_id: str | None
    provider_id: str | None
    model_id: str | None
    model_version: str | None
    price_snapshot_id: str | None
    budget_version: int
    spent_cost_microunits: int
    reserved_cost_microunits: int
    requested_reservation_microunits: int
    requested_token_reservation: int
    requested_wall_reservation_ms: int
    requested_tool_reservation: int
    verified_first_answer_preterminal: bool
    actual_cost_status: str
    actual_cost_microunits: int | None
    economically_certified: bool
    no_external_effect: bool = True


@dataclass(frozen=True, slots=True)
class ComputePolicyProposal:
    status: str
    trace: DecisionTrace
    reservation_cost_microunits: int
    reservation_tokens: int
    reservation_wall_ms: int
    reservation_tool_calls: int
    required_owner_action: str | None
    provider_call_authorized: bool = False
    # Always proposal-only; even RESERVATION_REQUIRED is not an admission or call permit.


@dataclass(frozen=True, slots=True)
class MockAblationCase:
    case_id: str
    workload_kind: str
    policy: Literal["simple", "adaptive"]
    fixture_cost_microunits: int
    fixture_latency_ms: int
    fixture_independently_accepted: bool


def _nat(value: object) -> bool:
    return type(value) is int and value >= 0


def _valid_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(c.isascii() and (c.isalnum() or c in "-_./") for c in value)
    )


def _fresh(start: object, end: object, now: int) -> bool:
    return _nat(start) and _nat(end) and start <= now < end


def _preterminal(frame: object) -> bool:
    return (
        isinstance(frame, StreamFrameFixture)
        and frame.verified is True
        and frame.substantive_text is True
        and frame.before_terminal is True
        and frame.pinned_citation is True
    )


def propose_compute(
    item: ComputeDecisionInput,
    providers: tuple[ProviderCatalogFixture, ...],
    prices: tuple[PriceSnapshotFixture, ...],
) -> ComputePolicyProposal:
    """Deterministic bounded route *proposal*. No external calls or AR02 mutation."""
    selected: ProviderCatalogFixture | None = None
    selected_price: PriceSnapshotFixture | None = None
    rejected: list[tuple[str, str]] = []
    requested_tokens = 0
    requested_cost = 0
    requested_wall = 0
    requested_tools = 0

    observed_cost = item.actual_cost_microunits if _nat(item.actual_cost_microunits) else None
    cost_state = "OBSERVED_NOT_SETTLED" if observed_cost is not None else "UNKNOWN"

    def emit(status: str, reason: str) -> ComputePolicyProposal:
        trace = DecisionTrace(
            schema_version=SCHEMA_VERSION,
            policy_version=POLICY_VERSION,
            status=status,
            reason_codes=(reason,),
            rejected_routes=tuple(rejected),
            selected_route_id=selected.route_id if selected else None,
            provider_id=selected.provider_id if selected else None,
            model_id=selected.model_id if selected else None,
            model_version=selected.model_version if selected else None,
            price_snapshot_id=selected_price.snapshot_id if selected_price else None,
            budget_version=item.budget_version,
            spent_cost_microunits=item.spent_cost_microunits,
            reserved_cost_microunits=item.reserved_cost_microunits,
            requested_reservation_microunits=requested_cost,
            requested_token_reservation=requested_tokens,
            requested_wall_reservation_ms=requested_wall,
            requested_tool_reservation=requested_tools,
            verified_first_answer_preterminal=(
                item.workload_kind == "QA-I" and _preterminal(item.verified_stream_frame)
            ),
            actual_cost_status=cost_state,
            actual_cost_microunits=observed_cost,
            economically_certified=False,
            no_external_effect=True,
        )
        return ComputePolicyProposal(
            status=status,
            trace=trace,
            reservation_cost_microunits=requested_cost,
            reservation_tokens=requested_tokens,
            reservation_wall_ms=requested_wall,
            reservation_tool_calls=requested_tools,
            required_owner_action=(
                "AR02_CAS_RESERVE" if status == "RESERVATION_REQUIRED" else None
            ),
            provider_call_authorized=False,
        )

    # Fail closed before considering route, price, utility or caller preference.
    if not all(
        _valid_id(x)
        for x in (
            item.tenant_id,
            item.task_id,
            item.run_id,
            item.residency,
            item.privacy_class,
            item.currency,
            item.phase,
        )
    ) or not all(
        _nat(x)
        for x in (
            item.task_version,
            item.lease_epoch,
            item.budget_version,
            item.now_ms,
        )
    ):
        return emit("DENY", "INVALID_IDENTITY")

    numeric = (
        item.max_cost_microunits,
        item.spent_cost_microunits,
        item.reserved_cost_microunits,
        item.max_tokens,
        item.spent_tokens,
        item.reserved_tokens,
        item.max_wall_ms,
        item.spent_wall_ms,
        item.reserved_wall_ms,
        item.max_tool_calls,
        item.spent_tool_calls,
        item.reserved_tool_calls,
        item.max_attempts,
        item.attempts_used,
        item.max_retries,
        item.retry_index,
        item.request_tokens,
        item.request_wall_ms,
        item.request_tool_calls,
        item.qa_verification_reserve_ms,
        item.retrieval_depth,
        item.max_retrieval_depth,
        item.reflection_steps,
        item.max_reflection_steps,
        item.agent_count,
        item.max_agent_count,
    )
    if not all(_nat(x) for x in numeric):
        return emit("DENY", "INVALID_BUDGET")
    if item.workload_kind not in _WORKLOADS:
        return emit("DENY", "UNKNOWN_WORKLOAD")
    if item.cancelled:
        return emit("STOP", "CANCELLED")
    if item.unknown_effect or item.failure_class in (
        "unknown_effect",
        "timeout_after_possible_dispatch",
    ):
        return emit("PAUSE", "UNKNOWN_EFFECT_RECONCILE")
    if item.late_billing_overrun:
        return emit("STOP", "LATE_BILLING_OVERRUN")
    if item.billing_uncertain or (
        item.actual_cost_microunits is not None and not _nat(item.actual_cost_microunits)
    ):
        return emit("PAUSE", "BILLING_UNCERTAIN")
    if item.now_ms >= item.deadline_at_ms:
        return emit("STOP", "DEADLINE_EXPIRED")
    if (
        item.source_grant_valid is not True
        or not _valid_id(item.source_revision)
        or item.source_revision != item.authorized_revision
        or not _nat(item.source_expires_at_ms)
        or not _nat(item.context_expires_at_ms)
        or item.now_ms >= min(item.source_expires_at_ms, item.context_expires_at_ms)
    ):
        return emit("DENY", "CONTEXT_STALE_OR_UNAUTHORIZED")
    if item.attempts_used >= item.max_attempts:
        return emit("STOP", "ATTEMPTS_EXHAUSTED")
    if item.retry_index > item.max_retries:
        return emit("STOP", "RETRY_EXHAUSTED")
    if item.retry_index and item.failure_class not in _RETRY_SAFE:
        return emit("STOP", "RETRY_NOT_SAFE")
    if item.request_tokens == 0 or item.request_wall_ms == 0:
        # A pure compute policy is never a tool permit; tool phase remains AR04-owned.
        return emit("DENY", "INVALID_REQUEST")
    if (
        item.agent_count < 1
        or item.agent_count > item.max_agent_count
        or item.retrieval_depth > item.max_retrieval_depth
        or item.reflection_steps > item.max_reflection_steps
    ):
        return emit("DENY", "EXPANSION_CAP")

    if item.workload_kind == "QA-I" and item.qa_verification_reserve_ms <= 0:
        return emit("DENY", "QA_VERIFICATION_RESERVE")

    # First determine authorization and freshness, never score utility before it.
    eligible: list[ProviderCatalogFixture] = []
    for route in providers:
        if not isinstance(route, ProviderCatalogFixture):
            continue
        if not all(
            _valid_id(x)
            for x in (
                route.route_id,
                route.provider_id,
                route.model_id,
                route.model_version,
            )
        ):
            rejected.append(("INVALID_ROUTE", "MALFORMED"))
            continue
        if (
            route.provider_id not in item.approved_providers
            or item.residency not in route.residencies
            or item.privacy_class not in route.privacy_classes
            or item.workload_kind not in route.supported_workloads
            or (item.workload_kind == "QA-I" and route.supports_verified_citations is not True)
        ):
            rejected.append((route.route_id, "AUTHORIZATION_FILTER"))
            continue
        if (
            route.available is not True
            or not _fresh(route.observed_at_ms, route.expires_at_ms, item.now_ms)
            or not _nat(route.max_request_tokens)
        ):
            rejected.append((route.route_id, "CATALOG_UNAVAILABLE_OR_STALE"))
            continue
        eligible.append(route)
    if not eligible:
        return emit("DENY", "NO_ELIGIBLE_ROUTE")

    # Price authority is synthetic ONLY; this cannot reserve money in real AR02.
    for route in eligible:
        quote = next(
            (
                p
                for p in prices
                if isinstance(p, PriceSnapshotFixture)
                and _valid_id(p.snapshot_id)
                and p.provider_id == route.provider_id
                and p.model_id == route.model_id
                and p.model_version == route.model_version
                and p.currency == item.currency
                and item.currency == "MICROUSD"
                and p.trusted_fixture is True
                and _fresh(p.observed_at_ms, p.expires_at_ms, item.now_ms)
                and type(p.cost_per_token_microunits) is int
                and p.cost_per_token_microunits > 0
            ),
            None,
        )
        if quote is None:
            rejected.append((route.route_id, "PRICE_MISSING_EXPIRED_OR_UNTRUSTED"))
            continue
        selected, selected_price = route, quote
        break
    if selected is None or selected_price is None:
        return emit("DENY", "NO_VALID_PRICE")

    requested_tokens = item.request_tokens * item.agent_count
    requested_wall = item.request_wall_ms
    requested_tools = item.request_tool_calls
    requested_cost = requested_tokens * selected_price.cost_per_token_microunits
    if requested_tokens > selected.max_request_tokens:
        return emit("DENY", "MODEL_TOKEN_LIMIT")

    # Exact inclusive comparisons. +1 exceeds limit. No floating point cost.
    if item.spent_tokens + item.reserved_tokens + requested_tokens > item.max_tokens:
        return emit("DENY", "TOKEN_CEILING")
    if (
        item.spent_cost_microunits + item.reserved_cost_microunits + requested_cost
        > item.max_cost_microunits
    ):
        return emit("DENY", "COST_CEILING")
    if item.spent_tool_calls + item.reserved_tool_calls + requested_tools > item.max_tool_calls:
        return emit("DENY", "TOOL_CEILING")
    if (
        item.spent_wall_ms + item.reserved_wall_ms + requested_wall > item.max_wall_ms
        or item.now_ms + requested_wall > item.deadline_at_ms
    ):
        return emit("DENY", "WALL_CEILING")
    if item.workload_kind == "QA-I" and (
        item.spent_wall_ms
        + item.reserved_wall_ms
        + requested_wall
        + item.qa_verification_reserve_ms
        > item.max_wall_ms
        or item.now_ms + requested_wall + item.qa_verification_reserve_ms > item.deadline_at_ms
    ):
        return emit("ABSTAIN", "QA_VERIFICATION_RESERVE")

    if requested_tools > 0:
        # AR07 never acquires a live AR04 permit or proposes a dispatch.
        return emit("DENY", "AR04_PERMIT_REQUIRED")

    # Consumer must obtain AR02-owned CAS at item.budget_version or
    # recompute on conflict. This function makes NO mutation and emits NO call.
    return emit("RESERVATION_REQUIRED", "AR02_CAS_REQUIRED")


def mock_ablation(cases: tuple[MockAblationCase, ...]) -> dict:
    """Small matched synthetic fixture accounting; NOT experimental evidence."""
    result: dict = {"status": "SYNTHETIC_ONLY_NO_PERFORMANCE_CLAIM"}
    aggregates: dict[tuple[str, str], dict] = {}
    pair_index: dict[tuple[str, str], set[str]] = {}
    for item in cases:
        if (
            not isinstance(item, MockAblationCase)
            or not _valid_id(item.case_id)
            or item.workload_kind not in _WORKLOADS
            or item.policy not in ("simple", "adaptive")
            or not _nat(item.fixture_cost_microunits)
            or not _nat(item.fixture_latency_ms)
            or type(item.fixture_independently_accepted) is not bool
        ):
            raise ValueError("Invalid synthetic ablation fixture")
        pair = (item.workload_kind, item.case_id)
        pair_index.setdefault(pair, set())
        if item.policy in pair_index[pair]:
            raise ValueError("Duplicate synthetic case/policy")
        pair_index[pair].add(item.policy)
        key = (item.workload_kind, item.policy)
        obj = aggregates.setdefault(
            key, {"count": 0, "accepted": 0, "total_cost": 0, "total_latency_ms": 0}
        )
        obj["count"] += 1
        obj["accepted"] += int(item.fixture_independently_accepted)
        obj["total_cost"] += item.fixture_cost_microunits
        obj["total_latency_ms"] += item.fixture_latency_ms
    if any(s != {"simple", "adaptive"} for s in pair_index.values()):
        raise ValueError("Ablation requires paired synthetic workload/case IDs")
    for (workload, policy), obj in sorted(aggregates.items()):
        result.setdefault(workload, {})[policy] = {
            **obj,
            "cost_per_accepted": (obj["total_cost"] / obj["accepted"] if obj["accepted"] else None),
            "source": "fixed_mock_fixture_not_real_billing",
        }
    for workload, pair in result.items():
        if workload == "status":
            continue
        simple, adaptive = pair["simple"], pair["adaptive"]

        # Pareto is only a comparison of invented fixture numbers.
        def dominates(a: dict, b: dict) -> bool:
            return (
                a["accepted"] >= b["accepted"]
                and a["total_cost"] <= b["total_cost"]
                and a["total_latency_ms"] <= b["total_latency_ms"]
                and (
                    a["accepted"] > b["accepted"]
                    or a["total_cost"] < b["total_cost"]
                    or a["total_latency_ms"] < b["total_latency_ms"]
                )
            )

        pair["mock_pareto"] = (
            "simple_dominates_fixture"
            if dominates(simple, adaptive)
            else "adaptive_dominates_fixture"
            if dominates(adaptive, simple)
            else "no_fixture_dominance"
        )
    return result
