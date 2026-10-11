# M27 W5 B13 | F13 20-source offline core dependency closure candidate

2026-10-11. Version `m27.w5.b13.offline.core.closure/v1`.

## Scope

B13 introduces a **new** manifest-v3-only validator. It never modifies B11, B12,
the F12 manifest or frozen source. It compares 20 independent source hashes to
the exact original Git blobs under B12's frozen clean worktree
`e7cbfdbc4da2027fcd42e7e4586362018a2323ef`,
tree `891d7487d8b9c6b085d1dbbdd651b3817fc7c35d`.
The F13 manifest is pinned to
`0781bb17f1dd405e5140accc1071d019742643902849bb75cd512af9be2f0cde`.
The original F12 SHA set is unchanged and the sole new source is
`m27_ar03_context_broker_experimental.py`,
SHA `b3263c8ae00d99296d449965b94fb6b40a4f70ae8d260e86133ea3b824da9d6e`.

A strict lexical-scope AST gate checks deferred imports, explicitly includes
AR06 -> AR03 in the dependency graph, disallows arbitrary unpinned third parties,
ambiguous relative and dynamic imports, and permits precisely P09
`EvidenceIntake._verify_signature`'s function-local
`cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey`
import **only as an excluded feature**. The core does not install, vendor, verify
or authorize externally signed Ed25519 evidence. The runtime probe is intended
to fail closed if unavailable cryptography can be used to grant admission.

The proposed build uses sorted stored ZIP entries and the canonical 1980
timestamp, modes and metadata; it performs two independently rooted builds,
original Git byte checks, package readback and a fresh isolated
`python -I -S -B` I02+19 module import. The attempted synthetic AR06->AR03
path and P09 negative witness are strictly required before a full positive claim.

## Actual gate disposition

**B13_BLOCKED** pending real executed source/static closure, deterministic
two-build ZIP, origin-provenance/import, AR06 functional deferred selection and
P09 optional-Ed25519 absent-crypto proof. An attempt to run the B13
`OfflineCoreDependencyClosureV1.run` command encountered an explicit
platform safety refusal. The denied operation was not rerouted via RDC or
Codex App, or restated through another tool. The runnable positive build
code remains a *candidate*, not an attested build.

The separately executed new negative/static/receipt/ZIP tests and Ruff
evidence are documented in the worker report. They are not substitutes
for the refused full run.

## Immutable limits

`B13_ALL_FEATURES_DEPENDENCY_CLOSED = FALSE`.
`B13_REAL_SIGNED_EXECUTED_OCI_IMAGE_ATTESTED = FALSE`.
`REL01 = NOT_CERTIFIED`. `REL02 = NOT_AUTHORIZED`.
No real provider, source authority, independently qualified hidden Phase B
evaluation, original 523 gate, CI publishing, client ACK or Production
promotion is within this package.
