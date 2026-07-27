# Promptfoo offline evaluation

This directory fixes `promptfoo` at `0.121.19` and uses its official Python Provider and Python assertion interfaces. It is intentionally an offline `stub` harness: it loads the existing 10-case `cultural_product_generation_v2.json` dataset, calls the existing Brief validator, frozen local RAG service, and v2 Prompt compiler, then returns a deterministic evaluator envelope. It does not call Flask, MySQL, DashScope, Met API, Promptfoo Cloud, or `promptfoo share`.

Run from this directory after `npm ci`:

```bash
npm run validate
PROMPTFOO_PYTHON=../../backend/.venv/bin/python npm run eval:stub
PROMPTFOO_PYTHON=../../backend/.venv/bin/python npm run verify:failure-exit
```

The local override selects the repository virtual environment that already supplies the frozen RAG dependencies. In CI, `backend/requirements.txt` is installed into the configured Python interpreter, and the workflow sets `PROMPTFOO_PYTHON=python`.

Round 16 extends the same pinned framework with deterministic security-boundary cases:

```bash
PROMPTFOO_PYTHON=../../backend/.venv/bin/python npm run eval:security
```

This writes `latest.json`, `latest.html`, and `latest.junit.xml` under `evaluation/artifacts/`. The JSON is the fixed local input to the administrator-only quality summary endpoint; that endpoint returns only run counts, status, timestamp, attack-success rate, and category aggregates. It never returns Promptfoo prompts, responses, payloads, provider configuration, or authorization material. Missing, oversized, malformed, and structurally incompatible reports are reported as unavailable.

The first evaluation writes native Promptfoo reports to `evaluation/artifacts/`:

- `round-15-results.json`
- `round-15-report.html`
- `round-15-junit.xml`

They are ignored by Git because they contain test variables and outputs. The scripts set a temporary `PROMPTFOO_CONFIG_DIR` and disable Promptfoo telemetry, so the evaluation neither writes to the user's home directory nor contacts Promptfoo Cloud. `evaluation_metadata` states that all output and timing is `executor_type=stub`, `data_origin=test`, and `measurement_scope=harness_self_test`; it must never be interpreted as real model latency or quality. The separate intentional-failure config is a command-exit test and does not create a report.

There is no authorized real-model executor in Round 16: `executor_type=real` fails closed. Consequently the default and CI paths cannot call DashScope, generate images, write databases, retry model calls, or persist model bodies. A future explicitly authorized text-only lane would require a separate reviewed change and must cap its dataset at 12 cases.
