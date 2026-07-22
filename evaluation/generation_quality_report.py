"""Read-only, content-free report for persisted v2 generation attempts.

This tool reports database observability records.  It never calls a model and
never exports briefs, prompts, generated text, credentials, or provider URLs.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def build_quality_report(attempts, metrics):
    failures = [row for row in attempts if row["status"] == "FAILED"]
    running = [row for row in attempts if row["status"] == "RUNNING"]
    by_failure = Counter(
        "%s:%s" % (row.get("failed_stage") or "unknown", row.get("error_code") or "unknown")
        for row in failures
    )
    latency_samples = defaultdict(list)
    token_values = {"input_tokens": [], "output_tokens": [], "total_tokens": []}
    for metric in metrics:
        latency_samples[metric["stage"]].append(metric["latency_ms"])
        for key in token_values:
            if metric.get(key) is not None:
                token_values[key].append(metric[key])
    return {
        "report_kind": "generation_quality_observability",
        "data_origin": "database_observability_records",
        "request_count": len(attempts),
        "succeeded_count": sum(row["status"] == "SUCCEEDED" for row in attempts),
        "failed_count": len(failures),
        "running_count": len(running),
        "running_requests": [{key: row.get(key) for key in ("request_id", "brief_sha256")} for row in running],
        "failure_distribution": dict(sorted(by_failure.items())),
        "latency_samples_ms": dict(sorted(latency_samples.items())),
        "token_usage": {key: (sum(values) if values else None) for key, values in token_values.items()},
        "failures": [
            {key: row.get(key) for key in ("request_id", "failed_stage", "error_code", "brief_sha256")}
            for row in failures
        ],
    }


def load_report_rows(mysql_service):
    attempts = mysql_service.execute_query(
        "SELECT request_id,status,failed_stage,error_code,brief_sha256 FROM generation_attempts ORDER BY created_at ASC",
        (), max_retries=0,
    ) or []
    metrics = mysql_service.execute_query(
        "SELECT request_id,stage,latency_ms,input_tokens,output_tokens,total_tokens FROM model_call_metrics ORDER BY created_at ASC,id ASC",
        (), max_retries=0,
    ) or []
    return attempts, metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a content-free v2 observability report")
    parser.add_argument("--output", required=True, help="JSON report path")
    parser.add_argument("--failure-candidates", help="optional JSON candidate export path")
    args = parser.parse_args(argv)
    from backend.services.mysql_service import MySQLService
    from backend.config import load_settings

    settings = load_settings()
    service = MySQLService(settings.mysql_host, settings.mysql_port, settings.mysql_user, settings.mysql_password, settings.mysql_database)
    if not service.connect():
        raise SystemExit("database unavailable")
    attempts, metrics = load_report_rows(service)
    report = build_quality_report(attempts, metrics)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.failure_candidates:
        Path(args.failure_candidates).write_text(json.dumps(report["failures"], ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
