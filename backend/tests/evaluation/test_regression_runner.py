import json
from pathlib import Path

import pytest

from evaluation import runner


def dataset(cases):
    return {
        "dataset_version": "1.1.0",
        "target_type": runner.TARGET_TYPE,
        "data_origin": "test",
        "cases": cases,
    }


def case(case_id="case-1", **overrides):
    value = {
        "case_id": case_id,
        "category": "blue_and_white_porcelain",
        "prompt": "青花主题",
        "style": "国潮",
        "expected": {"outcome": "success"},
        "required_fields": ["title", "content"],
        "contains_keywords": ["青花"],
        "forbidden_keywords": ["secret"],
        "assertion_strength": "strict",
        "description": "test case",
    }
    value.update(overrides)
    return value


class FakeExecutor:
    executor_type = "fake"
    model_mode = "stub"
    measurement_scope = "harness_self_test"

    def __init__(self, response=None, error=None):
        self.response = response or runner.ExecutorResponse("success", "青花标题", "青花内容")
        self.error = error

    def execute(self, _case):
        if self.error:
            raise self.error
        return self.response


def test_loads_versioned_component_dataset_and_rejects_duplicate_case_id(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(dataset([case(), case("case-1")]), ensure_ascii=False), encoding="utf-8")
    with pytest.raises(runner.DatasetValidationError, match="CASE_ID_INVALID_OR_DUPLICATE"):
        runner.load_dataset(path)


@pytest.mark.parametrize("bad_case", [case(prompt=""), case(expected={"outcome": "unknown"}), case(contains_keywords="not-a-list"), case(assertion_strength="absolute")])
def test_rejects_invalid_component_dataset_schema_and_rules(tmp_path, bad_case):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(dataset([bad_case]), ensure_ascii=False), encoding="utf-8")
    with pytest.raises(runner.DatasetValidationError):
        runner.load_dataset(path)


def test_stub_dataset_is_case_specific_and_never_uses_network():
    source = Path(__file__).resolve().parents[3] / "evaluation" / "datasets" / "cultural_generation_v1.json"
    loaded = runner.load_dataset(source)
    report = runner.run_evaluation(loaded, runner.StubExecutor())
    assert report["target_type"] == runner.TARGET_TYPE
    assert report["measurement_scope"] == "harness_self_test"
    assert report["executor_type"] == report["model_mode"] == "stub"
    assert report["passed"] == report["dataset_case_count"] == report["selected_case_count"] == 5
    blue = runner.StubExecutor().execute(next(item for item in loaded["cases"] if item["case_id"] == "blue-and-white-bookmark"))
    silk = runner.StubExecutor().execute(next(item for item in loaded["cases"] if item["case_id"] == "silk-road-mural"))
    assert "丝路" not in f"{blue.title} {blue.content}"
    assert "传统节日" not in f"{silk.title} {silk.content}"


def test_component_outcome_field_and_keyword_failure_are_explained():
    missing = runner.run_evaluation(dataset([case()]), FakeExecutor(runner.ExecutorResponse("success", "青花标题", None)))
    assert "MISSING_FIELD:content" in missing["cases"][0]["reasons"]
    outcome = runner.run_evaluation(dataset([case(expected={"outcome": "error", "error_code": "MODEL_UNAVAILABLE"})]), FakeExecutor())
    assert {"OUTCOME_MISMATCH", "ERROR_CODE_MISMATCH"} <= set(outcome["cases"][0]["reasons"])
    changed_keyword = runner.run_evaluation(dataset([case(contains_keywords=["错误关键词"])]), FakeExecutor())
    assert changed_keyword["cases"][0]["reasons"] == ["MISSING_KEYWORD:错误关键词"]


def test_timeout_provider_exception_and_report_are_sanitized():
    timeout = runner.run_evaluation(dataset([case()]), FakeExecutor(error=TimeoutError("token=private")))
    assert timeout["cases"][0]["error_code"] == "EXECUTOR_TIMEOUT"
    provider = runner.run_evaluation(dataset([case()]), FakeExecutor(error=RuntimeError("credential-sentinel")))
    rendered = json.dumps(provider)
    assert provider["cases"][0]["error_code"] == "EXECUTOR_ERROR"
    assert "credential-sentinel" not in rendered


def test_per_case_latency_and_summary_percentiles_use_same_samples():
    moments = iter([0.0, 0.001, 0.001, 0.004])
    report = runner.run_evaluation(dataset([case("one"), case("two")]), FakeExecutor(), clock=lambda: next(moments))
    assert [item["latency_ms"] for item in report["cases"]] == [1.0, 3.0]
    assert report["latency"]["sample_count"] == 2
    assert report["latency"]["p50"] == 1.0
    assert report["latency"]["p95"] == 3.0


def test_stub_cli_writes_a_component_scoped_json_report(tmp_path, monkeypatch):
    report_path = tmp_path / "stub-report.json"
    monkeypatch.setattr("sys.argv", ["evaluation.runner", "--executor", "stub", "--report", str(report_path)])
    assert runner.main() == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["target_type"] == runner.TARGET_TYPE
    assert report["measurement_scope"] == "harness_self_test"
    assert report["selection_rule"] == "all dataset cases"


@pytest.mark.parametrize("arguments", [
    ["--executor", "real"],
    ["--executor", "real", "--allow-real-model"],
    ["--executor", "real", "--allow-real-model", "--max-real-cases", "6"],
])
def test_real_execution_requires_explicit_opt_in_and_bounded_case_limit(monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["evaluation.runner", *arguments, "--report", "/tmp/not-written.json"])
    with pytest.raises(SystemExit) as exited:
        runner.main()
    assert exited.value.code == 2


def test_real_executor_requires_a_configured_key_without_instantiating_provider(monkeypatch):
    class UnconfiguredService:
        api_key = None

    monkeypatch.setattr("backend.services.aigc_service.AIGCService", lambda: UnconfiguredService())
    with pytest.raises(RuntimeError, match="REAL_MODEL_NOT_CONFIGURED"):
        runner.RealDashScopeExecutor()


def test_real_report_never_contains_provider_exception_or_authorization():
    report = runner.run_evaluation(
        dataset([case()]),
        FakeExecutor(error=RuntimeError("Authorization: Bearer unit-test-key raw-provider-response")),
    )
    rendered = json.dumps(report)
    assert "unit-test-key" not in rendered
    assert "raw-provider-response" not in rendered
