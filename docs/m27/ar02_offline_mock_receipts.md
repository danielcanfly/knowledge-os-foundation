# AR02A EXPERIMENTAL_NO_EXTERNAL_DISPATCH

Offline in-memory sequential mock only. Trusted=True is injected fixture assumption, NOT verification of independent signer, IdP, legal consent or policy. No network provider calls, no new wire ABI, no replacement for original AR01D v1 bytes or native EvidenceBundleRef. X01-X09 stay OPEN. T1 intent/outbox, T2 claim, T3 UNKNOWN_EFFECT, T5 stale verifier mock assertions are NOT database durability or external exactly-once proof.


Additional bounded regression examples: a charge ID is bound to its original reservation ID and amount, and read returns a detached snapshot so callers cannot alter journal head or approval sets through a read. These are sequential in-memory invariants only, not proof of multi-process isolation, durable CAS, independent identity verification, provider exactly-once semantics, or real persistence.
