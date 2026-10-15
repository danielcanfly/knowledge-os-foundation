# A04 | Real locally generated preterminal Claim-SSE (isolated Nonprod)

**Scope:** independent owner-controlled A04 worksite. **NOT** frozen Q34 native handler, signed Product App, or Production. Original deterministic 21/21 baseline is preserved, not relabeled as model inference.

## Two distinct OS model paths

1. **Deterministic external stub**: `A04_TEST_MODE=1` enables the original 21 independent Client positive/negative tests. `stub_provider.py` is **not a language model**.
2. **Actual local autoregressive model inference**: `A04_LOCAL_MODEL=1` enables `real_local` and `real_local_negative` using `local_model_provider.py`. This calls the **real llama.cpp binary (b11425)** to perform **local Qwen2.5-0.5B-Instruct GGUF Q4_K_M** text generation, with generation settings and OS child PID receipts. No prewritten answer string is passed as a model output.

Official licensed open-weight sources:
- Qwen2.5-0.5B-Instruct-GGUF: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF (Apache-2.0)
- llama.cpp b11425: https://github.com/ggml-org/llama.cpp/releases/tag/b11425
- GGUF SHA256 (pinned): `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`
- llama.cpp release asset SHA256 (official GitHub API digest): `14811f683abf2f32c62df48fcc36dbe4f0da307094080095eebb2b3906e705e4`

Downloaded binaries are ignored by Git and stored **only inside** `model_runtime/` in A04. Zero remote inference, zero secret/provider credentials, zero billable cloud model calls. Local compute/electricity is **not** claimed to cost $0.

## Implementation and guarantees

First-party A04-authored synthetic source files + manifest SHA256, exact evidence spans and tenant ACLs → model generates actual paraphrased candidate sentence → **independent bounded factual entailment** on count/cadence attributes, source bytes, citations, numerical contradiction checks, revocation/cancel → fsynced event → TCP SSE `claim.verified` to **separate OS process Client** before worker finishes → Client proof ACK → terminal. Provider child exits are required for success, except for safe refusals/cancellations.

The bounded verifier validates only small, declared atomic count/cadence facts. It is NOT arbitrary-domain NLI or qualified original-source semantic truth. If the model hallucinates unsupported text, no `claim.verified` event is allowed. This is a **real model generation** milestone but does **not** admit the native Q34/REL01 hard Gate.

## Reproduce in A04 only

`/opt/homebrew/bin/python3.11 bootstrap.py` (only if source manifest exists/verified) then:
`A04_TEST_MODE=1 A04_LOCAL_MODEL=1 /opt/homebrew/bin/python3.11 -u app.py --port-file evidence/port.txt`

Independently from another OS process:
`/opt/homebrew/bin/python3.11 tests/acceptance.py` (original 21)
`/opt/homebrew/bin/python3.11 tests/real_model_acceptance.py` (8 model-specific cases)

Original and newly added failure logs remain in A04/evidence; a successful rerun never deletes raw failed cases. Run and model adapter are constrained by a 60-second local task deadline, 2 real local decoder calls, 52 max generated tokens each, no automatic retry, isolated process group forced cleanup on cancellation/timeout.

## Out-of-scope external Gate

Previously explicitly refused native frozen Q34 source changes are **not** retried, rehosted, merged or submitted as an equivalent patch. Official 523 / blind200 protected evaluation, native signed Q34 Client pathway, qualified corpus/IdP, and Provider invoice remain their independent Product/Release gates.
