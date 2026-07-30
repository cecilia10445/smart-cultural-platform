from backend.services.agent_image_generation import AgentImageGenerationService


def package(mode="single_hero"):
    return {"positive_prompt": "confirmed product prompt", "negative_prompt": "no text", "presentation_mode": mode}


class FakeAigc:
    def __init__(self): self.calls = []
    def generate_image_from_prompt(self, positive, negative):
        self.calls.append(("generate", positive, negative))
        return "https://provider.example/reference.png"
    def edit_image_with_reference(self, reference, prompt, negative, size):
        self.calls.append(("edit", reference, prompt, negative, size))
        return "https://provider.example/final.png"


def test_agent_image_generation_uses_confirmed_package_for_single_hero():
    aigc = FakeAigc()
    service = AgentImageGenerationService(aigc, persist=lambda url, _dir: f"/static/images/{url.rsplit('/', 1)[-1]}", images_dir="/tmp")
    result = service.generate(package())
    assert result["image_url"] == "/static/images/reference.png"
    assert aigc.calls == [("generate", "confirmed product prompt", "no text")]


def test_agent_image_generation_preserves_multi_view_edit_semantics():
    aigc = FakeAigc()
    service = AgentImageGenerationService(aigc, persist=lambda url, _dir: "/static/images/final.png", images_dir="/tmp")
    result = service.generate(package("flat_front_back"))
    assert result["image_url"] == "/static/images/final.png"
    assert [call[0] for call in aigc.calls] == ["generate", "edit"]
    assert aigc.calls[-1][-1] == "1200*800"
    assert "正面与背面" in aigc.calls[-1][2]
