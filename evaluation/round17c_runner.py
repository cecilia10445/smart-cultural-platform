"""Round 17C clean rebuild: fair, text-only controlled A/B primitives.

Real providers are never constructed unless a caller explicitly supplies an
already-created client. The CLI/default path only emits a blocked artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent, PromptedOutput, RunContext, ToolOutput, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.alibaba import AlibabaProvider

from backend.agents.skill_registry import SKILLS, load_skill
from backend.domain.cultural_product_brief import validate_cultural_product_request
from backend.rag.models import RetrievalDecision, RetrievalResult
from backend.rag.service import CulturalRagService
from evaluation.round17c_contract import (
    GuidedPlan,
    Round17CContractError,
    Round17CFinalOutput,
    canonical_json,
    sha256_json,
    text_skill_catalog,
    validate_final_output,
)


RUNNER_VERSION = "round17c-clean-1.0"
ROOT = Path(__file__).resolve().parent / "artifacts" / "round-17c-clean"
ROUND17C_PROFILE = OpenAIModelProfile(
    default_structured_output_mode="prompted",
    supports_json_object_output=True,
    openai_supports_tool_choice_required=True,
    openai_supports_reasoning=True,
    openai_reasoning_enabled_by_default=False,
    openai_supports_reasoning_effort_none=True,
)
MODEL_SETTINGS = {
    "temperature": 0,
    "max_tokens": 1800,
    "openai_reasoning_effort": "none",
    "tool_choice": "auto",
    "parallel_tool_calls": False,
}
BRIEF_PAYLOAD = {
    "brief_version": "1.0",
    "brief": {
        "product_type": "折叠阅读灯",
        "cultural_source": {"source_type": "user_confirmed", "name": "清代山水画意象", "era": "清代", "creator": None},
        "confirmed_facts": ["竹木灯体", "半透明纸质扩散罩", "适合书房与旅行阅读"],
        "form_and_material": "竹木灯体与半透明纸质扩散罩，便于折叠收纳与稳定展开。",
        "use_case": "书房阅读、旅行阅读",
        "target_audience": "年轻阅读者、博物馆文创消费者",
        "visual_direction": {"preset_id": "ink-paper", "cultural_context": "清代山水画意象的层次与留白", "medium": "纸墨与竹木", "palette": "米白、墨色、竹木暖色", "composition": "主体清晰、留白克制、便于识别", "additional_requirements": "突出可折叠结构与扩散罩的透光关系"},
        "presentation_mode": "single_hero",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_value(args: list[str], default: str = "unknown") -> str:
    try:
        return subprocess.check_output(args, cwd=Path(__file__).parents[1], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return default


def _atomic_json(path: Path, value: Any) -> None:
    if path.exists():
        raise Round17CContractError("SEALED_RUN_IMMUTABLE")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_text(path: Path, text: str) -> None:
    if path.exists():
        raise Round17CContractError("SEALED_RUN_IMMUTABLE")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_run(run_dir: Path, required_files: list[str] | None = None, *, seal_name: str = "sha256sums.json") -> dict[str, str]:
    """Fail closed: inventory is exact and later additions invalidate the seal."""
    actual = {path.name for path in run_dir.iterdir() if path.is_file() and path.name != seal_name}
    required = set(required_files or actual)
    if actual != required:
        raise Round17CContractError("ARTIFACT_INVENTORY_INVALID")
    checksums = {name: file_sha256(run_dir / name) for name in sorted(required)}
    _atomic_json(run_dir / seal_name, {"inventory_version": 1, "required_files": sorted(required), "sha256": checksums})
    verified = json.loads((run_dir / seal_name).read_text(encoding="utf-8"))
    if verified.get("required_files") != sorted(required) or set(verified.get("sha256", {})) != required:
        raise Round17CContractError("INTEGRITY_CHECK_FAILED")
    if any(file_sha256(run_dir / name) != digest for name, digest in verified["sha256"].items()):
        raise Round17CContractError("INTEGRITY_CHECK_FAILED")
    return verified


def freeze_evidence(brief: dict[str, Any], rag: CulturalRagService | None = None) -> dict[str, Any]:
    service = rag or CulturalRagService(str(Path(__file__).resolve().parents[1] / "rag" / "corpus" / "met_open_access"))
    request = brief if "brief" in brief else {"brief_version": BRIEF_PAYLOAD["brief_version"], "brief": brief}
    normalized = validate_cultural_product_request(request)
    decision = service.decide_query(service.query_for_brief(normalized), 3)
    return {
        "query": decision.query,
        "top_k": 3,
        "status": decision.status,
        "reason": decision.reason,
        "sources": [{"source_id": item.source_id, "title": item.title, "evidence": item.evidence, "license": item.license, "source_url": item.source_url} for item in decision.results],
    }


def _decision(snapshot: dict[str, Any]) -> RetrievalDecision:
    results = tuple(RetrievalResult(item["source_id"], 1.0, item["title"], item["source_url"], item["license"], item["evidence"]) for item in snapshot["sources"])
    return RetrievalDecision(snapshot["status"], snapshot["reason"], snapshot["query"], results, results)


def final_prompt(brief: dict[str, Any], evidence: dict[str, Any], skill_instructions: str = "") -> str:
    return "ROUND17C_BRIEF_JSON\n" + canonical_json(brief) + "\nFROZEN_EVIDENCE_JSON\n" + canonical_json(evidence) + ("\nTRUSTED_TEXT_SKILL_CHECKLIST\n" + skill_instructions if skill_instructions else "")


FINAL_SYSTEM_PROMPT = (
    "写出可直接交付的中文文创产品文案和文字版设计说明。只使用 Brief 与冻结证据；不得虚构年代、作者、馆藏或认证。"
    "产品文案中的自然标题必须能识别具体产品类别。最终只返回 JSON：product_copy、image_design_spec、used_source_ids。"
    "product_copy 和 image_design_spec 必须是连续自然段，绝不输出 JSON、字段标签、Markdown 表格、代码块、source ID、Skill 名、工具轨迹或内部分析。"
    "如提供 Skill，其字段和检查项只是内部写作检查表，不能改变这个最终合同。"
)


def _request_shape(request: httpx.Request) -> dict[str, Any]:
    """Return the allow-listed, secret-free portion of a Chat Completions request."""
    try:
        payload = json.loads(request.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    tool_names = [item.get("function", {}).get("name") for item in tools if isinstance(item, dict)]
    return {
        "endpoint": str(request.url.copy_with(query=None)),
        "model": payload.get("model"),
        "response_format": payload.get("response_format"),
        "reasoning_effort": payload.get("reasoning_effort"),
        "enable_thinking": payload.get("enable_thinking"),
        "tool_choice": payload.get("tool_choice"),
        "parallel_tool_calls": payload.get("parallel_tool_calls"),
        "tool_names": [name for name in tool_names if isinstance(name, str)],
        "request_shape_sha256": hashlib.sha256(request.content).hexdigest(),
    }


def _redact_error_message(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)(authorization|cookie|api[_-]?key)\\s*[:=]\\s*[^\\s,;]+", r"\\1=[redacted]", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", text)
    return text[:1000]


def sanitized_model_error(error: BaseException, *, stage: str, model_name: str, request_ordinal: int, request_shape_hash: str | None) -> dict[str, Any]:
    """Extract only safe, stable provider diagnostics from a model exception chain."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    status = next((getattr(item, "status_code", None) for item in chain if getattr(item, "status_code", None) is not None), None)
    code = next((getattr(item, "code", None) for item in chain if getattr(item, "code", None)), None)
    body = next((getattr(item, "body", None) for item in chain if getattr(item, "body", None) is not None), None)
    if isinstance(body, dict):
        code = body.get("code") or code
        message = body.get("message") or body.get("error")
    else:
        message = next((str(item) for item in chain if str(item)), None)
    return {
        "exception_class": type(error).__name__,
        "model_name": model_name,
        "http_status": status,
        "provider_error_code": code,
        "provider_message": _redact_error_message(message),
        "stage": stage,
        "request_ordinal": request_ordinal,
        "request_shape_sha256": request_shape_hash,
    }


class InstrumentedTransport(httpx.AsyncBaseTransport):
    """Counts actual wire attempts without mutating OpenAI-compatible requests."""

    def __init__(self, inner: httpx.AsyncBaseTransport, counter: dict[str, Any] | None = None):
        self.inner = inner
        self.counter = counter if counter is not None else {"requests": 0}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/chat/completions"):
            self.counter["requests"] = self.counter.get("requests", 0) + 1
            self.counter.setdefault("attempts", []).append({
                "stage": self.counter.get("stage", "unknown"),
                "ordinal": self.counter["requests"],
                "utc": _now(),
                **_request_shape(request),
            })
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def build_dashscope_client(*, api_key: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None, counter: dict[str, Any] | None = None, trust_env: bool = False) -> AsyncOpenAI:
    """Only client factory for the compatible domestic Chat Completions endpoint."""
    inner = transport or httpx.AsyncHTTPTransport()
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=InstrumentedTransport(inner, counter),
            timeout=httpx.Timeout(connect=10, read=90, write=30, pool=10),
            trust_env=trust_env,
        ),
    )


def build_model(*, model_name: str, openai_client: Any) -> OpenAIChatModel:
    """The sole model factory used by baseline, planner, final and recorder."""
    provider = AlibabaProvider(openai_client=openai_client)
    return OpenAIChatModel(model_name, provider=provider, profile=ROUND17C_PROFILE, settings=MODEL_SETTINGS)


def build_final_generator(model: Any) -> Agent:
    return Agent(
        model=model,
        output_type=PromptedOutput(Round17CFinalOutput, template="Return JSON only. Schema: {schema}"),
        retries=0,
        system_prompt=FINAL_SYSTEM_PROMPT,
    )


@dataclass
class PlannerDeps:
    frozen: dict[str, Any]
    loaded_skill_id: str | None = None
    loaded_skill_body: str | None = None
    loaded_skill_sha256: str | None = None
    catalog_sha256: str = ""
    frozen_evidence_sha256: str = ""
    trajectory: list[dict[str, Any]] = field(default_factory=list)


async def retrieve_cultural_sources(ctx: RunContext[PlannerDeps], query: str, top_k: int = 3) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip() or not isinstance(top_k, int) or not 1 <= top_k <= 3:
        raise Round17CContractError("INVALID_RETRIEVAL_REQUEST")
    snapshot = ctx.deps.frozen
    ctx.deps.trajectory.append({"tool": "retrieve_cultural_sources", "query_sha256": sha256_json({"query": query, "top_k": top_k}), "result_sha256": sha256_json(snapshot)})
    return snapshot


async def load_generation_skill(ctx: RunContext[PlannerDeps], skill_id: str) -> dict[str, str]:
    skill = SKILLS.get(skill_id)
    if not skill or skill.kind != "text":
        raise Round17CContractError("TEXT_SKILL_REQUIRED")
    if ctx.deps.loaded_skill_id is not None:
        raise Round17CContractError("EXACTLY_ONE_TEXT_SKILL_REQUIRED")
    instructions = load_skill(skill_id)
    ctx.deps.loaded_skill_id = skill_id
    ctx.deps.loaded_skill_body = instructions
    ctx.deps.loaded_skill_sha256 = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
    ctx.deps.trajectory.append({"tool": "load_generation_skill", "skill_id": skill_id, "kind": skill.kind, "instructions_sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest()})
    return {"skill_id": skill_id, "kind": "text", "version": skill.version, "instructions": instructions}


def build_guided_planner(model: Any) -> Agent:
    catalog = canonical_json(text_skill_catalog(SKILLS))
    def planner_settings(_ctx: RunContext[PlannerDeps]) -> dict[str, Any]:
        # Pydantic AI reserves `required` for function tools. With a sole ToolOutput,
        # `none` resolves to provider-level required for that output tool.
        return {"tool_choice": "none", "parallel_tool_calls": False}
    agent = Agent(
        model=model,
        deps_type=PlannerDeps,
        output_type=ToolOutput(load_generation_skill, name="load_generation_skill", strict=True, sequential=True),
        retries=0,
        system_prompt=(
            "You are a text-only planning stage. The only visible skills are this text catalog: " + catalog + ". "
            "The Brief and frozen evidence are already supplied by the server; do not retrieve evidence. "
            "Call load_generation_skill exactly once for one suitable text skill. "
            "Never load visual skills. Do not draft product copy or any JSON/text response. The tool call is your only output."
        ),
        model_settings=planner_settings,
    )
    return agent


def planner_prompt(brief: dict[str, Any], frozen: dict[str, Any]) -> str:
    summary = {
        "status": frozen.get("status"),
        "reason": frozen.get("reason"),
        "sources": [{"source_id": item.get("source_id"), "title": item.get("title"), "evidence": item.get("evidence")} for item in frozen.get("sources", [])],
    }
    return "ROUND17C_BRIEF_JSON\n" + canonical_json(brief) + "\nFROZEN_EVIDENCE_SUMMARY_JSON\n" + canonical_json(summary) + "\nFROZEN_EVIDENCE_SHA256\n" + sha256_json(frozen)


def run_baseline(model: Any, brief: dict[str, Any], frozen: dict[str, Any]) -> tuple[Round17CFinalOutput, dict[str, Any]]:
    started = time.perf_counter()
    result = build_final_generator(model).run_sync(final_prompt(brief, frozen), usage_limits=UsageLimits(request_limit=1))
    output = validate_final_output(result.output, frozen)
    return output, {"requests": result.usage.requests, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "tool_calls": 0}


def run_guided(model: Any, brief: dict[str, Any], frozen: dict[str, Any]) -> tuple[Round17CFinalOutput, dict[str, Any]]:
    """Planner sees evidence only through its tool; final generator sees one shared snapshot."""
    started = time.perf_counter()
    deps = PlannerDeps(frozen=frozen, catalog_sha256=sha256_json(text_skill_catalog(SKILLS)), frozen_evidence_sha256=sha256_json(frozen))
    planner = build_guided_planner(model)
    planner_result = planner.run_sync(planner_prompt(brief, frozen), deps=deps, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
    if not deps.loaded_skill_id or not deps.loaded_skill_body:
        raise Round17CContractError("EXACTLY_ONE_TEXT_SKILL_REQUIRED")
    tools = [item["tool"] for item in deps.trajectory]
    if tools != ["load_generation_skill"]:
        raise Round17CContractError("GUIDED_TRAJECTORY_INVALID")
    final = build_final_generator(model).run_sync(final_prompt(brief, frozen, deps.loaded_skill_body), usage_limits=UsageLimits(request_limit=1))
    output = validate_final_output(final.output, frozen)
    return output, {
        "requests": planner_result.usage.requests + final.usage.requests,
        "planner_requests": planner_result.usage.requests,
        "final_requests": final.usage.requests,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "loaded_text_skill": deps.loaded_skill_id,
        "loaded_skill_sha256": deps.loaded_skill_sha256,
        "catalog_sha256": deps.catalog_sha256,
        "frozen_evidence_sha256": deps.frozen_evidence_sha256,
        "tool_trajectory": deps.trajectory,
    }


def run_guided_plan(model: Any, brief: dict[str, Any], frozen: dict[str, Any]) -> tuple[PlannerDeps, dict[str, str], dict[str, Any]]:
    """Planner-only half of Guided; preserves cached Skill bytes for the final half."""
    started = time.perf_counter()
    deps = PlannerDeps(frozen=frozen, catalog_sha256=sha256_json(text_skill_catalog(SKILLS)), frozen_evidence_sha256=sha256_json(frozen))
    result = build_guided_planner(model).run_sync(planner_prompt(brief, frozen), deps=deps, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
    if not deps.loaded_skill_id or not deps.loaded_skill_body or [x["tool"] for x in deps.trajectory] != ["load_generation_skill"]:
        raise Round17CContractError("GUIDED_TRAJECTORY_INVALID")
    return deps, result.output, {"requests": result.usage.requests, "latency_ms": round((time.perf_counter()-started)*1000,3), "tool_trajectory": deps.trajectory, "selected_skill_id": deps.loaded_skill_id, "skill_body_sha256": deps.loaded_skill_sha256}


def run_guided_final(model: Any, brief: dict[str, Any], frozen: dict[str, Any], deps: PlannerDeps) -> tuple[Round17CFinalOutput, dict[str, Any]]:
    if not deps.loaded_skill_body:
        raise Round17CContractError("EXACTLY_ONE_TEXT_SKILL_REQUIRED")
    started=time.perf_counter(); result=build_final_generator(model).run_sync(final_prompt(brief, frozen, deps.loaded_skill_body), usage_limits=UsageLimits(request_limit=1)); output=validate_final_output(result.output, frozen)
    return output, {"requests": result.usage.requests, "latency_ms": round((time.perf_counter()-started)*1000,3), "selected_skill_id":deps.loaded_skill_id, "skill_body_sha256":deps.loaded_skill_sha256}


def create_blocked_run(*, root: Path = ROOT, brief_payload: dict[str, Any] = BRIEF_PAYLOAD) -> Path:
    """Offline default: records no provider construction and no model/database/image calls."""
    run_id = f"round-17c-clean-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{_git_value(['git', 'rev-parse', '--short', 'HEAD'])}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started = _now()
    manifest = {
        "run_id": run_id, "started_at": started, "finished_at": _now(),
        "git_sha": _git_value(["git", "rev-parse", "HEAD"]),
        "dirty": bool(_git_value(["git", "status", "--porcelain"], "")),
        "runner_version": RUNNER_VERSION,
        "schema_sha256": sha256_json(Round17CFinalOutput.model_json_schema()),
        "technical_status": "blocked", "evaluation_validity": "not_run", "integrity_status": "pending",
        "failure_stage": "authorization", "stable_error": "REAL_MODEL_NOT_AUTHORIZED",
        "model": {"provider": "dashscope-chat-completions", "name": "not_constructed", "base_url": "not_constructed"},
        "retries": 0, "actual_calls": {"qwen": 0, "deepseek": 0, "image": 0, "database_writes": 0},
    }
    _atomic_json(run_dir / "manifest.json", manifest)
    _atomic_json(run_dir / "brief.json", brief_payload)
    _atomic_json(run_dir / "frozen-evidence.json", {"status": "not_run"})
    _atomic_json(run_dir / "normalized-report.json", {"technical_status": "blocked", "evaluation_validity": "not_run", "integrity_status": "pending", "reason": "REAL_MODEL_NOT_AUTHORIZED", "arms": {}})
    seal_run(run_dir, ["manifest.json", "brief.json", "frozen-evidence.json", "normalized-report.json"])
    return run_dir
