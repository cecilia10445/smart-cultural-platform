import hashlib
import json

import pytest
from pydantic import ValidationError

from evaluation.round17c_contract import Round17CFinalOutput, assess_pairwise_consistency, text_skill_catalog, validate_final_output
from evaluation.round17c_judge import DIMENSIONS, extract_promptfoo_jobs, normalize_judge_results, opaque_candidate_mapping
from evaluation.round17c_runner import create_blocked_run, seal_run
from backend.agents.skill_registry import SKILLS


EVIDENCE = {"status": "grounded", "sources": [{"source_id": "other-source", "title": "Other", "evidence": {}, "license": "CC0", "source_url": "https://example.invalid"}]}
GOOD = {"product_copy": "清韵折叠阅读灯以竹木和半透明纸罩带来温和光线，适合书房与旅行阅读。", "image_design_spec": "画面展示展开的折叠阅读灯，突出竹木纹理、纸罩透光、米白墨色和清晰留白。", "used_source_ids": ["other-source"]}


def _judge(score=4):
    return json.dumps({"dimensions": {key: {"score": score, "reason": "fixture"} for key in DIMENSIONS}, "final_reason": "fixture"}, ensure_ascii=False)


def test_final_schema_rejects_json_field_shell_and_source_id():
    for bad in (
        {**GOOD, "product_copy": '{"标题":"阅读灯"}'},
        {**GOOD, "product_copy": "标题：清韵折叠阅读灯，适合阅读并采用竹木。"},
        {**GOOD, "image_design_spec": "met-other-source 的画面说明应被拒绝，因为 ID 不面向用户。"},
    ):
        with pytest.raises(ValidationError):
            Round17CFinalOutput(**bad)


def test_final_schema_and_citations_are_common_and_evidence_bound():
    output = Round17CFinalOutput(**GOOD)
    assert validate_final_output(output, EVIDENCE).model_dump() == output.model_dump()
    with pytest.raises(Exception):
        validate_final_output(Round17CFinalOutput(**{**GOOD, "used_source_ids": ["not-frozen"]}), EVIDENCE)
    with pytest.raises(Exception):
        validate_final_output(output, {"status": "grounded", "sources": []})


def test_text_catalog_excludes_every_visual_skill_without_hardcoded_choice():
    catalog = text_skill_catalog(SKILLS)
    assert catalog and all(item["kind"] == "text" for item in catalog)
    assert {item["skill_id"] for item in catalog}.isdisjoint({key for key, skill in SKILLS.items() if skill.kind == "visual"})


def test_position_bias_and_conflict_are_inconclusive():
    mapping = opaque_candidate_mapping()
    from evaluation.round17c_contract import JudgePairwiseResult
    ab = JudgePairwiseResult(winner_index=1, winner_candidate_id="candidate_1", final_reason="candidate_1")
    ba = JudgePairwiseResult(winner_index=1, winner_candidate_id="candidate_1", final_reason="candidate_1")
    assert assess_pairwise_consistency(ab, ba, mapping) == ("inconclusive_position_bias", None)
    normalized = normalize_judge_results(_judge(), _judge(), ab.model_dump_json(), ba.model_dump_json())
    assert normalized["evaluation_validity"] == "inconclusive_position_bias"


def test_judge_parse_failure_has_no_default_score():
    result = normalize_judge_results("not json", _judge(), json.dumps({"winner_index": 0, "winner_candidate_id": "candidate_0", "final_reason": "candidate_0"}), json.dumps({"winner_index": 1, "winner_candidate_id": "candidate_1", "final_reason": "candidate_1"}))
    assert result["evaluation_validity"] == "judge_parse_error"
    assert result["individual"]["baseline"]["score"] is None


def test_judge_requires_exact_dimension_set_and_promptfoo_exactly_four_jobs():
    raw = json.loads(_judge()); raw["dimensions"]["unexpected"] = {"score": 4, "reason": "no"}
    assert normalize_judge_results(json.dumps(raw), _judge(), json.dumps({"winner_index": 0, "winner_candidate_id": "candidate_0", "final_reason": "candidate_0"}), json.dumps({"winner_index": 1, "winner_candidate_id": "candidate_1", "final_reason": "candidate_1"}))["evaluation_validity"] == "judge_parse_error"
    jobs = {"individual-baseline", "individual-guided", "pairwise-ab", "pairwise-ba"}
    payload = {"results": {"results": [{"metadata": {"round17c_judge_job": job}, "response": {"output": "{}"}} for job in jobs]}}
    assert set(extract_promptfoo_jobs(payload)) == jobs


def test_blocked_run_has_observed_zero_calls_and_is_sealed(tmp_path):
    run = create_blocked_run(root=tmp_path)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["actual_calls"] == {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0}
    checksums = json.loads((run / "sha256sums.json").read_text())["sha256"]
    assert all(len(value) == 64 for value in checksums.values())
    with pytest.raises(Exception):
        seal_run(run)
