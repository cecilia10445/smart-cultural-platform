import json
from types import SimpleNamespace

import evaluation.promptfoo.round17c_deepseek_provider as provider


def _individual() -> str:
    return json.dumps({"dimensions": {name: {"score": 4, "reason": "中文短理由"} for name in provider.DIMENSIONS}, "final_reason": "中文最终理由"}, ensure_ascii=False)


def _response(content, *, finish_reason="stop", reasoning=None, refusal=None):
    message = SimpleNamespace(content=content, reasoning_content=reasoning, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)], usage=SimpleNamespace(prompt_tokens=9, completion_tokens=10, total_tokens=19), model="deepseek-v4-pro", _request_id="request-safe")


def _call(monkeypatch, tmp_path, response):
    source = tmp_path / "judge-inputs.json"
    source.write_text(json.dumps({"brief": {}, "arms": {"baseline": {}, "skill_guided": {}}}), encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response)), close=lambda: None)
    monkeypatch.setattr(provider, "build_deepseek_client", lambda **_: fake)
    return provider.call_api("ignored", {"config": {"job": "individual-baseline", "base_url": "https://api.deepseek.com", "trust_env": "false", "judge_inputs_path": str(source)}}, {})


def test_full_json_has_utf8_diagnostics_and_disabled_thinking(monkeypatch, tmp_path):
    result = _call(monkeypatch, tmp_path, _response(_individual(), reasoning="不应显示"))
    assert "error" not in result
    assert result["metadata"]["response_diagnostics"]["thinking"] == {"type": "disabled"}
    assert result["metadata"]["response_diagnostics"]["reasoning_content_chars"] == 4
    assert json.loads(json.dumps(result, ensure_ascii=False))["output"].find("中文短理由") >= 0


def test_prompt_contract_forbids_schema_wrapper():
    prompt = provider._anonymous_prompt("individual-baseline", {"brief": {}, "arms": {"baseline": {}, "skill_guided": {}}})
    assert "required_json_shape" not in prompt
    assert "top_level_output" in prompt


def test_length_empty_truncated_and_refusal_are_promptfoo_errors(monkeypatch, tmp_path):
    cases = [
        (_response('{"dimensions":', finish_reason="length"), "DEEPSEEK_OUTPUT_TRUNCATED"),
        (_response(""), "DEEPSEEK_OUTPUT_EMPTY"),
        (_response('{"dimensions":'), "DEEPSEEK_OUTPUT_INVALID_JSON"),
        (_response(_individual(), refusal="拒绝"), "DEEPSEEK_PROVIDER_REFUSAL"),
    ]
    for response, code in cases:
        assert _call(monkeypatch, tmp_path, response)["error"] == code
