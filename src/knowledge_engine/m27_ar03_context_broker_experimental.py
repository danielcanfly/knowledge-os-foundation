"""EXPERIMENTAL_NO_LIVE_PROVIDER. Deterministic fake ContextBroker, no remote effects."""

import re
from dataclasses import dataclass

EXPERIMENTAL_NO_LIVE_PROVIDER = True
TRUST = {"untrusted": 0, "source_attested": 1, "governed": 2}
HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Request:
    tenant: str
    principal: str
    purpose: str
    scopes: frozenset[str]
    now: int
    tokens: int
    cost: int
    freshness: int
    trust_floor: str = "untrusted"


@dataclass(frozen=True)
class GrantFixture:
    tenant: str
    principal: str
    purpose: str
    scopes: frozenset[str]
    expires: int
    externally_authenticated: bool = False


@dataclass(frozen=True)
class Candidate:
    scope: str
    source_id: str
    revision: str
    digest: str
    tenant: str
    principals: frozenset[str]
    purpose: str
    expires: int
    retrieved: int
    tokens: int
    cost: int | None
    trust: str = "untrusted"
    tainted: bool = False
    consent_expires: int | None = None
    revoked: bool = False
    skill: bool = False
    signed: bool = False
    citation_offsets_safe: bool = True
    synthetic_native: bool = False


@dataclass(frozen=True)
class Result:
    selected: tuple[Candidate, ...]
    omissions: tuple[tuple[str, str], ...]
    tokens: int
    cost: int
    expires: int


def select(
    req: Request, candidates: tuple[Candidate, ...], grant: GrantFixture | None = None
) -> Result:
    """No model instructions or signed authorization are established by this mock."""
    if min(req.tokens, req.cost, req.freshness) < 0 or req.trust_floor not in TRUST:
        raise ValueError("invalid budget or trust")
    admitted = bool(
        grant
        and grant.externally_authenticated
        and grant.expires > req.now
        and grant.tenant == req.tenant
        and grant.principal == req.principal
        and grant.purpose == req.purpose
        and req.scopes <= grant.scopes
    )
    chosen = []
    omissions = []
    seen = {}
    used_tokens = used_cost = 0
    for c in sorted(candidates, key=lambda x: (x.scope, x.source_id, x.revision, x.digest)):
        reason = None
        if not admitted or c.scope not in req.scopes:
            reason = "unauthorized_scope"
        elif c.tenant != req.tenant or req.principal not in c.principals:
            reason = "acl_denied"
        elif c.purpose != req.purpose:
            reason = "policy_denied"
        elif c.revoked or (c.consent_expires is not None and c.consent_expires <= req.now):
            reason = "consent_expired"
        elif c.expires <= req.now or c.retrieved > req.now or req.now - c.retrieved > req.freshness:
            reason = "stale"
        elif not c.revision:
            reason = "source_revision_missing"
        elif not HEX.fullmatch(c.digest):
            reason = "invalid_digest"
        elif c.trust not in TRUST or TRUST[c.trust] < TRUST[req.trust_floor]:
            reason = "trust_below_floor"
        elif c.synthetic_native or (c.skill and not c.signed) or not c.citation_offsets_safe:
            reason = "policy_denied"
        elif c.cost is None or min(c.tokens, c.cost) < 0:
            reason = "budget_exhausted"
        elif (c.scope, c.source_id) in seen:
            reason = "duplicate" if seen[c.scope, c.source_id] == c.digest else "invalid_digest"
        elif used_tokens + c.tokens > req.tokens or used_cost + c.cost > req.cost:
            reason = "budget_exhausted"
        else:
            seen[c.scope, c.source_id] = c.digest
            chosen.append(c)
            used_tokens += c.tokens
            used_cost += c.cost
        if reason:
            omissions.append((c.scope, reason))
    return Result(
        tuple(chosen),
        tuple(omissions),
        used_tokens,
        used_cost,
        min((c.expires for c in chosen), default=req.now),
    )


def preserve_native_pin(
    original_id: str,
    original_digest: str,
    new_id: str,
    new_digest: str,
    verified_external_pin: bool = False,
) -> str | None:
    """Only an identity assertion, not independent validation of evidence bytes."""
    if (
        verified_external_pin
        and original_id
        and original_id == new_id
        and HEX.fullmatch(original_digest)
        and original_digest == new_digest
    ):
        return original_id
    return None
