"""Offline Promptfoo adapter for the existing cultural-product v2 components."""

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPOSITORY_ROOT / "evaluation" / "datasets" / "cultural_product_generation_v2.json"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.domain.cultural_product_brief import validate_cultural_product_request
from backend.prompts.cultural_product_v1 import PROMPT_TEMPLATE_VERSION, build_text_messages
from backend.rag.service import CulturalRagService
from evaluation.promptfoo.security_assertions import evaluate_security_case


EVALUATION_METADATA = {
    "executor_type": "stub",
    "data_origin": "test",
    "measurement_scope": "harness_self_test",
    "latency_scope": "harness_runtime_only",
}
def _cases_by_id():
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return {case["case_id"]: case for case in dataset["cases"]}


def evaluate_case(case_id):
    """Run the existing validation/RAG/prompt path and return a deterministic Stub envelope."""
    case = _cases_by_id().get(case_id)
    if case is None:
        raise ValueError("UNKNOWN_EVALUATION_CASE")
    brief = validate_cultural_product_request(case["request"])
    service = CulturalRagService(root=str(REPOSITORY_ROOT / "rag" / "corpus" / "met_open_access"))
    decision = service.retrieve(brief)
    retrieval_context = {"status": decision.status, "evidence": service.evidence_block(decision)}
    build_text_messages(brief, retrieval_context)
    used_source_ids = [decision.results[0].source_id] if decision.status == "grounded" else []
    citations = service.verified_sources(decision, used_source_ids, decision.status)
    available_source_ids = [result.source_id for result in decision.results]
    return {
        "product_name": "离线文创方案",
        "factual_background": "基于已验证馆藏资料生成背景说明。" if decision.status == "grounded" else "当前资料不足，未使用官方引用。",
        "creative_origin": "离线 Stub 仅验证文化来源与引用边界。",
        "design_concept": "离线 Stub 验证结构化生成契约。",
        "cultural_meaning": "离线 Stub 验证可解释的文化表达。",
        "selling_points": ["明确产品形态", "可核对引用边界", "结构化字段展示"],
        "used_source_ids": used_source_ids,
        "evidence_status": decision.status,
        "citations": citations,
        "available_source_ids": available_source_ids,
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "evaluation_metadata": EVALUATION_METADATA,
    }


def call_api(_prompt, options, context):
    """Promptfoo entry point; Round 16 has no authorized real-model executor."""
    config = options.get("config", {})
    executor_type = config.get("executor_type", "stub")
    if executor_type == "real":
        return {"output": "", "error": "REAL_EVALUATION_DISABLED"}
    if executor_type != "stub":
        return {"output": "", "error": "STUB_EXECUTOR_REQUIRED"}
    case_id = context.get("vars", {}).get("case_id")
    try:
        if case_id and case_id.startswith("security-"):
            response = evaluate_security_case(case_id)
            metadata = {**EVALUATION_METADATA, "security_category": response["security_category"]}
            return {"output": json.dumps(response, ensure_ascii=False), "metadata": metadata}
        response = evaluate_case(case_id)
    except Exception:
        return {"output": "", "error": "EVALUATION_PROVIDER_FAILED"}
    return {"output": json.dumps(response, ensure_ascii=False), "metadata": EVALUATION_METADATA}
