# Round 17C experimental status

Round 17C is an isolated text-only evaluation harness, not a production-v2 generation integration.

## Experimental business text path

`POST /api/v2/cultural-products/generate-with-text-skill` integrates the
audited text-only flow without changing the existing image-and-MySQL V2
endpoint. It freezes local RAG evidence, receives one native Qwen text-Skill
tool call, then produces one final text result. It writes a sealed local
artifact and makes no image, DeepSeek, or database call.

The operations page reads only these business-generation artifacts. It shows
source IDs, selected text Skill, native tool trajectory, delivery text, timing
and observed calls. Judge scores, winners, and A/B data are intentionally
hidden until a later evaluation round produces a valid result.

- A real Baseline and Skill-guided text A/B were generated from the same Brief, frozen evidence, and final-output schema.
- The Qwen planner emitted a native `load_generation_skill` tool call. The Round 17B safe loader audited and loaded one text Skill (`retail-product-copy`).
- Qwen calls were 3; image calls and database writes were 0.
- The DeepSeek Judge is **inconclusive**. Its strict individual-output contract was violated, so `evaluation_validity=judge_parse_error`; no winner may be displayed.
- Raw 5/5 values in malformed Judge payloads are not valid official scores and must not be used as quality evidence.
- Round 17D, not this commit, is responsible for a defensible quality conclusion.
