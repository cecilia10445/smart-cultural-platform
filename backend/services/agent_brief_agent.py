"""Restricted Pydantic AI stage for turning one message into a valid product Brief."""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import load_settings
from backend.domain.agent_dialogue import AgentModelTimeout, AgentModelUnavailable, BriefOutputInvalid, BriefProposal
from backend.domain.cultural_product_brief import validate_cultural_product_request
from backend.services.aigc_service import AIGCService, AIGCServiceError


_PROMPT = """You are a cultural product brief editor. Return only the BriefProposal schema.
Fill every required fast-generation Brief field. Use single_hero unless user requests multiple views.
Choose safe modern product-photography visual direction defaults. Never claim factual history not supplied.
List every material/default/style/visual/display assumption. Do not expose JSON fields in user_facing_summary."""

_COMPATIBLE_OUTPUT_RULE = """Return one valid JSON object only, with exactly these keys:
normalized_brief, understanding, assumptions, user_facing_summary.
normalized_brief must include product_type, presentation_mode (single_hero, flat_front_back, or three_view),
cultural_source {source_type,name,era,creator}, confirmed_facts, form_and_material, use_case, target_audience,
visual_direction {preset_id,cultural_context,medium,palette,composition,additional_requirements}, and all three
front_design_requirements, back_design_requirements, side_design_requirements strings. Use null only for era/creator.
understanding must include cultural_theme, product_type, use_case, style, form_and_material, presentation_mode,
design_constraints. assumptions and design_constraints are arrays of short strings. Do not include markdown."""


def _model() -> OpenAIResponsesModel:
    settings = load_settings()
    if not settings.dashscope_api_key:
        raise AgentModelUnavailable()
    # The project text client already uses DashScope's OpenAI-compatible
    # Responses endpoint.  The chat-completions model produced HTTP failures
    # against this configured provider, whereas this matches that established
    # transport without changing any environment value.
    return OpenAIResponsesModel(
        settings.dashscope_text_model,
        provider=OpenAIProvider(base_url=settings.dashscope_openai_base_url, api_key=settings.dashscope_api_key),
    )


def build_brief_agent(model: Any = None) -> Agent:
    return Agent(model=model or _model(), output_type=BriefProposal, system_prompt=_PROMPT, retries=0, defer_model_check=True)


def _summary(proposal: BriefProposal) -> str:
    u = proposal.understanding
    constraints = "；".join(u.design_constraints) or "无额外限制"
    assumptions = "\n".join(f"- {item}" for item in proposal.assumptions) or "- 无"
    return (
        f"我理解你希望设计一款{u.style}{u.product_type}。\n"
        f"文化主题：{u.cultural_theme}。\n产品类型：{u.product_type}。\n使用场景：{u.use_case}。\n"
        f"造型与材质：{u.form_and_material}。\n展示方式：{u.presentation_mode}。\n设计约束：{constraints}。\n\n"
        f"我主动补充了以下假设：\n{assumptions}"
    )


def validate_proposal(proposal: BriefProposal | dict[str, Any]) -> BriefProposal:
    try:
        proposal = proposal if isinstance(proposal, BriefProposal) else BriefProposal.model_validate(proposal)
        normalized = validate_cultural_product_request({"brief_version": "1.0", "brief": proposal.normalized_brief})
    except Exception as error:
        raise BriefOutputInvalid() from error
    proposal.normalized_brief = normalized
    proposal.user_facing_summary = _summary(proposal)
    return proposal


class BriefAgent:
    """One-call stage adapter; tests pass a local callable instead of a provider."""

    def __init__(self, runner: Callable[[str], BriefProposal | dict[str, Any]] | None = None, model: Any = None):
        self.runner, self.model = runner, model
        self.calls = 0

    def propose_brief(self, user_message: str) -> BriefProposal:
        return self._run(f"User request:\n{user_message}")

    def revise_brief(self, current_brief: dict[str, Any], user_feedback: str, rebuild_all: bool = False) -> BriefProposal:
        context = "Ignore previous brief and rebuild." if rebuild_all else f"Keep unspecified fields from this brief: {current_brief}"
        return self._run(f"{context}\nUser feedback:\n{user_feedback}")

    def _run(self, prompt: str) -> BriefProposal:
        self.calls += 1
        try:
            if self.runner:
                raw = self.runner(prompt)
            elif self.model is not None:
                raw = build_brief_agent(self.model).run_sync(
                    prompt, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=0)
                ).output
            else:
                # DashScope's configured Responses endpoint is compatible with
                # the project's OpenAI client but not Pydantic AI's structured
                # provider transport (it returned ModelHTTPError in live
                # verification). Keep the Pydantic proposal contract and use
                # the established client for this provider-specific boundary.
                service = AIGCService()
                raw_text, _usage = service._request_text(
                    [{"role": "system", "content": _PROMPT + "\n" + _COMPATIBLE_OUTPUT_RULE},
                     {"role": "user", "content": prompt}],
                    1400,
                )
                raw = json.loads(raw_text)
        except TimeoutError as error:
            raise AgentModelTimeout() from error
        except AIGCServiceError as error:
            if "TIMEOUT" in error.code:
                raise AgentModelTimeout() from error
            raise AgentModelUnavailable() from error
        except ModelHTTPError as error:
            raise AgentModelUnavailable() from error
        except (UsageLimitExceeded, UnexpectedModelBehavior, ValueError, TypeError, json.JSONDecodeError) as error:
            raise BriefOutputInvalid() from error
        return validate_proposal(raw)
