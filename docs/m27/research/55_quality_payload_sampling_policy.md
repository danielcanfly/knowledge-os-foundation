# M27 Quality Payload Sampling Policy

Policy fixed before semantic scorer calls: `unique-question-stratified-all-verified-categories/v1`.

The accepted full523 receipts contain 237 `verified_cited_answer` rows but only 9 unique `(category, question)` semantic prompts across three verified-answer categories: `cited_answer`, `multilingual`, and `retrieval_hard`. The quality-scoring run scores all 9 unique prompts, preserving every verified-answer category and removing only deterministic repeated instances of the same semantic prompt. No score-based selection is permitted. Safe terminals remain excluded from semantic answer-quality aggregation and retain their separate admission correctness evidence.

Payload regeneration is explicitly labeled isolated quality-scoring payload capture and does not replace or mutate accepted admission receipts.
