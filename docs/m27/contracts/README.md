# AR01I Task-Native Contract Validators v1.0.0

Isolated source-only implementation, **feature OFF**. No import into production runtime, no journal, action dispatch, broker, verification engine, transport, provider, memory writes, image build or release claims.

Modules are pure strict dictionary validators. Security-relevant unexpected fields and unknown version/enum values fail closed. Canonical JSON uses sorted UTF-8 JSON; SHA256 envelopes are references, not authentication signatures. Runtime actor authentication, consent withdrawal, policy engine evaluation, lease fencing, CAS journal, exactly-once protection, source/image attestation, remote observation, client replay and transport byte verification are **NOT IMPLEMENTED**.

AR01D N01-N28: unit tests cover only structural/simulated predicates (including cross-tenant items, source references, digest conflict, approval expiry, immutable terminal transition and fail-closed publication shapes). Full behavioral runtime assertions for N02, N06-N07, N09-N12, N14-N15, N17-N23, N25-N28 are **NOT IMPLEMENTED** pending AR02-05. Never treat the test names as proof of integrated defenses.

The AR01 Master Addendum takes precedence: `unknown_effect` is nonterminal quarantine, zero budgets prohibit usage, authoritative external observations are required for success, and first substantive verified payload byte requires future transport receipts. The source-only base is not equivalent to the active 30P image.

Examples: `PYTHONPATH=src python3 -m pytest -q tests/test_m27_contracts_v1.py`. No external dependency installed by this package. Schemas may evolve by separately reviewed versioned contracts.
