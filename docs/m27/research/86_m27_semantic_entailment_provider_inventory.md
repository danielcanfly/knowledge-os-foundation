# Stage 30F provider inventory
| Candidate | Availability | Invocation | Schema | Risks / limits | Decision |
| --- | --- | --- | --- | --- | --- |
| M27 Stage30E literal | Available | M27 native | Deterministic but lexical only | Fails semantic paraphrase, translation and cluster | Rejected |
| M27 independent quality scorer | Available | Quality payload validation | Structured receipts | No inference about claim support | Rejected |
| Local NLI transformer | Not present in host or inspected runtime | No inference model installed | N/A | Dependency missing | Not selected |
| Cloudflare GPT-OSS | Generic M26 router exists, but no matching credentials observed in isolated candidate environment | Generic Cloudflare client | Prompt-constrained JSON possible | Network/quotas, not calibrated | Not selected |
| MiniMax-M3 | Existing generic client and runtime configuration observed, secret value never read or exported | Existing MiniMaxClient.call in active isolated candidate, narrow NLI messages only | Prompt-constrained JSON, validated fail-closed in M27 native adapter | Network dependency, latency, unproven NLI performance | Offline candidate only |
| M26 mature answer composer | Present | Forbidden | N/A | Would violate independent-verifier boundary | Excluded |

The generic provider must not be considered calibrated or publication-ready solely because an API call returns successfully.
