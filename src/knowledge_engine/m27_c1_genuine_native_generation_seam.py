"""C1 genuine LIVE-native seam, disabled by default until independently admitted.

No synthetic success or caller-supplied signer. Separate trust anchor MUST be
compile-time pinned from an independently approved third-party/Controller manifest
in a future distinct source release; there is intentionally no key in this branch.
No provider operation, model text, Client ACK or semantic issuer can be invented.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

import m27_f03_source_rights_admission as f03
import m27_h02_native_nonprod_consumer as h02
import m27_g01_current_native_consumer as g01
import m27_task_contracts_v1 as tc

ABI = "m27.c1.native-live-generation-governed/v1"
CLIENT_ABI = "m27.c1.native-verified-text-ack/v1"
PROVIDER_ABI = "m27.c1.provider-new-delta/v1"
TRUST_ROOT_MANIFEST_SHA256 = None  # Deliberate HOLD: no independent current root has been admitted.
OBLIGATIONS = tuple(x[0] for x in g01.OBLIGATIONS)
ROLES = ("provider_controller", "source_controller", "semantic_issuer", "client_idp")
MAX_DELTA = 1024
MAX_CHARS = 8192
MAX_WIRE = 32768
MAX_EVENTS = 128
MAX_TOKENS = 192
MAX_WALL_SECONDS = 30
MAX_BUDGET_MICROUSD = 100000
UTC = dt.timezone.utc


class NotQualified(ValueError):
    pass


def check(ok, reason):
    if not ok:
        raise NotQualified(reason)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def private_file(path: Path, *, max_size=32768) -> bytes:
    path = Path(path)
    st = path.lstat()
    check(stat.S_ISREG(st.st_mode) and not path.is_symlink()
          and stat.S_IMODE(st.st_mode) == 0o600
          and st.st_uid == os.geteuid() and st.st_size <= max_size,
          "PRIVATE_AUTHORITY_FILE_DENIED")
    raw = path.read_bytes()
    check(raw and len(raw) <= max_size, "PRIVATE_AUTHORITY_FILE_INVALID")
    return raw


def utc_epoch(value):
    check(type(value) is int and 0 < value < 2**42, "INVALID_EXPIRY")
    return value


def verify_ed25519(public_pem: bytes, payload: dict, signature_b64: str) -> None:
    """One-way public-key verification; NEVER sign or infer independent identity.

    The authenticated trust-root manifest itself must have a release-pinned SHA.
    A caller-supplied public key, an unpinned path or a lambda True are rejected.
    """
    check(type(signature_b64) is str and len(signature_b64) <= 256,
          "MISSING_SIGNED_BYTES")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise NotQualified("INVALID_SIGNATURE_ENCODING") from exc
    check(len(signature) == 64 and public_pem.startswith(b"-----BEGIN PUBLIC KEY-----"),
          "INVALID_EXTERNAL_SIGNATURE_OR_ROOT")
    with tempfile.TemporaryDirectory(prefix="m27-c1-public-verify-") as directory:
        root = Path(directory)
        (root / "public.pem").write_bytes(public_pem)
        (root / "payload.bin").write_bytes(canonical(payload))
        (root / "signature.bin").write_bytes(signature)
        try:
            done = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin",
                 "-inkey", str(root / "public.pem"), "-rawin",
                 "-in", str(root / "payload.bin"),
                 "-sigfile", str(root / "signature.bin")],
                capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NotQualified("EXTERNAL_SIGNATURE_VERIFIER_UNAVAILABLE") from exc
        check(done.returncode == 0, "INDEPENDENT_SIGNATURE_INVALID")


class IndependentAuthority:
    """External Controller-bound trust anchor. No root => zero eligible model calls."""

    def __init__(self, root_path: Path | None):
        check(type(TRUST_ROOT_MANIFEST_SHA256) is str and
              re.fullmatch(r"[0-9a-f]{64}", TRUST_ROOT_MANIFEST_SHA256),
              "INDEPENDENT_TRUST_ROOT_NOT_ADMITTED")
        check(root_path is not None, "MISSING_INDEPENDENT_TRUST_ROOT")
        raw = private_file(root_path)
        check(sha(raw) == TRUST_ROOT_MANIFEST_SHA256, "TRUST_ROOT_PIN_MISMATCH")
        root = json.loads(raw)
        check(type(root) is dict and set(root) == {"version", "roles"} and
              root["version"] == "m27.external-independent-trust/v1" and
              type(root["roles"]) is dict and set(root["roles"]) == set(ROLES),
              "UNQUALIFIED_TRUST_ROOT_MANIFEST")
        principals = [root["roles"][role]["principal"] for role in ROLES]
        check(all(type(p) is str and 3 <= len(p) <= 128 for p in principals) and
              len(set(principals)) == 4, "ISSUER_ROLE_SEPARATION_NOT_MET")
        self.roles = root["roles"]

    def receipt(self, role: str, signed: dict, expected: dict, *, nonce: str) -> dict:
        check(role in ROLES and type(signed) is dict and
              set(signed) == {"payload", "signature_b64"}, "UNTRUSTED_RECEIPT")
        p = signed["payload"]
        check(type(p) is dict and
              set(p) == set(expected) | {"role", "issuer", "nonce", "issued_at", "expires_at"}
              and p.get("role") == role and
              p.get("issuer") == self.roles[role]["principal"] and
              p.get("nonce") == nonce, "RECEIPT_ROLE_BINDING_MISMATCH")
        check(all(p[k] == v for k, v in expected.items()),
              "RECEIPT_CONTEXT_SOURCE_TASK_MISMATCH")
        now = int(time.time())
        check(utc_epoch(p["issued_at"]) <= now and
              now < utc_epoch(p["expires_at"]) <= now + 300,
              "RECEIPT_EXPIRED_OR_UNBOUNDED")
        pem = self.roles[role]["public_key_pem"].encode("ascii")
        verify_ed25519(pem, p, signed["signature_b64"])
        return p


class BoundedProviderWire:
    """Single scoped HTTPS NDJSON model stream, no redirects/proxies/retries/fallback.

    A real qualified model route requires a controller-verified admission bound
    to the EXACT custom Worker URL/model before this transport can be created.
    """

    def __init__(self, *, url: str, model: str, token_path: Path,
                 approved_origin: str, approved_model: str):
        parsed = urlsplit(url)
        check(parsed.scheme == "https" and parsed.username is None and
              parsed.password is None and parsed.fragment == "" and
              parsed.query == "" and parsed.hostname and
              parsed.path and parsed.path != "/",
              "UNSUPPORTED_OR_UNSAFE_PROVIDER_ROUTE")
        check(url == approved_origin and model == approved_model and
              model and len(model) <= 128, "PROVIDER_ROUTE_MODEL_UNQUALIFIED")
        # Credential stays on the provider-side approved host; never send to reports.
        self.token_path, self.url, self.model = token_path, url, model

    def one_bounded_stream(self, *, prompt: str, task_sha: str,
                           request_id: str, max_tokens: int):
        check(0 < max_tokens <= MAX_TOKENS and len(prompt) <= 1500 and
              re.fullmatch(r"[0-9a-f]{64}", task_sha) is not None,
              "MODEL_BUDGET_OR_TASK_INVALID")
        raw_token = private_file(self.token_path, max_size=2048)
        check(b"\n" not in raw_token and b"\r" not in raw_token,
              "CREDENTIAL_LINEBREAK_DENIED")
        data = canonical({"model": self.model, "prompt": prompt,
                          "max_tokens": max_tokens, "stream": True,
                          "request_id": request_id, "task_sha256": task_sha})
        request = Request(self.url, data=data, method="POST", headers={
            "Authorization": "Bearer " + raw_token.decode("ascii"),
            "Content-Type": "application/json", "Accept": "application/x-ndjson"})
        class NeverRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise NotQualified("PROVIDER_REDIRECT_DENIED")
        opener = build_opener(ProxyHandler({}), HTTPSHandler(), NeverRedirect())
        total, count, begun = 0, 0, time.monotonic()
        # Wire is never disclosed as an answer until qualified semantic receipt.
        try:
            with opener.open(request, timeout=MAX_WALL_SECONDS) as stream:
                check(stream.status == 200 and
                      "application/x-ndjson" in stream.headers.get("Content-Type", ""),
                      "PROVIDER_WIRE_NOT_QUALIFIED")
                for raw in stream:
                    total += len(raw)
                    count += 1
                    check(total <= MAX_WIRE and count <= MAX_EVENTS and
                          time.monotonic() - begun < MAX_WALL_SECONDS,
                          "PROVIDER_STREAM_BUDGET_EXHAUSTED")
                    event = json.loads(raw)
                    check(type(event) is dict and
                          set(event) == {"kind", "text", "model", "request_id"} and
                          event["kind"] in ("delta", "done") and
                          event["model"] == self.model and
                          event["request_id"] == request_id,
                          "UNKNOWN_PROVIDER_EVENT_SHAPE_OR_MODEL")
                    yield raw, event
        finally:
            raw_token = b""


def assert_preterminal_verified_client_text(
        first_verified_ns: int | None, first_ack_ns: int | None,
        provider_done_ns: int | None) -> None:
    """Real timing evidence: BOTH claim and independent client ACK precede done.

    Never infer a preterminal substantive first-text delivery from a progress
    event, a source-only extract, or a first verified response after completion.
    """
    check(type(first_verified_ns) is int and
          type(first_ack_ns) is int and type(provider_done_ns) is int and
          0 < first_verified_ns < first_ack_ns < provider_done_ns,
          "VERIFIED_SUBSTANTIVE_FIRST_TEXT_CLIENT_ACK_NOT_PRETERMINAL")


class GeneratedSession:
    """Unpublishable until independent semantic receipt and physical client ACK.

    Must be built exclusively by a separately authorized runtime that already
    checked Provider/Source/IdP signed receipts; never exposed as user-created.
    """

    def __init__(self, *, task_sha: str, request_id: str,
                 pins: dict, source_recheck, journal: h02.FsyncJournal,
                 authority: IndependentAuthority, model: str):
        check(isinstance(authority, IndependentAuthority) and callable(source_recheck),
              "INDEPENDENT_ISSUER_OR_SOURCE_RECHECK_MISSING")
        self.task_sha = task_sha
        self.request_id = request_id
        self.pins = pins
        self.source_recheck = source_recheck
        self.journal = journal
        self.authority = authority
        self.model = model
        self.nonce = secrets.token_hex(24)
        self.state = "ACTIVE"
        self.full_text = ""
        self.raw_deltas = []
        self.verified = {}
        self.acked = []
        self.provider_done = False
        self.provider_done_ns = None
        self.first_verified_text_ns = None
        self.first_client_ack_ns = None
        self.first_verified_client_delivery_ns = None
        self.started = time.monotonic_ns()
        self.lock = threading.RLock()

    def current(self):
        check(self.state == "ACTIVE" and
              time.monotonic_ns() - self.started < MAX_WALL_SECONDS * 10**9,
              "CANCELLED_REVOKED_OR_DEADLINE")
        check(self.source_recheck() == self.pins["source_proof_sha256"],
              "SOURCE_OR_RIGHTS_CHANGED")

    def delta(self, raw: bytes, event: dict):
        with self.lock:
            self.current()
            check(not self.provider_done and
                  type(raw) is bytes and len(raw) <= MAX_DELTA * 4 and
                  type(event) is dict and event.get("kind") in ("delta", "done"),
                  "INVALID_PROVIDER_WIRE")
            check(json.loads(raw) == event and
                  set(event) == {"kind", "text", "model", "request_id"} and
                  event["request_id"] == self.request_id and
                  event["model"] == self.model,
                  "RAW_PROVIDER_IDENTITY_OR_EVENT_BYTES_MISMATCH")
            if event["kind"] == "done":
                check(event.get("text") == "", "DONE_MUST_NOT_CONTAIN_TEXT")
                self.provider_done = True
                self.provider_done_ns = time.monotonic_ns()
                return
            part = event.get("text")
            check(type(part) is str and 0 < len(part) <= MAX_DELTA and
                  len(self.full_text) + len(part) <= MAX_CHARS and
                  len(self.raw_deltas) < MAX_EVENTS and
                  part.encode("utf-8") in raw, "UNTRUSTED_OR_OVERSIZED_GENERATED_DELTA")
            self.raw_deltas.append(sha(raw))
            self.full_text += part
            self.journal.record({"event": "provider_delta_unpublished",
                                 "raw_sha256": sha(raw), "seq": len(self.raw_deltas),
                                 "origin": "LIVE_NEW_PROVIDER_NOT_YET_VERIFIED"})

    def verified_claim(self, *, obligation: str, text: str, signed: dict):
        with self.lock:
            self.current()
            check(obligation in OBLIGATIONS and
                  obligation not in self.verified and
                  len(self.verified) == OBLIGATIONS.index(obligation) and
                  type(text) is str and 16 <= len(text) <= 600 and
                  text in self.full_text and self.raw_deltas,
                  "GENERATED_CLAIM_NOT_IN_RAW_DELTAS")
            if obligation == OBLIGATIONS[0]:
                check(not self.provider_done and self.provider_done_ns is None,
                      "FIRST_VERIFIED_TEXT_MUST_PRECEDE_PROVIDER_DONE")
            expected = {"task_sha256": self.task_sha,
                        "request_id": self.request_id,
                        "source_proof_sha256": self.pins["source_proof_sha256"],
                        "source_manifest_sha256": self.pins["source_manifest_sha256"],
                        "obligation": obligation, "text_sha256": sha(text.encode()),
                        "provider_model": self.model,
                        "model_origin": "LIVE_NEW_PROVIDER"}
            self.authority.receipt("semantic_issuer", signed, expected,
                                   nonce=self.nonce)
            cid = obligation
            challenge = secrets.token_hex(24)
            now_ns = time.monotonic_ns()
            if cid == OBLIGATIONS[0]:
                self.first_verified_text_ns = now_ns
            citations = self.pins.get("citations")
            check(type(citations) is dict and cid in citations,
                  "NO_SOURCE_BOUND_CITATION_FOR_LIVE_CLAIM")
            self.verified[cid] = {"claim_id": cid, "text": text,
                                  "text_sha256": expected["text_sha256"],
                                  "challenge": challenge, "verified_at_ns": now_ns,
                                  "citation": citations[cid],
                                  "client_delivered_at_ns": None}
            self.journal.record({"event": "independent_semantic_verified",
                                 "claim_id": cid, "sha256": expected["text_sha256"]})
            # The semantic issuer's POST response must NEVER supply the
            # Client-only challenge or pretend model text was delivered to a
            # Native Client. Only the authenticated separate GET can expose
            # verified substantive text/challenge for signed Client ACK.
            return {"status": "INDEPENDENT_SEMANTIC_RECEIPT_VERIFIED_NOT_CLIENT_DELIVERED",
                    "client_abi": CLIENT_ABI, "claim_id": cid,
                    "text_sha256": expected["text_sha256"],
                    "request_id": self.request_id,
                    "native_client_get_required": True,
                    "actual_client_delivery": False}

    def pull_verified(self, *, cid: str):
        """True Native Client transport reads independently verified new text.

        This GET is a real Client delivery gate, not issuer POST completion,
        progress SSE, source-only span, or provider buffer consumption. Exact
        separately signed Client IdP ACK is still required afterwards.
        """
        with self.lock:
            self.current()
            check(cid in self.verified and cid not in self.acked and
                  cid == OBLIGATIONS[len(self.acked)],
                  "VERIFIED_CLIENT_TEXT_NOT_READY_OR_REPLAY")
            claim = self.verified[cid]
            check(not self.provider_done and self.provider_done_ns is None,
                  "VERIFIED_TEXT_DELIVERY_MUST_PRECEDE_PROVIDER_DONE")
            check(claim["client_delivered_at_ns"] is None,
                  "VERIFIED_CLIENT_DELIVERY_REPLAY_DENIED")
            when = time.monotonic_ns()
            claim["client_delivered_at_ns"] = when
            if cid == OBLIGATIONS[0]:
                self.first_verified_client_delivery_ns = when
            self.journal.record({
                "event": "verified_new_model_text_delivered_to_native_client",
                "claim_id": cid, "text_sha256": claim["text_sha256"],
                "when_ns": when, "provider_done": False})
            return {"status": "VERIFIED_SUBSTANTIVE_MODEL_TEXT_DELIVERED_PRETERMINAL",
                    "client_abi": CLIENT_ABI,
                    "request_id": self.request_id,
                    "claim_id": cid, "text": claim["text"],
                    "text_sha256": claim["text_sha256"],
                    "challenge": claim["challenge"],
                    "citation": claim["citation"],
                    "source_proof_sha256": self.pins["source_proof_sha256"],
                    "provider_done": False, "cache": "OFF",
                    "product_pass": False}

    def ack(self, *, cid: str, challenge: str, text_sha256: str,
            client_signature: dict):
        with self.lock:
            self.current()
            check(cid in self.verified and cid not in self.acked and
                  cid == OBLIGATIONS[len(self.acked)],
                  "CLIENT_ACK_REPLAY_OR_WRONG_ORDER")
            claim = self.verified[cid]
            check(type(claim.get("client_delivered_at_ns")) is int and
                  claim["client_delivered_at_ns"] < time.monotonic_ns(),
                  "CLIENT_ACK_BEFORE_ACTUAL_TEXT_DELIVERY_DENIED")
            check(hmac.compare_digest(challenge, claim["challenge"]) and
                  hmac.compare_digest(text_sha256, claim["text_sha256"]),
                  "CLIENT_ACK_NONCE_OR_DIGEST_INVALID")
            expected = {"task_sha256": self.task_sha,
                        "request_id": self.request_id,
                        "source_proof_sha256": self.pins["source_proof_sha256"],
                        "claim_id": cid, "text_sha256": claim["text_sha256"],
                        "challenge": challenge,
                        "client_abi": CLIENT_ABI}
            self.authority.receipt("client_idp", client_signature, expected,
                                   nonce=self.nonce)
            if cid == OBLIGATIONS[0]:
                check(not self.provider_done and self.provider_done_ns is None,
                      "FIRST_CLIENT_ACK_MUST_PRECEDE_PROVIDER_DONE")
                self.first_client_ack_ns = time.monotonic_ns()
            self.acked.append(cid)
            self.journal.record({"event": "external_client_ack",
                                 "claim_id": cid, "text_sha256": text_sha256,
                                 "when_ns": time.monotonic_ns()})

    def terminal(self):
        with self.lock:
            self.current()
            check(self.provider_done and tuple(self.acked) == OBLIGATIONS and
                  tuple(self.verified) == OBLIGATIONS and self.raw_deltas,
                  "TERMINAL_BEFORE_LIVE_PROVIDER_DONE_SEMANTIC_AND_ACK")
            assert_preterminal_verified_client_text(
                self.first_verified_text_ns,
                self.first_client_ack_ns, self.provider_done_ns)
            check(type(self.first_verified_client_delivery_ns) is int and
                  self.first_verified_text_ns <
                  self.first_verified_client_delivery_ns <
                  self.first_client_ack_ns and
                  all(type(self.verified[k].get("client_delivered_at_ns")) is int
                      for k in OBLIGATIONS),
                  "NATIVE_FIRST_VERIFIED_TEXT_NOT_ACTUALLY_DELIVERED")
            self.current()
            text = " ".join(self.verified[k]["text"] for k in OBLIGATIONS)
            check(all(self.verified[k]["text"] in self.full_text for k in OBLIGATIONS),
                  "FINAL_NOT_GENERATED")
            self.state = "TERMINAL"
            self.journal.record({"event": "terminal", "status": "SIGNED_CLIENT_ACK_COMPLETE",
                                 "answer_sha256": sha(text.encode()),
                                 "when_ns": time.monotonic_ns()})
            return {"status": "NEW_MODEL_VERIFIED_CLIENT_ACKED",
                    "answer_text": text, "answer_sha256": sha(text.encode()),
                    "citations": {oid: self.verified[oid]["citation"]
                                  for oid in OBLIGATIONS},
                    "source_proof_sha256": self.pins["source_proof_sha256"],
                    "actual_preterminal_client_ack": True,
                    "first_substantive_text_before_provider_done": True,
                    "first_client_ack_before_provider_done": True,
                    "first_verified_model_text_native_delivery_confirmed": True,
                    "first_verified_text_ms": round(
                        (self.first_verified_text_ns - self.started) / 1e6, 3),
                    "actual_complete_answer_ms": round(
                        (time.monotonic_ns() - self.started) / 1e6, 3),
                    "actual_usage": None,
                    "cache_mode": "OFF"}

    def cancel(self):
        with self.lock:
            check(self.state == "ACTIVE", "REPLAYED_CANCEL_OR_TERMINAL")
            self.state = "CANCELLED"
            self.journal.record({"event": "terminal", "status": "CANCELLED_NO_PUBLISH"})
            return {"status": "CANCELLED_NO_PUBLISH", "answer_text": None}


class NativeLiveProduct:
    """C1 controlled real generation: freeze -> signed rights -> HTTPS -> verify -> ACK.

    The true trust-root digest is deliberately NOT pinned in this source.
    No trusted root or separately signed grants exist in the current worksite.
    Thus no provider call or publish is possible in this exact release.
    """

    def __init__(self, *, repo: Path, fence: Path, journal: Path,
                 trust_root: Path | None = None,
                 qualification_bundle: Path | None = None):
        self.repo = Path(repo).resolve(strict=True)
        self.fence = Path(fence)
        self.journal = h02.FsyncJournal(journal)
        self.trust_root = trust_root
        self.qualification_bundle = qualification_bundle
        self.status = "LIVE_NOT_RUN_EXTERNAL_TRUST_ROOT_MISSING"
        self.provider_invocations = 0
        self.sessions = {}
        self.lock = threading.RLock()

    def _reader(self):
        return g01.Consumer(repo=self.repo, fence=self.fence,
                            journal=Path(str(self.journal.path) + ".source.jsonl"))

    def _source(self):
        """Real two-document A05 source byte verification, NOT semantic issuer."""
        proofs = self._reader()._source()
        check(len(proofs) == 2 and
              proofs[0]["document_sha256"] != proofs[1]["document_sha256"] and
              proofs[0]["source_manifest_sha256"] == f03.A05_SOURCE_PIN and
              proofs[1]["source_manifest_sha256"] == f03.A05_SOURCE_PIN and
              proofs[0]["rights_epoch"] == proofs[1]["rights_epoch"] and
              proofs[0]["rights_sha256"] == proofs[1]["rights_sha256"],
              "A05_REAL_SOURCE_PROOF_OR_EPOCH_INVALID")
        return proofs

    @staticmethod
    def _bounded_task_request(body: dict):
        check(type(body) is dict and set(body) ==
              {"question", "tenant", "cache_mode", "max_tokens",
               "deadline_seconds", "fallback_consent"},
              "LIVE_TASKCONTRACT_SHAPE_DENIED")
        check(body["question"] == g01.QUESTION and
              body["tenant"] == "owner-internal" and
              body["cache_mode"] == "OFF" and
              type(body["max_tokens"]) is int and
              0 < body["max_tokens"] <= MAX_TOKENS and
              type(body["deadline_seconds"]) is int and
              0 < body["deadline_seconds"] <= MAX_WALL_SECONDS and
              body["fallback_consent"] is False,
              "LIVE_TASK_RIGHTS_BUDGET_OR_FALLBACK_DENIED")

    def prepare(self, body: dict) -> dict:
        """Stage 1: only OS-local A05 + original TaskContract. NEVER invoke model.

        Allows genuine distinct Controllers to see the actual immutable task/source
        SHA and sign their own bounded authority before Stage 2. No circular
        'sign a timestamp-generated SHA you have not seen yet' protocol.
        """
        self._bounded_task_request(body)
        with self.lock:
            check(not self.sessions and not getattr(self, "pending", None) and
                  self.journal.recover() == "EMPTY",
                  "LIVE_SESSION_RESTART_OR_REPLAY_DENIED")
            proofs = self._source()
            source_hash = sha(canonical(proofs))
            principal = "os-uid:" + str(os.geteuid())
            task = h02.local_task(g01.QUESTION, principal)
            task["constraints"] = [
                "Actual two A05 OS independently byte-proved source obligations",
                "New Provider generation only with separately signed Controller grant",
                "Genuine separate Semantic Issuer before publishing any new model text",
                "Separate cryptographic Client ACK before Terminal",
                "Cache OFF, no fallback, no effects, fail-closed revocation"]
            task["definition_of_done"]["predicate_refs"] = [
                "independent_idp", "independent_source_rights", "live_provider_delta",
                "independent_semantic_two_obligations",
                "two_signed_client_acks_preterminal",
                "source_revocation_recheck", "cache_off"]
            task["budget"]["max_tokens"] = body["max_tokens"]
            task["budget"]["max_wall_ms"] = body["deadline_seconds"] * 1000
            task["budget"]["max_cost_microunits"] = MAX_BUDGET_MICROUSD
            task = tc.task_contract(task)
            task_sha = tc.sha256(task)
            nonce, request_id = secrets.token_hex(24), secrets.token_hex(24)
            context = {
                "task_sha256": task_sha,
                "request_id": request_id,
                "source_proof_sha256": source_hash,
                "source_manifest_sha256": f03.A05_SOURCE_PIN,
                "rights_epoch": proofs[0]["rights_epoch"],
                "tenant": "owner-internal"}
            pins = {**context, "source_rights_sha256": proofs[0]["rights_sha256"],
                    "citations": {p["obligation_id"]: p["citation"] for p in proofs}}
            self.pending = {
                "task": task, "task_sha": task_sha, "body": body.copy(),
                "nonce": nonce, "request_id": request_id, "context": context,
                "pins": pins, "source_proofs_sha256": source_hash,
                "prepared_ns": time.monotonic_ns()}
            self.journal.record({
                "event": "real_a05_source_and_task_prepared_NOT_PROVIDER",
                "task_sha256": task_sha, "source_proof_sha256": source_hash,
                "rights_epoch": proofs[0]["rights_epoch"],
                "request_id": request_id,
                "provider_called": False, "product_qualified": False})
            return {"status": "CURRENT_TASK_SOURCE_PREPARED_AWAIT_EXTERNAL_GRANTS",
                    "native_abi": ABI, "client_abi": CLIENT_ABI,
                    "task_contract_sha256": task_sha,
                    "source_manifest_sha256": f03.A05_SOURCE_PIN,
                    "source_proof_sha256": source_hash,
                    "rights_epoch": proofs[0]["rights_epoch"],
                    "request_id": request_id, "nonce": nonce,
                    "prepared_source_count": len(proofs),
                    # Cryptographic source hashes from the SAME TaskContract,
                    # not a second H02 task or an independently signed proof.
                    "source_binding_sha256": sha(canonical([
                        {"obligation_id": p["obligation_id"],
                         "document_sha256": p["document_sha256"],
                         "excerpt_sha256": p["excerpt_sha256"],
                         "citation": p["citation"]} for p in proofs])),
                    "source_obligation_ids": [p["obligation_id"]
                                              for p in proofs],
                    "source_byte_verified_local": True,
                    "independent_product_rights_verified": False,
                    "independent_semantic_issuer_verified": False,
                    "provider_called": False, "actual_usage": None,
                    "cache": "OFF", "answer_text": None,
                    "product_pass": False}

    def start(self, body: dict) -> dict:
        """Stage 2: requires distinct external signed source/provider/idp receipts.

        No general Owner permission or installed Provider credential can replace
        these externally verified, current-source, nonce-bound grants.
        """
        check(type(body) is dict and set(body) == {"request_id"} and
              type(body["request_id"]) is str,
              "LIVE_START_REQUIRES_FROZEN_TASK_ID")
        # Mandatory compile-time pinned external public trust root. Currently NONE.
        authority = IndependentAuthority(root_path=self.trust_root)
        with self.lock:
            pending = getattr(self, "pending", None)
            check(type(pending) is dict and
                  pending["request_id"] == body["request_id"] and
                  not self.sessions, "NO_SUCH_PENDING_UNREPLAYED_TASK")
            check(time.monotonic_ns() - pending["prepared_ns"] < 120 * 10**9,
                  "PENDING_EXTERNAL_GRANT_EXPIRED")
            check(self.qualification_bundle is not None,
                  "EXTERNAL_SCOPED_GRANTS_NOT_PRESENT")
            grant = json.loads(private_file(self.qualification_bundle))
            check(type(grant) is dict and set(grant) ==
                  {"provider", "source", "client", "nonce", "url", "model",
                   "token_file", "client_principal",
                   "upper_bound_input_micro_per_1k",
                   "upper_bound_output_micro_per_1k", "wire_protocol"},
                  "UNKNOWN_EXTERNAL_GRANT_BUNDLE")
            nonce = grant["nonce"]
            check(grant["wire_protocol"] == PROVIDER_ABI,
                  "PROVIDER_WIRE_CONTRACT_NOT_VERIFIED")
            check(nonce == pending["nonce"] and
                  type(grant["url"]) is str and type(grant["model"]) is str and
                  type(grant["client_principal"]) is str and
                  re.fullmatch(r"[a-zA-Z0-9._:-]{3,128}", grant["client_principal"]) and
                  type(grant["upper_bound_input_micro_per_1k"]) is int and
                  type(grant["upper_bound_output_micro_per_1k"]) is int and
                  0 <= grant["upper_bound_input_micro_per_1k"] <= 100000000 and
                  0 <= grant["upper_bound_output_micro_per_1k"] <= 100000000,
                  "UNSCOPED_EXTERNAL_GRANT")
            body_orig = pending["body"]
            # Conservative input byte-count ceiling; this is a provider-controller
            # signed PRICE UPPER BOUND, not fabricated invoice/actual usage.
            expected_cost = (
                len(g01.QUESTION.encode()) * grant["upper_bound_input_micro_per_1k"] +
                body_orig["max_tokens"] * grant["upper_bound_output_micro_per_1k"]
                + 999) // 1000
            check(expected_cost <= MAX_BUDGET_MICROUSD,
                  "SIGNED_PROVIDER_UPPER_BOUND_EXCEEDS_COST_CAP")
            check(sha(canonical(self._source())) == pending["source_proofs_sha256"],
                  "A05_SOURCE_REVOKED_SINCE_TASK_FREEZE")
            context = pending["context"]
            authority.receipt("source_controller", grant["source"],
                              context, nonce=nonce)
            provider_scope = {**context, "url": grant["url"],
                "model": grant["model"], "max_tokens": body_orig["max_tokens"],
                "deadline_seconds": body_orig["deadline_seconds"],
                "max_request_cost_microusd": expected_cost,
                "upper_bound_input_micro_per_1k": grant["upper_bound_input_micro_per_1k"],
                "upper_bound_output_micro_per_1k": grant["upper_bound_output_micro_per_1k"],
                "wire_protocol": PROVIDER_ABI,
                "fallback_allowed": False}
            authority.receipt("provider_controller", grant["provider"],
                              provider_scope, nonce=nonce)
            authority.receipt("client_idp", grant["client"],
                              {**context, "client_principal": grant["client_principal"],
                               "client_abi": CLIENT_ABI}, nonce=nonce)
            wire = BoundedProviderWire(
                url=grant["url"], model=grant["model"],
                token_path=Path(grant["token_file"]),
                approved_origin=grant["url"], approved_model=grant["model"])
            req_id = pending["request_id"]
            sess = GeneratedSession(
                task_sha=pending["task_sha"], request_id=req_id,
                pins=pending["pins"],
                source_recheck=lambda: sha(canonical(self._source())),
                journal=self.journal, authority=authority, model=grant["model"])
            sess.nonce = nonce
            self.sessions[req_id] = sess
            self.pending = None
            self.journal.record({
                "event": "distinct_controller_verified_live_admission",
                "task_sha256": pending["task_sha"],
                "source_proof_sha256": pending["source_proofs_sha256"],
                "rights_epoch": context["rights_epoch"],
                "provider_route_pinned": True,
                "wire_protocol": PROVIDER_ABI,
                "model": grant["model"], "request_id": req_id,
                "controller_signed_cost_upper_microusd": expected_cost})
            worker = threading.Thread(target=self._run_one,
                args=(sess, wire, body_orig["max_tokens"]), daemon=True,
                name="c1-one-bounded-native-provider-" + req_id[:8])
            worker.start()
            return {"status": "SIGNED_LIVE_ADMISSION_PROVIDER_STARTING",
                    "request_id": req_id,
                    "task_contract_sha256": pending["task_sha"],
                    "source_proof_sha256": pending["source_proofs_sha256"],
                    "max_signed_cost_microusd": expected_cost,
                    "cache": "OFF", "client_abi": CLIENT_ABI,
                    "answer_text": None, "actual_client_ack": False,
                    "product_pass": False}

    def _run_one(self, session: GeneratedSession, wire: BoundedProviderWire,
                 max_tokens: int):
        try:
            self.provider_invocations += 1
            for raw, event in wire.one_bounded_stream(
                prompt=g01.QUESTION, task_sha=session.task_sha,
                request_id=session.request_id, max_tokens=max_tokens):
                session.delta(raw, event)
            check(session.provider_done, "PROVIDER_STREAM_MISSING_DONE")
        except Exception:
            # A failed live attempt is UNKNOWN, never paid/verified success.
            if session.state == "ACTIVE":
                try:
                    session.cancel()
                except NotQualified:
                    pass
            self.status = "LIVE_PROVIDER_UNKNOWN_SAFE_ABSTAINED"

    def session(self, request_id: str) -> GeneratedSession:
        check(type(request_id) is str and request_id in self.sessions,
              "UNKNOWN_OR_REPLAYED_LIVE_TASK")
        return self.sessions[request_id]

    def verify_claim(self, body: dict):
        check(type(body) is dict and set(body) ==
              {"request_id", "obligation", "text", "signed_semantic_receipt"},
              "SEMANTIC_REQUEST_SHAPE_DENIED")
        return self.session(body["request_id"]).verified_claim(
            obligation=body["obligation"], text=body["text"],
            signed=body["signed_semantic_receipt"])

    def pull_verified(self, *, request_id: str, claim_id: str):
        return self.session(request_id).pull_verified(cid=claim_id)

    def ack(self, body: dict):
        check(type(body) is dict and set(body) ==
              {"request_id", "claim_id", "challenge", "text_sha256",
               "signed_client_ack"}, "CLIENT_ACK_SHAPE_DENIED")
        self.session(body["request_id"]).ack(
            cid=body["claim_id"], challenge=body["challenge"],
            text_sha256=body["text_sha256"],
            client_signature=body["signed_client_ack"])
        return {"status": "SIGNED_EXTERNAL_CLIENT_ACK_RECEIVED",
                "answer_text": None}

    def terminal(self, body: dict):
        check(type(body) is dict and set(body) == {"request_id"},
              "LIVE_TERMINAL_SHAPE_DENIED")
        return self.session(body["request_id"]).terminal()

    def cancel(self, body: dict):
        check(type(body) is dict and set(body) == {"request_id"},
              "LIVE_CANCEL_SHAPE_DENIED")
        return self.session(body["request_id"]).cancel()

    def admission_status(self):
        return {"native_generation_abi": ABI, "native_client_abi": CLIENT_ABI,
                "provider_abi": PROVIDER_ABI, "cache": "OFF",
                "product_pass": False, "provider_called": False,
                "qualified_source_issuer": False, "qualified_semantic_issuer": False,
                "qualified_idp": False,
                "trust_root_sha256": TRUST_ROOT_MANIFEST_SHA256,
                "cloudflare_primary": "EXPLICIT_PREVIOUS_REFUSAL_NO_EQUIVALENT_PROBE",
                "minimax_fallback": "NOT_RUN_NO_INDEPENDENT_PRIMARY_FAILURE",
                "actual_provider_usage": None,
                "cap_tokens": MAX_TOKENS, "cap_wall_seconds": MAX_WALL_SECONDS,
                "max_cost_microusd": MAX_BUDGET_MICROUSD,
                "status": self.status}