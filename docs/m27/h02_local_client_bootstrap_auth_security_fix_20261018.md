# H02 Owner-private loopback Source Review local-client authorization

Scope: actual P0 local security defect repair in a new isolated H02 Nonprod Worktree. **Not** a Product IdP, cross-tenant auth/rights grant, native LLM streaming, C28 or Production acceptance.

## Original real defect and correction
An independent subprocess on the same authorized MacBook issued JSON `POST /nonprod/source-review/start` with **no Authorization header** and received **HTTP 200**, `LOCAL_MULTITOPIC_SOURCE_REVIEW_AWAITING_ACK`, and nonempty real firstparty A05 source claims. Loopback binding and status `source_candidate_not_answer` do not authorize arbitrary local clients to read sources.

The isolated SourceReviewServer now generates a cryptographically random 48-byte-entropy-strength per-server bootstrap Bearer token. `do_POST` fails closed with HTTP403 *before reading/validating the question or invoking A05 retrieval* unless the request has: exact bound IP:port Host, no Origin header, an exact Bearer token equal under constant-time comparison, and ordinary existing JSON/schema/size rules. Token is obtained only from the explicitly authorized local server-launch process and supplied to the separately launched real OS Client through stdin, not serialized in JSON, querystrings, stdout or test artifacts. Old anonymous/incorrect/browsers with Origin clients get no source claims. Both positive Client ACK/terminal and unsupported negative flow still work. Distinct server instances receive different tokens.

## Security scope
This is **not** independently validated remote principal/tenant Product Identity, has no multi-user isolation guarantees, and must never be exposed to nonloopback interfaces or advertised as IdP. An operator who can inspect a same-UID Python process may be able to recover local tokens; it is defense-in-depth for the isolated localhost source-review service, not cross-OS-account authority. External Product IdP/source-controller/issuance remains HOLD. No answer cache, Provider LLM, model response, G03 effects, protected official evaluation or change to frozen Q34.

## Evidence and gate rules
Raw unauthenticated before-fix observation: HTTP 200 / nonempty source claims / auth_header_required false, in this engineering session, intentionally no source text exposed in report. New negative cases: missing token, bad token, wrong Origin, wrong Host, token rotation. New positive uses actual permitted client. Existing H02/F03 bounded local source regression stays green. Both Python 3.11 and 3.14 must pass independently before source commit/promotion.

Owner Charter primary: `/Users/huaihsuanhuang/Desktop/06_M27_VNEXT_MASTER_ARCHITECTURE_AND_CONSTRUCTION_CHARTER_V1_20261014.md`. Strict final Product requirements success >95% on 523 (>=497 real complete answers), independent rubric quality >85/100, complete-answer p95 <15s on same qualified product; **not certified by this local source-only security test**. H01 0/9, C28 NOT_RUN, Product signed image NOT_BUILT, Production NO_GO.
