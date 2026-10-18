"""S03 local delivery boundary for REAL A05 bytes, not a Product IdP grant.

Owner-only, local source-candidate proof. This is intentionally incapable of
issuing, verifying, or elevating real remote identity, licensing or Store access.
A caller-supplied context / epoch floor is never an independent Product receipt.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

import m27_f03_source_rights_admission as f03

_LOCAL_CHANNEL = "owner-os-local-nonprod"
_CONTEXT_KEYS = frozenset({"client_id", "session_nonce", "tenant", "principal", "channel"})
_NO_PRODUCT = {
    "product_authenticated": False, "product_admitted": False,
    "verified_final": False, "independent_issuer": False,
    "answer_cache_enabled": False, "answer_cache_hit": False,
    "answer_cache_write": False, "cache_mode": "BYPASS",
    "remote_store_authorized": False, "remote_revocation_authorized": False,
    "candidate_only": False,
}


def _deny(code: str) -> dict:
    return {"decision": "DENY_" + code, **_NO_PRODUCT}


def check_local_candidate_delivery(
    reader: f03.A05OwnerCorpusAdmission,
    candidate: dict,
    *,
    origin: dict,
    recipient: dict,
    issued_at: dt.datetime,
    delivered_at: dt.datetime,
    lease_ttl_seconds: int,
    independent_epoch_floor: int,
    expected_revision: str = f03.A05_REVISION,
) -> dict:
    """Revalidate disk, citations, receiver and epoch at local delivery.

    Epoch floor MUST come from independent custody for any meaningful rollback
    resilience; the local test floor is explicitly simulated, NOT such custody.
    No caller-supplied argument can convert this output into a Product permit.
    """
    try:
        require = f03.check
        require(isinstance(reader, f03.A05OwnerCorpusAdmission),
                "INVALID_READER")
        require(type(candidate) is dict and
                candidate.get("decision") == "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE"
                and candidate.get("candidate_only") is True
                and candidate.get("nonprod_file_mode") in ("REAL_GIT_SOURCE", "TEST_COPY")
                and candidate.get("product_authenticated") is False
                and candidate.get("product_admitted") is False
                and candidate.get("verified_final") is False
                and candidate.get("independent_issuer") is False
                and candidate.get("answer_cache_enabled") is False
                and candidate.get("answer_cache_hit") is False
                and candidate.get("answer_cache_write") is False
                and candidate.get("cache_mode") == "BYPASS"
                and candidate.get("native_consumer_joined") is False,
                "NOT_SAFE_LOCAL_CANDIDATE")
        require(type(origin) is dict and set(origin) == _CONTEXT_KEYS
                and type(recipient) is dict and set(recipient) == _CONTEXT_KEYS,
                "MISSING_OR_EXTRA_CLIENT_BINDING")
        require(all(type(origin[k]) is str and 0 < len(origin[k]) <= 128
                    for k in _CONTEXT_KEYS), "INVALID_ORIGIN_FIELDS")
        require(origin["channel"] == _LOCAL_CHANNEL
                and origin["tenant"] == "owner-internal"
                and origin["principal"] == "os-uid:" + str(os.geteuid()),
                "NONLOCAL_OR_UNBOUND_IDENTITY")
        require(recipient == origin, "CROSS_CLIENT_SESSION_OR_TENANT")
        require(type(lease_ttl_seconds) is int and
                0 < lease_ttl_seconds <= f03.MAX_TTL_SECONDS,
                "INVALID_LOCAL_LEASE_TTL")
        require(type(independent_epoch_floor) is int and
                independent_epoch_floor >= 1, "MISSING_MONOTONIC_EPOCH_FLOOR")
        require(type(issued_at) is dt.datetime and
                type(delivered_at) is dt.datetime and
                issued_at.tzinfo is not None and
                delivered_at.tzinfo is not None and
                issued_at.utcoffset() == dt.timedelta(0) and
                delivered_at.utcoffset() == dt.timedelta(0),
                "UTC_CLOCK_REQUIRED")
        require(issued_at <= delivered_at <
                issued_at + dt.timedelta(seconds=lease_ttl_seconds),
                "EXPIRED_BEFORE_CLIENT_DELIVERY")

        corpus, release, release_sha = reader._pinned_release()
        expires = dt.datetime.fromisoformat(release["expires_at"])
        starts = dt.datetime.fromisoformat(release["snapshot_at"])
        require(starts <= issued_at and
                delivered_at + dt.timedelta(seconds=1) <= expires and
                issued_at + dt.timedelta(seconds=lease_ttl_seconds) <= expires,
                "SOURCE_RELEASE_EXPIRED_AT_DELIVERY")
        require(expected_revision == f03.A05_REVISION
                and candidate.get("source_revision") == expected_revision
                and candidate.get("release_id") == f03.A05_RELEASE_ID
                and candidate.get("source_manifest_sha256") == f03.A05_SOURCE_PIN
                and candidate.get("release_sha256") == release_sha,
                "SOURCE_RELEASE_VERSION_MISMATCH")
        epoch, rev_sha, revoked = reader._epoch(release)
        require(epoch >= independent_epoch_floor,
                "RESTORED_BELOW_INDEPENDENT_EPOCH_FLOOR")
        require(candidate.get("rights_epoch") == epoch
                and candidate.get("revocation_sha256") == rev_sha,
                "RIGHTS_REVOCATION_CHANGED")
        s = candidate.get("source")
        require(type(s) is dict and
                s.get("corpus_id") == f03.A05_RELEASE_ID
                and s.get("corpus_revision") == f03.A05_REVISION
                and s.get("corpus_sha256") == f03.A05_SOURCE_PIN
                and s.get("source_manifest_sha256") == f03.A05_SOURCE_PIN,
                "SOURCE_PROJECTION_VERSION_MISMATCH")
        policy = candidate.get("policy")
        require(type(policy) is dict and
                policy.get("revocation_epoch") == epoch,
                "SOURCE_PROJECTION_EPOCH_MISMATCH")
        citations = candidate.get("sources")
        require(type(citations) is list and 0 < len(citations) <= 5,
                "MISSING_CITATIONS")
        allowed = {(c["source_filename"], c["byte_start"], c["byte_end"],
                    c["quote_sha256"], c["source_sha256"])
                   for c in corpus["chunks"]}
        lookup = {d["filename"]: d for d in corpus["docs"]}
        for c in citations:
            require(type(c) is dict, "BAD_CITATION")
            name = c.get("document")
            require(type(name) is str and name in lookup
                    and c.get("release_id") == f03.A05_RELEASE_ID
                    and c.get("source_revision") == f03.A05_REVISION
                    and c.get("revocation_epoch") == epoch
                    and c.get("document_sha256") == lookup[name]["sha256"]
                    and c.get("document_sha256") not in revoked
                    and c.get("source_uri") == "urn:sha256:" + lookup[name]["sha256"],
                    "CITATION_PROVENANCE_OR_RIGHTS")
            start, end = c.get("byte_start"), c.get("byte_end")
            require(type(start) is int and type(end) is int and
                    (name, start, end, c.get("excerpt_sha256"),
                     c.get("document_sha256")) in allowed,
                    "CITATION_NOT_FROZEN_SPAN")
            actual = reader._read(name)
            require(f03.sha(actual) == lookup[name]["sha256"] and
                    f03.sha(actual[start:end]) == c["excerpt_sha256"],
                    "CITATION_BYTES_CHANGED")
        require(s.get("source_ids") == [c["document"] for c in citations],
                "SOURCE_PROJECTION_CITATION_MISMATCH")

        return {
            "decision": "LOCAL_DELIVERY_CONTEXT_BOUND_SOURCE_CANDIDATE_ONLY",
            "source_release_sha256": release_sha,
            "source_manifest_sha256": f03.A05_SOURCE_PIN,
            "rights_epoch": epoch,
            "revocation_sha256": rev_sha,
            "client_context_sha256": f03.sha(f03.canonical(origin)),
            "citation_count": len(citations),
            "source_revision": f03.A05_REVISION,
            **{**_NO_PRODUCT, "candidate_only": True},
        }
    except (f03.Rejected, OSError, KeyError, TypeError, ValueError,
            OverflowError) as error:
        return _deny(str(error) if isinstance(error, f03.Rejected)
                     else "INCOMPLETE_UNTRUSTED_OR_UNAVAILABLE_SOURCE")
    except Exception:
        return _deny("UNEXPECTED_LOCAL_VALIDATION_FAILURE")


def remote_product_rights_decision(*_args: Any, **_kwargs: Any) -> dict:
    """No local owner proof is an IdP/Controller/Store/JWKS signature."""
    return {
        **_deny("ACTUAL_CONTROLLER_IDP_AND_STORE_PERMIT_NOT_PROVIDED"),
        "product_rights_status": "PRODUCT_RIGHTS_HOLD",
        "g04_remote_authorized": False,
    }
