# Usage report — Ghost Data Audit

## Final prediction run (the run that produced output.csv)

- Run: `runs/final-20261025T124654Z`. Command: `python3 code/main.py --dataset dataset --output output.csv --no-llm`.
- Requests processed: **518**. Unresolved: 0. `summary.json` records `model_calls: 0`.
- **Model calls during prediction: 0. Tokens: 0. Cost: $0.** The run works fully offline, with deterministic parsing, local ONNX OCR (no provider tokens) and SQL sandboxing.
- The run replays **cached two-model OpenAI document classifications** from `code/prompts/document_classifications.json`. Each cache entry is keyed by the document's SHA-256, so a changed document would not match the cache.
  - evidence_46 -> SUPPORT_ATTACHMENT (rule_06). openai:gpt-5.5 confidence 0.78; openai:gpt-5.4-mini confidence 0.98; the two models agreed.
  - evidence_18 -> USER_EXPORT (rule_09). Both models agreed.
  - A classification is used only when `agreed: true`.

## Offline development calls that built the cache (`code/classify_documents.py`)

| Call set | Model | Docs | Tokens (recorded) |
|---|---|---:|---:|
| Initial classification | openai:gpt-5.5 | 3 | ~3,701 total |
| Initial classification | openai:gpt-5.4-mini | 3 | ~2,921 total |
| Re-run (the 2 cached docs) | gpt-5.5 + gpt-5.4-mini | 2 | not recorded; **estimated** at about 2/3 of the initial run: ~2,470 (gpt-5.5) + ~1,950 (mini) |

The script calls each model at most once per document (`max_calls=1`, `retries=0`, max output 3,000 tokens, max input 24 KB).

## Advisory LLM case reviews (QA only; they did not change predictions)

Source: `runs/agents/qa/llm-review-*.json`, `usage` field.

| Model | Attempted calls | Successful calls | Input | Output | of which reasoning | Cached input | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| openai:gpt-5.5 | 40 | 3 | 6,299 | 1,335 | 1,257 | 1,792 | 7,634 |
| openai:gpt-5.4-mini | 36 | 7 | 14,258 | 972 | 0 | 0 | 15,230 |

Attempted calls that did not succeed were stopped by the call budget or failed before returning usage, so they consumed no recorded tokens.

## Totals

| Model | Recorded tokens | + estimated re-run | Estimated total |
|---|---:|---:|---:|
| openai:gpt-5.5 | 11,335 | ~2,470 | ~13,800 |
| openai:gpt-5.4-mini | 18,151 | ~1,950 | ~20,100 |
| **Overall** | **29,486** | ~4,420 | **~33,900** |

Averages over the 518 requests: recorded ~56.9 tokens/request (gpt-5.5 21.9, mini 35.0); including the estimated re-run, ~65.5 tokens/request. All of these tokens are one-time development or QA costs. The marginal cost of reproducing output.csv is 0 tokens.

## Estimated cost (ESTIMATES, not invoices)

**Assumed** list prices; check the current OpenAI pricing page:
- gpt-5.5: $1.25 per 1M input tokens and $10.00 per 1M output tokens.
- gpt-5.4-mini: $0.25 per 1M input tokens and $2.00 per 1M output tokens.

There is no input/output split for the classification calls, so they are priced as if every token were output. This is an upper bound.

| Item | Estimate |
|---|---:|
| gpt-5.5 reviews (6,299 in / 1,335 out) | ~$0.021 |
| gpt-5.4-mini reviews (14,258 in / 972 out) | ~$0.006 |
| gpt-5.5 classification (3,701 + ~2,470) | <= ~$0.062 |
| gpt-5.4-mini classification (2,921 + ~1,950) | <= ~$0.010 |
| **Overall** | **<= ~$0.10 (about $0.0002 per request)** |
| Final prediction run | **$0** |

Reproduce offline with `--no-llm`. Rebuilding the cache needs `.env` with `OPENAI_API_KEY` (copy it from `.env.example`) and `python3 code/classify_documents.py --dataset dataset`.
