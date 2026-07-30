"""Restricted Pydantic AI stage for turning one message into a valid product Brief."""

from __future__ import annotations

from typing import Any, Callable

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import load_settings
from backend.domain.agent_dialogue import AgentModelTimeout, AgentModelUnavailable, BriefOutputInvalid, BriefProposal
from backend.domain.cultural_product_brief import validate_cultural_product_request


_PROMPT = """You are a cultural product brief editor. Return only the BriefProposal schema.
Fill every required fast-generation Brief field. Use single_hero unless user requests multiple views.
Choose safe modern product-photography visual direction defaults. Never claim factual history not supplied.
List every material/default/style/visual/display assumption. Do not expose JSON fields in user_facing_summary."""


def _model() -> OpenAIChatModel:
    settings = load_settings()
    if not settings.dashscope_api_key:
        raise AgentModelUnavailable()
    return OpenAIChatModel(
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
            raw = self.runner(prompt) if self.runner else build_brief_agent(self.model).run_sync(
                prompt, usage_limits=UsageLimits(request_limit=2, tool_calls_limit=0)
            ).output
        except TimeoutError as error:
            raise AgentModelTimeout() from error
        except (UsageLimitExceeded, UnexpectedModelBehavior, ValueError, TypeError) as error:
            raise BriefOutputInvalid() from error
        return validate_proposal(raw)
