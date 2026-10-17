"""M27 B3-02 isolated, fail-closed Cloudflare Worker Gateway PRIMARY routing.

No network implementation, credentials, Production wiring, signing authority or model
qualification is provided. The injected transport and verifier are authoritative only
within their separately established trust domains. Fixture outcomes are TEST ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from threading import Lock
from typing import Callable, Iterable, Mapping, Protocol
import math
import time

ABI = "m27.b3.provider-router/v1"
PRIMARY = "cloudflare_custom_worker_gateway"
FALLBACK = "minimax"


class Failure(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_5XX = "UPSTREAM_5XX"
    QUOTA = "QUOTA"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    CAPABILITY_APPROVED = "CAPABILITY_APPROVED"
    AUTH = "AUTH"
    ACL = "ACL"
    CONFIG = "CONFIG"
    RIGHTS = "RIGHTS"
    REVOKED = "REVOKED"
    PRIVACY = "PRIVACY"
    VERIFIER = "VERIFIER"
    OBLIGATION = "OBLIGATION"
    EMPTY_GENERATION = "EMPTY_GENERATION"
    PROVIDER_PROTOCOL = "PROVIDER_PROTOCOL"
    BUDGET = "BUDGET"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


RETRYABLE = frozenset({Failure.UNAVAILABLE, Failure.TIMEOUT, Failure.UPSTREAM_5XX, Failure.QUOTA, Failure.CIRCUIT_OPEN, Failure.CAPABILITY_APPROVED})
HARD_DENY = frozenset(set(Failure) - set(RETRYABLE))


@dataclass(frozen=True)
class RouteConfig:
    # Only an independently approved, pinned, signed runtime policy may enter Product.
    mode: str = "nonprod_fixture"
    gateway_route_id: str = "UNVERIFIED_TEST_ONLY_CUSTOM_GATEWAY"
    provenance_verified: bool = False
    signed_policy_digest: str = ""
    primary: str = PRIMARY
    fallback: str = FALLBACK
    approved_model_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    max_primary_attempts: int = 2
    max_fallback_attempts: int = 1
    attempt_timeout_s: float = 5.0
    total_deadline_s: float = 18.0
    max_retry_after_s: float = 2.0
    backoff_s: float = 0.05
    circuit_threshold: int = 2
    circuit_cooldown_s: float = 30.0
    max_input_tokens: int = 4096
    max_output_tokens: int = 512
    max_total_attempt_tokens: int = 8192
    max_known_cost_usd: float = 1.0
    allow_approved_capability_gap: bool = False

    def __post_init__(self) -> None:
        if self.primary != PRIMARY or self.fallback != FALLBACK or self.primary == self.fallback:
            raise ValueError("PROVIDER_ORDER_INVARIANT")
        if self.mode not in ("nonprod_fixture", "product"):
            raise ValueError("INVALID_MODE")
        if not (1 <= self.max_primary_attempts <= 3 and self.max_fallback_attempts == 1):
            raise ValueError("UNBOUNDED_ATTEMPTS")
        if not (0 < self.attempt_timeout_s <= self.total_deadline_s <= 120):
            raise ValueError("UNBOUNDED_TIMEOUT")
        if not (0 <= self.backoff_s <= 3 and 0 <= self.max_retry_after_s <= 30):
            raise ValueError("UNBOUNDED_RETRY")
        if not (1 <= self.circuit_threshold <= 10 and 0 < self.circuit_cooldown_s <= 3600):
            raise ValueError("UNBOUNDED_CIRCUIT")
        if min(self.max_input_tokens, self.max_output_tokens, self.max_total_attempt_tokens) <= 0:
            raise ValueError("UNBOUNDED_TOKEN_BUDGET")
        if not math.isfinite(self.max_known_cost_usd) or self.max_known_cost_usd < 0:
            raise ValueError("UNBOUNDED_COST")


@dataclass(frozen=True)
class Task:
    request_id: str
    task_sha256: str
    tenant: str
    principal: str
    acl_epoch: str
    source_sha256: str
    source_rights: str
    source_region: str
    obligation_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    estimated_input_tokens: int
    max_output_tokens: int
    fallback_consent: bool = False
    fallback_regions: tuple[str, ...] = ()
    fallback_terms_approved: bool = False
    cache_mode: str = "BYPASS"
    has_side_effects: bool = False
    cancelled: bool = False
    requested_capability_gap: bool = False


@dataclass(frozen=True)
class ProviderRequest:
    abi: str
    provider: str
    request_id: str
    task_sha256: str
    tenant: str
    principal: str
    acl_epoch: str
    source_sha256: str
    source_rights: str
    billing_idempotency_key: str
    obligation_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    max_output_tokens: int
    cache_mode: str


@dataclass(frozen=True)
class WireEvent:
    kind: str  # meta, claim, done, error; text exists only in claim
    model_id: str = ""
    text: str = ""
    obligation_id: str = ""
    citation_ids: tuple[str, ...] = ()
    http_status: int = 0
    error_code: str = ""
    retry_after_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class Rights:
    allowed: bool
    reason: str = ""
    acl_epoch: str = ""
    source_sha256: str = ""
    source_rights: str = ""


@dataclass(frozen=True)
class Proof:
    accepted: bool
    reason: str
    obligation_id: str
    source_sha256: str
    citation_ids: tuple[str, ...]
    independent_issuer: bool = False


class Transport(Protocol):
    def stream(self, request: ProviderRequest, timeout_s: float) -> Iterable[WireEvent]: ...


class RightsGate(Protocol):
    def check(self, task: Task) -> Rights: ...


class ClaimVerifier(Protocol):
    def verify(self, task: Task, claim: WireEvent, provider: str, upstream_model: str) -> Proof: ...


@dataclass
class Attempt:
    provider_attempted: str
    actual_upstream_model_id: str | None = None
    error_class: str | None = None
    status: str = "started"
    elapsed_s: float | None = None
    observed_input_tokens: int | None = None
    observed_output_tokens: int | None = None
    observed_cost_usd: float | None = None


@dataclass
class Outcome:
    status: str
    reason: str
    primary_error_class: str | None = None
    fallback_reason: str | None = None
    attempted: list[Attempt] = field(default_factory=list)
    emitted: list[tuple[str, str]] = field(default_factory=list)
    client_notified_status: str = "terminal_only"
    first_text_monotonic: float | None = None
    terminal_monotonic: float | None = None
    route_id: str = "UNVERIFIED_TEST_ONLY_CUSTOM_GATEWAY"
    route_provenance: str = "UNVERIFIED_TEST_ONLY"
    actual_cost_usd: float | None = None
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None

    @property
    def text(self) -> str:
        return "\n".join(text for _, text in self.emitted)


class Circuit:
    """One probe per cool-down; no half-open stampede across concurrent callers."""
    def __init__(self, threshold: int, cooldown: float) -> None:
        self.threshold, self.cooldown = threshold, cooldown
        self.failures = 0
        self.opened_at: float | None = None
        self.probing = False
        self.lock = Lock()

    def enter(self, now: float) -> bool:
        with self.lock:
            if self.opened_at is None:
                return True
            if now - self.opened_at < self.cooldown or self.probing:
                return False
            self.probing = True
            return True

    def success(self) -> None:
        with self.lock:
            self.failures = 0
            self.opened_at = None
            self.probing = False

    def failure(self, now: float) -> None:
        with self.lock:
            self.failures += 1
            if self.probing or self.failures >= self.threshold:
                self.opened_at = now
            self.probing = False

    def release(self) -> None:
        with self.lock:
            self.probing = False


def classify(event: WireEvent) -> Failure:
    code = event.error_code.upper()
    if code in ("ACL_DENIED", "TENANT_DENIED"): return Failure.ACL
    if code in ("SOURCE_REVOKED",): return Failure.REVOKED
    if code in ("RIGHTS_DENIED",): return Failure.RIGHTS
    if code in ("PRIVACY_DENIED",): return Failure.PRIVACY
    if code in ("VERIFICATION_FAILED",): return Failure.VERIFIER
    if code in ("CAPABILITY_APPROVED",): return Failure.CAPABILITY_APPROVED
    if event.http_status in (401, 403) or code in ("AUTH_FAILED",): return Failure.AUTH
    if event.http_status == 429: return Failure.QUOTA
    if 500 <= event.http_status <= 599: return Failure.UPSTREAM_5XX
    if event.http_status in (400, 404, 405, 409, 413, 422) or code == "CONFIG_ERROR": return Failure.CONFIG
    if code == "UPSTREAM_TIMEOUT": return Failure.TIMEOUT
    if code == "UPSTREAM_UNAVAILABLE": return Failure.UNAVAILABLE
    return Failure.UNKNOWN


class Router:
    def __init__(self, config: RouteConfig, transport: Transport, rights: RightsGate,
                 verifier: ClaimVerifier, *, now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 publish: Callable[[str, str], None] | None = None,
                 cancelled: Callable[[], bool] = lambda: False) -> None:
        self.config, self.transport, self.rights, self.verifier = config, transport, rights, verifier
        self.now, self.sleep, self.publish = now, sleep, publish or (lambda _ob, _text: None)
        self.cancelled = cancelled
        self.circuit = {PRIMARY: Circuit(config.circuit_threshold, config.circuit_cooldown_s),
                        FALLBACK: Circuit(config.circuit_threshold, config.circuit_cooldown_s)}

    def _allowed(self, task: Task) -> Failure | None:
        c = self.config
        if c.mode == "product":
            # This isolated B3 adapter MUST NEVER independently attest Product admission.
            return Failure.CONFIG
        if (not task.request_id or any(len(d) != 64 or any(c not in '0123456789abcdef' for c in d)
                                       for d in (task.task_sha256, task.source_sha256))):
            return Failure.CONFIG
        if not task.tenant or not task.principal or not task.acl_epoch or not task.source_rights:
            return Failure.ACL
        if not task.source_region: return Failure.PRIVACY
        if not task.obligation_ids or len(set(task.obligation_ids)) != len(task.obligation_ids):
            return Failure.OBLIGATION
        if not task.citation_ids or len(set(task.citation_ids)) != len(task.citation_ids):
            return Failure.VERIFIER
        if task.cancelled: return Failure.CANCELLED
        if task.has_side_effects: return Failure.CONFIG  # no replayable action/tool generation
        if task.cache_mode not in ("AUTO", "BYPASS", "REFRESH"): return Failure.CONFIG
        if task.estimated_input_tokens <= 0 or task.estimated_input_tokens > c.max_input_tokens:
            return Failure.BUDGET
        if task.max_output_tokens <= 0 or task.max_output_tokens > c.max_output_tokens:
            return Failure.BUDGET
        if task.requested_capability_gap and not c.allow_approved_capability_gap:
            return Failure.CONFIG
        return None

    def _rights(self, task: Task) -> Failure | None:
        try:
            state = self.rights.check(task)
        except Exception:
            return Failure.RIGHTS  # fail closed if identity/rights ledger itself fails
        if not state.allowed:
            return Failure.REVOKED if state.reason == "REVOKED" else Failure.RIGHTS
        if (state.acl_epoch != task.acl_epoch or state.source_sha256 != task.source_sha256
                or state.source_rights != task.source_rights):
            return Failure.REVOKED
        return None

    def _fallback_allowed(self, task: Task) -> bool:
        return (task.fallback_consent and task.fallback_terms_approved
                and task.source_region in task.fallback_regions and not task.cancelled
                and not task.has_side_effects)

    def route(self, task: Task) -> Outcome:
        c, started = self.config, self.now()
        outcome = Outcome(status="safe_abstention", reason="UNSTARTED", route_id=c.gateway_route_id,
                          route_provenance=("SIGNED_POLICY_REQUIRE_H02_VALIDATION" if c.provenance_verified
                                            else "UNVERIFIED_TEST_ONLY"))
        observed_cost = 0.0
        known_cost = False
        total_estimated = 0
        actual_in, actual_out = 0, 0
        known_in, known_out = False, False
        publication_attempted = False  # callback may deliver and then raise; never replay

        def finish(status: str, reason: Failure | str) -> Outcome:
            outcome.status = status
            outcome.reason = reason.value if isinstance(reason, Failure) else reason
            outcome.terminal_monotonic = self.now()
            outcome.client_notified_status = ("partial_terminated" if publication_attempted and status != "answered"
                                             else status)
            outcome.actual_cost_usd = observed_cost if known_cost else None
            outcome.actual_input_tokens = actual_in if known_in else None
            outcome.actual_output_tokens = actual_out if known_out else None
            return outcome

        invalid = (Failure.CANCELLED if self.cancelled() else
                   self._allowed(task) or self._rights(task))
        if invalid: return finish("safe_abstention", invalid)

        for provider in (PRIMARY, FALLBACK):
            if self.cancelled():
                return finish('partial_terminated' if publication_attempted else 'safe_abstention', Failure.CANCELLED)
            if provider == FALLBACK:
                if outcome.primary_error_class not in {f.value for f in RETRYABLE}:
                    return finish("safe_abstention", outcome.primary_error_class or "PRIMARY_NOT_QUALIFIED")
                if not self._fallback_allowed(task):
                    return finish("safe_abstention", "FALLBACK_NOT_AUTHORIZED")
                outcome.fallback_reason = outcome.primary_error_class
            elif task.requested_capability_gap:
                outcome.primary_error_class = Failure.CAPABILITY_APPROVED.value
                continue
            for index in range(c.max_primary_attempts if provider == PRIMARY else c.max_fallback_attempts):
                if publication_attempted:
                    return finish("partial_terminated", "NO_SWITCH_AFTER_VERIFIED_FIRST_TEXT")
                invalid = Failure.CANCELLED if self.cancelled() else self._rights(task)
                if invalid: return finish("partial_terminated" if publication_attempted else "safe_abstention", invalid)
                if self.now() - started >= c.total_deadline_s:
                    return finish("safe_abstention", Failure.TIMEOUT)
                if total_estimated + task.estimated_input_tokens + task.max_output_tokens > c.max_total_attempt_tokens:
                    return finish("safe_abstention", Failure.BUDGET)
                if known_cost and observed_cost > c.max_known_cost_usd:
                    return finish("safe_abstention", Failure.BUDGET)
                if not self.circuit[provider].enter(self.now()):
                    failure = Failure.CIRCUIT_OPEN
                    if provider == PRIMARY:
                        outcome.primary_error_class = failure.value
                        break
                    return finish("safe_abstention", failure)
                budget_remaining = c.total_deadline_s - (self.now() - started)
                timeout_s = min(c.attempt_timeout_s, budget_remaining)
                req = ProviderRequest(
                    abi=ABI, provider=provider, request_id=task.request_id,
                    task_sha256=task.task_sha256, tenant=task.tenant,
                    principal=task.principal, acl_epoch=task.acl_epoch,
                    source_sha256=task.source_sha256, source_rights=task.source_rights,
                    billing_idempotency_key=sha256(
                        (task.request_id + '|' + task.task_sha256 + '|' + provider).encode()).hexdigest(),
                    obligation_ids=task.obligation_ids, citation_ids=task.citation_ids,
                    max_output_tokens=task.max_output_tokens, cache_mode=task.cache_mode)
                record = Attempt(provider_attempted=provider)
                outcome.attempted.append(record)
                total_estimated += task.estimated_input_tokens + task.max_output_tokens
                astart = self.now()
                failure: Failure | None = None
                retry_after: float | None = None
                seen_meta = False
                seen_done = False
                seen_obligations: set[str] = set()
                output_chars = 0
                try:
                    for event in self.transport.stream(req, timeout_s):
                        if self.cancelled():
                            failure = Failure.CANCELLED
                            break
                        if self.now() - started >= c.total_deadline_s or self.now() - astart > timeout_s:
                            failure = Failure.TIMEOUT
                            break
                        if event.kind == "error":
                            failure = classify(event)
                            retry_after = event.retry_after_s
                            break
                        if event.kind == "meta":
                            if seen_meta or not event.model_id:
                                failure = Failure.PROVIDER_PROTOCOL
                                break
                            approved = c.approved_model_ids.get(provider)
                            if approved and event.model_id not in approved:
                                failure = Failure.CONFIG
                                break
                            record.actual_upstream_model_id = event.model_id
                            seen_meta = True
                            continue
                        if event.kind == "claim":
                            if not seen_meta or seen_done or not event.text.strip():
                                failure = Failure.PROVIDER_PROTOCOL
                                break
                            if (event.obligation_id not in task.obligation_ids or
                                    event.obligation_id in seen_obligations):
                                failure = Failure.OBLIGATION
                                break
                            if (not event.citation_ids or
                                    not set(event.citation_ids).issubset(task.citation_ids)):
                                failure = Failure.VERIFIER
                                break
                            invalid = self._rights(task)
                            if invalid:
                                failure = invalid
                                break
                            proof = self.verifier.verify(task, event, provider,
                                                         record.actual_upstream_model_id or "")
                            if (not proof.accepted or proof.obligation_id != event.obligation_id
                                    or proof.source_sha256 != task.source_sha256
                                    or proof.citation_ids != event.citation_ids):
                                failure = Failure.VERIFIER
                                break
                            # Fixture-only verifier may validate controls; NOT Product issuer.
                            if c.mode == "product" and not proof.independent_issuer:
                                failure = Failure.VERIFIER
                                break
                            output_chars += len(event.text)
                            if output_chars > task.max_output_tokens * 8:
                                failure = Failure.BUDGET
                                break
                            invalid = self._rights(task)  # right before publishing
                            if invalid:
                                failure = invalid
                                break
                            seen_obligations.add(event.obligation_id)
                            publication_attempted = True
                            self.publish(event.obligation_id, event.text)
                            outcome.emitted.append((event.obligation_id, event.text))
                            if outcome.first_text_monotonic is None:
                                outcome.first_text_monotonic = self.now()
                            continue
                        if event.kind == "done":
                            if not seen_meta or seen_done:
                                failure = Failure.PROVIDER_PROTOCOL
                                break
                            seen_done = True
                            if event.input_tokens is not None:
                                if event.input_tokens < 0: failure = Failure.PROVIDER_PROTOCOL; break
                                record.observed_input_tokens = event.input_tokens
                                actual_in += event.input_tokens
                                known_in = True
                            if event.output_tokens is not None:
                                if event.output_tokens < 0: failure = Failure.PROVIDER_PROTOCOL; break
                                record.observed_output_tokens = event.output_tokens
                                actual_out += event.output_tokens
                                known_out = True
                                if event.output_tokens > task.max_output_tokens:
                                    failure = Failure.BUDGET
                                    break
                            if event.cost_usd is not None:
                                if not math.isfinite(event.cost_usd) or event.cost_usd < 0:
                                    failure = Failure.PROVIDER_PROTOCOL
                                    break
                                record.observed_cost_usd = event.cost_usd
                                observed_cost += event.cost_usd
                                known_cost = True
                                if observed_cost > c.max_known_cost_usd:
                                    failure = Failure.BUDGET
                                    break
                            break
                        failure = Failure.PROVIDER_PROTOCOL
                        break
                    if failure is None and not seen_done:
                        failure = Failure.PROVIDER_PROTOCOL
                    if failure is None and not outcome.emitted:
                        failure = Failure.EMPTY_GENERATION
                    if failure is None and seen_obligations != set(task.obligation_ids):
                        failure = Failure.OBLIGATION
                    if failure is None:
                        invalid = self._rights(task)
                        if invalid: failure = invalid
                except TimeoutError:
                    failure = Failure.TIMEOUT
                except ConnectionError:
                    failure = Failure.UNAVAILABLE
                except Exception:
                    # Exceptions from verifier/transport/publication cannot authorize retry.
                    failure = Failure.UNKNOWN
                finally:
                    record.elapsed_s = max(0.0, self.now() - astart)

                if failure is None:
                    record.status = "answered"
                    self.circuit[provider].success()
                    return finish("answered", "VERIFIED_ALL_OBLIGATIONS")
                record.status = "failed"
                record.error_class = failure.value
                if failure in RETRYABLE:
                    self.circuit[provider].failure(self.now())
                else:
                    self.circuit[provider].release()
                if publication_attempted:
                    return finish("partial_terminated", failure)
                if failure not in RETRYABLE:
                    return finish("safe_abstention", failure)
                if provider == PRIMARY:
                    outcome.primary_error_class = failure.value
                if index + 1 >= (c.max_primary_attempts if provider == PRIMARY else c.max_fallback_attempts):
                    break
                delay = c.backoff_s * (2 ** index)
                if failure == Failure.QUOTA and retry_after is not None:
                    if not math.isfinite(retry_after) or retry_after < 0 or retry_after > c.max_retry_after_s:
                        break
                    delay = max(delay, retry_after)
                if self.now() - started + delay >= c.total_deadline_s:
                    break
                self.sleep(delay)
            # No fallback from MiniMax, ever.
            if provider == FALLBACK:
                return finish("safe_abstention", outcome.attempted[-1].error_class
                              if outcome.attempted else Failure.UNAVAILABLE)
        return finish("safe_abstention", outcome.primary_error_class or Failure.UNKNOWN)


def _canonicalize_strict_envelope(frame: Mapping[str, object]) -> WireEvent:
    """Normalize ONLY an H02-validated typed envelope, never raw model claims as proof.

    H02 owns the actual wire parsers after genuine custom-Gateway schema mapping.
    The parser raises on unknown or structurally ambiguous upstream data.
    """
    kind = frame.get("kind")
    if kind == "meta":
        model = frame.get("actual_upstream_model_id")
        if not isinstance(model, str) or not model:
            raise ValueError("MISSING_ACTUAL_UPSTREAM_MODEL_ID")
        return WireEvent(kind="meta", model_id=model)
    if kind == "candidate_claim":
        obligation = frame.get("obligation_id")
        content = frame.get("text")
        citations = frame.get("citation_ids")
        if (not isinstance(obligation, str) or not obligation
                or not isinstance(content, str) or not content.strip()
                or not isinstance(citations, (tuple, list))
                or not citations or not all(isinstance(c, str) and c for c in citations)):
            raise ValueError("MALFORMED_UNVERIFIED_CLAIM")
        # No 'verified' flag from provider is trusted. Router always re-verifies.
        return WireEvent(kind="claim", text=content, obligation_id=obligation,
                         citation_ids=tuple(citations))
    if kind == "done":
        inputs = frame.get("observed_input_tokens")
        outputs = frame.get("observed_output_tokens")
        cost = frame.get("observed_cost_usd")
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0)
               for v in (inputs, outputs)):
            raise ValueError("BAD_OBSERVED_USAGE")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float))
                                or not math.isfinite(cost) or cost < 0):
            raise ValueError("BAD_OBSERVED_COST")
        return WireEvent(kind="done", input_tokens=inputs, output_tokens=outputs,
                         cost_usd=float(cost) if cost is not None else None)
    if kind == "error":
        status = frame.get("http_status", 0)
        reason = frame.get("error_code", "")
        retry = frame.get("retry_after_s")
        if (isinstance(status, bool) or not isinstance(status, int) or status < 0
                or not isinstance(reason, str) or
                (retry is not None and (isinstance(retry, bool) or
                                        not isinstance(retry, (int, float)) or
                                        not math.isfinite(retry)))):
            raise ValueError("MALFORMED_TRANSPORT_ERROR")
        return WireEvent(kind="error", http_status=status, error_code=reason,
                         retry_after_s=float(retry) if retry is not None else None)
    raise ValueError("UNSUPPORTED_WIRE_EVENT")


def canonicalize_custom_cloudflare_gateway(
        frame: Mapping[str, object], *, required_route_id: str) -> WireEvent:
    """TEST-ONLY canonical envelope for actual CUSTOM Gateway (never Workers AI direct).

    Does NOT assert that any live Gateway emits this shape. H02 must provide
    a separately admitted raw->envelope mapper and verify route authentication.
    """
    if (frame.get("carrier") != "custom_cloudflare_worker_gateway"
            or frame.get("route_id") != required_route_id
            or not required_route_id or required_route_id == "workers_ai_direct"):
        raise ValueError("NOT_AUTHORIZED_CUSTOM_GATEWAY_ROUTE")
    return _canonicalize_strict_envelope(frame)


def canonicalize_minimax(
        frame: Mapping[str, object]) -> WireEvent:
    """TEST-ONLY MiniMax Anthropic-family envelope, not a model issuer."""
    if (frame.get("carrier") != "minimax"
            or frame.get("protocol") != "anthropic_messages"):
        raise ValueError("NOT_MINIMAX_WIRE")
    return _canonicalize_strict_envelope(frame)
