import pytest

from backend.services.agent_brief_agent import BriefAgent
from backend.tests.test_agent_dialogue_service import proposal
from backend.domain.agent_dialogue import BriefOutputInvalid


def test_brief_agent_validates_a_complete_fast_generation_brief():
    result = BriefAgent(runner=proposal).propose_brief("以三兔共耳设计现代桌面灯，不要仿古")
    assert result.normalized_brief["presentation_mode"] == "single_hero"
    assert result.understanding.cultural_theme == "三兔共耳纹样"
    assert "默认现代产品摄影风格" in result.assumptions
    assert "文化主题：三兔共耳纹样" in result.user_facing_summary


def test_invalid_provider_shape_becomes_stable_brief_error():
    with pytest.raises(BriefOutputInvalid):
        BriefAgent(runner=lambda _prompt: {"normalized_brief": {}}).propose_brief("bad")
