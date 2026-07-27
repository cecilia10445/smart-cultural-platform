"""Project-specific Promptfoo assertion for verified cultural-source boundaries."""

import json
import re
import sys


EXPECTED_FIELDS = {
    "available_source_ids",
    "citations",
    "creative_origin",
    "design_concept",
    "cultural_meaning",
    "evidence_status",
    "evaluation_metadata",
    "factual_background",
    "selling_points",
    "product_name",
    "prompt_template_version",
    "used_source_ids",
}
REQUIRED_METADATA = {
    "executor_type": "stub",
    "data_origin": "test",
    "measurement_scope": "harness_self_test",
    "latency_scope": "harness_runtime_only",
}
SENSITIVE_PATTERN = re.compile(r"DASHSCOPE_API_KEY|Authorization|Bearer\\s+|SYSTEM[_ ]PROMPT|sk-[A-Za-z0-9]", re.IGNORECASE)


def evaluate_output(output):
    try:
        data = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"pass": False, "score": 0, "reason": "output is not JSON"}
    errors = []
    if set(data) != EXPECTED_FIELDS:
        errors.append("unexpected response field set")
    for field in ("product_name", "factual_background", "creative_origin", "design_concept", "cultural_meaning"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"{field} must be non-empty")
    points = data.get("selling_points")
    if not isinstance(points, list) or not 3 <= len(points) <= 5 or any(not isinstance(point, str) or not point.strip() for point in points):
        errors.append("selling_points must contain 3 to 5 non-empty strings")
    if data.get("prompt_template_version") != "cultural-product-rag-v2":
        errors.append("unexpected prompt template version")
    if data.get("evaluation_metadata") != REQUIRED_METADATA:
        errors.append("Stub metadata is incomplete or misleading")
    used_ids = data.get("used_source_ids")
    available_ids = data.get("available_source_ids")
    citations = data.get("citations")
    if not isinstance(used_ids, list) or len(used_ids) != len(set(used_ids)):
        errors.append("used_source_ids must be a unique list")
    if not isinstance(available_ids, list) or len(available_ids) != len(set(available_ids)):
        errors.append("available_source_ids must be a unique list")
    if isinstance(used_ids, list) and isinstance(available_ids, list) and not set(used_ids).issubset(available_ids):
        errors.append("used_source_ids includes an unavailable source")
    status = data.get("evidence_status")
    if status not in {"grounded", "insufficient_evidence"}:
        errors.append("invalid evidence_status")
    if not isinstance(citations, list):
        errors.append("citations must be a list")
    else:
        citation_ids = [item.get("source_id") for item in citations if isinstance(item, dict)]
        if citation_ids != used_ids:
            errors.append("citations do not match used_source_ids")
        for citation in citations:
            if not isinstance(citation, dict) or not all(isinstance(citation.get(key), str) and citation[key] for key in ("source_id", "title", "source_url", "license")):
                errors.append("citation is incomplete")
                break
            if not citation["source_url"].startswith("https://www.metmuseum.org/"):
                errors.append("citation is not a verified Met official URL")
                break
    if status == "insufficient_evidence" and (used_ids or citations):
        errors.append("insufficient_evidence must not carry citations")
    if status == "grounded" and (not used_ids or not citations):
        errors.append("grounded output requires verified citations")
    if SENSITIVE_PATTERN.search(json.dumps(data, ensure_ascii=False)):
        errors.append("output contains sensitive credential or prompt marker")
    return {"pass": not errors, "score": 1 if not errors else 0, "reason": "; ".join(errors) or "verified RAG boundary"}


def get_assert(output, _context):
    """Promptfoo Python assertion entry point."""
    return evaluate_output(output)


if __name__ == "__main__":
    print(json.dumps(evaluate_output(sys.argv[1]), ensure_ascii=False))
