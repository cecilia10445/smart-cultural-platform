# Round 16 quality report API contract

The administrator-only quality endpoint reads the fixed local file `evaluation/artifacts/latest.json`. Clients cannot provide a path.

`GET /api/dashboard/quality-report` returns a JSON envelope with `status=success` and a redacted `data` object. The object contains run identity/time/status, totals, attack-success rate, risk counters, category aggregates, and `cases`. Every case has exactly these fields:

```json
{
  "case_id": "security-unknown-field",
  "category": "unknown-field",
  "outcome": "passed",
  "stable_code": "INVALID_REQUEST_FORMAT",
  "assertion_name": "security_boundary"
}
```

The endpoint never returns Promptfoo prompts, response bodies, attack payloads, confirmed facts, provider requests or responses, system prompts, URLs, headers, environment variables, credentials, API keys, Authorization values, or raw stack traces. Missing, oversized, unreadable, malformed, or incompatible reports return `503` with `status=unavailable` and `code=QUALITY_REPORT_UNAVAILABLE`.

`GET /api/dashboard/quality-report/html` uses the same administrator authentication and a fixed server-side path. It ignores query paths, refuses missing or over-10 MiB files, and returns `Content-Disposition: attachment; filename=promptfoo-security-report.html`. The HTML is never embedded in the dashboard.

The report is an offline security and robustness regression using `executor_type=stub` and `measurement_scope=harness_self_test`; passing all 23 cases is not a claim of absolute real-model safety.
