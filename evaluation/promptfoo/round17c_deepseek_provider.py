"""Minimal Promptfoo target for the four real DeepSeek Judge jobs only."""
from __future__ import annotations
import os
import json
import hashlib
from typing import Any
import httpx
from openai import OpenAI


JUDGE_MAX_TOKENS = 1200
DIMENSIONS = (
    "professional_readability", "product_title_recognition", "brief_fit", "cultural_specificity",
    "design_executability", "factual_fidelity", "delivery_format", "conciseness_non_repetition",
)


def _as_bool(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _resolved_config(value: Any, environment_name: str, default: str | None = None) -> str | None:
    """File-provider YAML leaves ${VAR} literal, so resolve only declared values."""
    if isinstance(value, str) and value.strip() and not (value.startswith("${") and value.endswith("}")):
        return value
    return os.environ.get(environment_name) or default


def build_deepseek_client(*, api_key: str, base_url: str, trust_env: bool, transport: httpx.BaseTransport | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        http_client=httpx.Client(
            transport=transport,
            trust_env=trust_env,
            timeout=httpx.Timeout(connect=10, read=90, write=30, pool=10),
        ),
    )

def _anonymous_prompt(job: str, payload: dict[str, Any]) -> str:
    brief = payload["brief"]
    arms = payload["arms"]
    if job == "individual-baseline": content = {"candidate": arms["baseline"]}
    elif job == "individual-guided": content = {"candidate": arms["skill_guided"]}
    elif job == "pairwise-ab": content = {"candidate_0": arms["baseline"], "candidate_1": arms["skill_guided"]}
    elif job == "pairwise-ba": content = {"candidate_0": arms["skill_guided"], "candidate_1": arms["baseline"]}
    else: raise ValueError("ROUND17C_JUDGE_JOB_INVALID")
    if job.startswith("individual-"):
        contract = {
            "dimensions": {
                name: {"score": "integer 1..5", "reason": "one Chinese sentence, <=24 chars"}
                for name in DIMENSIONS
            },
            "final_reason": "string",
        }
    else:
        contract = {
            "winner_index": "integer 0 or 1",
            "winner_candidate_id": "candidate_0 or candidate_1; must match winner_index",
            "final_reason": "<=40 chars; explicitly name only winning candidate ID and one key difference",
        }
    instructions = {
        "role": "You judge anonymous candidate text only. Do not infer hidden provenance.",
        "requirements": [
            "Return exactly one compact JSON object and no markdown or chain of thought.",
            "The returned object itself must use exactly the following top-level keys; never wrap it in any schema or contract key.",
            "Individual reasons must be one short sentence; pairwise has only a short final_reason.",
            "Assess product recognizability, factual fidelity, direct deliverability, and repetition.",
            "Do not mention source IDs, tools, skills, or hidden arm identities.",
        ],
        "top_level_output": contract,
    }
    return json.dumps({"instructions": instructions, "brief": brief, **content}, ensure_ascii=False, sort_keys=True)


def _sanitized_provider_error(exc: Exception) -> dict[str, Any]:
    """Return only stable, non-secret provider diagnostics for Promptfoo artifacts."""
    response = getattr(exc, "response", None)
    body: Any = getattr(exc, "body", None)
    if body is None and response is not None:
        try:
            body = response.json()
        except Exception:
            body = None
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    code = None
    message = None
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            message = error.get("message")
    if message is None:
        message = getattr(exc, "message", None)
    if not isinstance(message, str):
        message = str(exc)
    # Never write a URL query, headers, or arbitrary long provider payload.
    message = message.replace(os.environ.get("DEEPSEEK_API_KEY", ""), "[REDACTED]")[:500]
    return {"exception_class": type(exc).__name__, "http_status": status, "provider_error_code": code, "provider_message": message}


def _response_diagnostics(response: Any, *, content: str, reasoning_content: Any, refusal: Any, model: str) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    return {
        "finish_reason": getattr(response.choices[0], "finish_reason", None),
        "content_chars": len(content),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "reasoning_content_present": bool(reasoning_content),
        "reasoning_content_chars": len(reasoning_content) if isinstance(reasoning_content, str) else 0,
        "refusal": refusal if isinstance(refusal, str) and len(refusal) <= 500 else None,
        "usage": {"prompt_tokens": getattr(usage, "prompt_tokens", None), "completion_tokens": getattr(usage, "completion_tokens", None), "total_tokens": getattr(usage, "total_tokens", None)},
        "model": getattr(response, "model", None) or model,
        "provider_request_id": getattr(response, "_request_id", None),
        "configured_max_tokens": JUDGE_MAX_TOKENS,
        "thinking": {"type": "disabled"},
    }


def _validate_output(job: str, content: str, diagnostics: dict[str, Any]) -> str | None:
    if diagnostics["finish_reason"] == "length":
        return "DEEPSEEK_OUTPUT_TRUNCATED"
    if diagnostics["refusal"]:
        return "DEEPSEEK_PROVIDER_REFUSAL"
    if not content.strip():
        return "DEEPSEEK_OUTPUT_EMPTY"
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return "DEEPSEEK_OUTPUT_INVALID_JSON"
    if not isinstance(value, dict):
        return "DEEPSEEK_OUTPUT_INVALID_JSON"
    if job.startswith("individual-"):
        dimensions = value.get("dimensions")
        if set(value) != {"dimensions", "final_reason"} or not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS) or not isinstance(value.get("final_reason"), str) or not value["final_reason"].strip():
            return "DEEPSEEK_OUTPUT_SCHEMA_INVALID"
        for item in dimensions.values():
            if not isinstance(item, dict) or set(item) != {"score", "reason"} or not isinstance(item.get("score"), int) or not 1 <= item["score"] <= 5 or not isinstance(item.get("reason"), str) or not item["reason"].strip():
                return "DEEPSEEK_OUTPUT_SCHEMA_INVALID"
    else:
        winner = value.get("winner_index")
        candidate = value.get("winner_candidate_id")
        reason = value.get("final_reason")
        if set(value) != {"winner_index", "winner_candidate_id", "final_reason"} or not isinstance(winner, int) or winner not in {0, 1} or candidate != f"candidate_{winner}" or not isinstance(reason, str) or not reason.strip():
            return "DEEPSEEK_OUTPUT_SCHEMA_INVALID"
    return None


def call_api(prompt: str, options: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {}) if isinstance(options, dict) else {}
    key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = _resolved_config(config.get("base_url"), "ROUND17C_DEEPSEEK_BASE_URL")
    model = _resolved_config(config.get("model"), "ROUND17C_DEEPSEEK_MODEL", "deepseek-v4-pro")
    job = config.get("job")
    trust_env = _as_bool(_resolved_config(config.get("trust_env"), "ROUND17C_DEEPSEEK_TRUST_ENV", "false"))
    source = config.get("judge_inputs_path") or os.environ.get("ROUND17C_JUDGE_INPUTS_PATH")
    if isinstance(source, str) and source:
        try:
            prompt = _anonymous_prompt(str(job), json.loads(open(source, encoding="utf-8").read()))
        except Exception:
            return {"output": "", "error": "ROUND17C_JUDGE_INPUTS_INVALID", "metadata": {"round17c_judge_job": job}}
    if not key or not isinstance(base_url, str) or not base_url:
        return {"output": "", "error": "DEEPSEEK_CONFIGURATION_REQUIRED", "metadata": {"value_recorded": False}}
    client = build_deepseek_client(api_key=key, base_url=base_url, trust_env=trust_env)
    try:
        response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=JUDGE_MAX_TOKENS, response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}})
        message = response.choices[0].message
        content = message.content or ""
        diagnostics = _response_diagnostics(response, content=content, reasoning_content=getattr(message, "reasoning_content", None), refusal=getattr(message, "refusal", None), model=str(model))
        validation_error = _validate_output(str(job), content, diagnostics)
        diagnostics["json_parse_status"] = validation_error or "valid"
        metadata = {"round17c_judge_job": job, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "response_diagnostics": diagnostics, "retries": 0}
        if validation_error:
            return {"output": content, "error": validation_error, "metadata": metadata}
        return {"output": content, "metadata": metadata}
    except Exception as exc:
        return {"output": "", "error": f"DEEPSEEK_PROVIDER_{type(exc).__name__}", "metadata": {"round17c_judge_job": config.get("job"), "retries": 0, "provider_error": _sanitized_provider_error(exc)}}
    finally:
        client.close()
