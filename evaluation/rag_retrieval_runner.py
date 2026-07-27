"""Versioned offline evaluation for the frozen cultural RAG retriever."""

import argparse
import json
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.rag.service import CulturalRagService


def evaluate_case(service, case):
    decision = service.decide_query(case["query"])
    retrieved_ids = [item.source_id for item in decision.results]
    expected_ids = case.get("expected_source_ids", [])
    expected_status = case["expected_status"]
    if case["case_type"] == "targeted":
        passed = decision.status == expected_status and any(
            source_id in retrieved_ids for source_id in expected_ids
        )
    else:
        passed = decision.status == expected_status and not retrieved_ids
    return {
        "id": case["id"],
        "case_type": case["case_type"],
        "query": case["query"],
        "expected_status": expected_status,
        "actual_status": decision.status,
        "decision_reason": decision.reason,
        "expected_source_ids": expected_ids,
        "retrieved_source_ids": retrieved_ids,
        "candidate_source_ids": [item.source_id for item in decision.candidates],
        "candidate_scores": [item.score for item in decision.candidates],
        "passed": passed,
    }


def build_report(dataset, service):
    results = [evaluate_case(service, case) for case in dataset["cases"]]
    targeted = [item for item in results if item["case_type"] == "targeted"]
    no_match = [item for item in results if item["case_type"] == "no_match"]
    recall_at_1 = sum(
        bool(item["retrieved_source_ids"])
        and item["retrieved_source_ids"][0] in item["expected_source_ids"]
        for item in targeted
    ) / len(targeted)
    recall_at_3 = sum(
        bool(set(item["retrieved_source_ids"]) & set(item["expected_source_ids"]))
        for item in targeted
    ) / len(targeted)
    reciprocal_ranks = []
    for item in targeted:
        ranks = [
            item["retrieved_source_ids"].index(source_id) + 1
            for source_id in item["expected_source_ids"]
            if source_id in item["retrieved_source_ids"]
        ]
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0)
    counts = {
        case_type: sum(item["case_type"] == case_type for item in results)
        for case_type in ("targeted", "no_match", "ambiguous")
    }
    return {
        "dataset_version": dataset["dataset_version"],
        "retriever_version": service.retriever_version,
        "sample_size": len(results),
        "case_type_counts": counts,
        "metric_scope": "six targeted cases; no_match accuracy excludes the ambiguity case",
        "Recall@1": recall_at_1,
        "Recall@3": recall_at_3,
        "MRR": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "no_match_accuracy": sum(
            item["actual_status"] == "insufficient_evidence" for item in no_match
        ) / len(no_match),
        "failed_case_ids": [item["id"] for item in results if not item["passed"]],
        "limitations": (
            "Only nine curated cases and six frozen objects are measured; "
            "the score and ambiguity thresholds are not evidence of general retrieval quality."
        ),
        "cases": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/cultural_rag_retrieval_v1.json",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    report = build_report(dataset, CulturalRagService("rag/corpus/met_open_access"))
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if not report["failed_case_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
