# Round 15 Promptfoo MVP

This directory fixes `promptfoo` at `0.121.19` and uses its official Python Provider and Python assertion interfaces. It is intentionally an offline `stub` harness: it loads the existing 10-case `cultural_product_generation_v2.json` dataset, calls the existing Brief validator, frozen local RAG service, and v2 Prompt compiler, then returns a deterministic evaluator envelope. It does not call Flask, MySQL, DashScope, Met API, Promptfoo Cloud, or `promptfoo share`.

Run from this directory after `npm ci`:

```bash
npm run validate
PROMPTFOO_PYTHON=../../backend/.venv/bin/python npm run eval:stub
PROMPTFOO_PYTHON=../../backend/.venv/bin/python npm run verify:failure-exit
```

The local override selects the repository virtual environment that already supplies the frozen RAG dependencies. In CI, `backend/requirements.txt` is installed into the configured Python interpreter, and the workflow sets `PROMPTFOO_PYTHON=python`.

The first evaluation writes native Promptfoo reports to `evaluation/artifacts/`:

- `round-15-results.json`
- `round-15-report.html`
- `round-15-junit.xml`

They are ignored by Git because they contain test variables and outputs. The scripts set a temporary `PROMPTFOO_CONFIG_DIR` and disable Promptfoo telemetry, so the evaluation neither writes to the user's home directory nor contacts Promptfoo Cloud. `evaluation_metadata` states that all output and timing is `executor_type=stub`, `data_origin=test`, and `measurement_scope=harness_self_test`; it must never be interpreted as real model latency or quality. The separate intentional-failure config is a command-exit test and does not create a report.
