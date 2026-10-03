# M27 Production Invariant Registry

These invariants must be preserved by every M27 stage. M27 may run in an isolated environment, but any future promotion candidate must satisfy this registry before touching production.

## Answer-surface invariants

| ID | Invariant | Current evidence | Gate implication |
|---|---|---|---|
| INV-001 | Generic extractive fallback must never be emitted as a user-facing answer. | `m26_pa7_arbitrary_query_runtime.py` contains the explicit guard returning `None`. | Permanent bad-template gate and source guard check. |
| INV-002 | The known bad templates must remain banned. | `scripts/m26_suggested_questions_quality_gate.py` is present in M27. | Run bad-template gate before promotion. |
| INV-003 | Unsupported material claims must fail closed or be repaired before publication. | M26 semantic verification spine remains production-equivalent. | No M27 path may bypass verifier. |
| INV-004 | Material answer text must not be streamed before verification. | Public SSE currently emits terminal answer from DTO; progress events are sanitized. | M27 verified streaming must be a separate gated project. |
| INV-005 | Safe abstention must remain safe and not leak internal answer fragments. | M26 safe abstention/public failure path preserved. | Any new planner/compute policy must route unsafe states to the same abstention boundary. |

## Evidence and citation invariants

| ID | Invariant | Current evidence | Gate implication |
|---|---|---|---|
| INV-101 | Every published material proposition must be evidence-bound. | M26 citation gate and semantic closure are production-equivalent in M27 source. | Context/agent changes must not bypass citation binding. |
| INV-102 | Evidence selection must preserve ACL and production bundle constraints. | Existing retrieval and bundle code was reconciled exactly from production image. | M27 tools must expose domain-level capabilities, not raw infra access. |
| INV-103 | R2/source expansion remains authoritative for publication. | Production bundle and source expansion code preserved. | M27 agentic retrieval may request more evidence, but cannot fabricate authority. |
| INV-104 | Prompt-injection text in evidence is quarantined as evidence, not instruction. | Existing context compiler has prompt-injection handling and instruction block separation. | Context Compiler extraction must preserve this behavior. |

## Runtime and governance invariants

| ID | Invariant | Current evidence | Gate implication |
|---|---|---|---|
| INV-201 | Current production container must not be modified by M27 work. | Production stayed healthy during Stage 0C. | M27 uses separate container/tag/port/volumes. |
| INV-202 | M27 must not bind production port `8080` on host. | Isolated compose binds `127.0.0.1:18080->8080`. | No nginx/Cloudflare route until explicit promotion. |
| INV-203 | M27 must not mutate production R2 active pointer. | Isolated M27 env does not include write credentials. | Write-capable env forbidden until approved. |
| INV-204 | M27 must not mutate production Qdrant aliases/collections. | No Qdrant write path was invoked. | Future M27 Qdrant use must start read-only or cloned. |
| INV-205 | M27 must not write production QA sqlite/admin audit sqlite. | Isolated env uses separate quota DB and M27 volumes. | All M27 DB paths must be separate or ephemeral. |
| INV-206 | Production promotion/rollback remains deterministic and guarded. | Production promotion modules were reconciled into M27 source, but not exposed to M27 tools. | `release.promote`/rollback must not be agent-facing early tools. |

## Architecture invariants

| ID | Invariant | Current evidence | Gate implication |
|---|---|---|---|
| INV-301 | M26 deterministic data plane remains the substrate. | M27 source now equals production source. | M27 wraps first, replaces later only behind gates. |
| INV-302 | Agent/Planner proposes; infrastructure enforces. | Existing admission, policy, citation and release boundaries preserved. | No M27 agent receives final security authority. |
| INV-303 | Test-time compute optimization starts from existing budget signals. | M26 already tracks deadline/provider-attempt budgets. | Extract `ComputePolicy` from existing behavior before adding learned/Jev policies. |
| INV-304 | Autonomous learning produces candidates only. | No learning plane currently writes production. | Future Learning Plane writes candidate reports/branches, never live truth. |
| INV-305 | Meta-Harness is lab-only until explicitly promoted. | No harness optimizer exists in production. | Candidate harness patches must go through eval/promotion gates. |
