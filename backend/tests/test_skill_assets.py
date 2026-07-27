from pathlib import Path

import pytest

from backend.agents.skill_registry import SKILLS, SKILL_ROOT, SkillAssetError, _frontmatter, _read_asset, catalog, load_skill


def test_all_six_assets_are_versioned_and_loadable():
    assert len(SKILLS) == 6
    for skill_id, skill in SKILLS.items():
        text = load_skill(skill_id)
        assert "**Use when:**" in text and "**Example 1:**" in text
        target = "product_copy" if skill.kind == "text" else "image_design_spec"
        assert target in text and "SkillRoutingOutput" in text
        assert "used_source_ids" in text
        assert skill_id in catalog() and skill.version == "1.0.0"
        metadata, _ = _read_asset(skill_id)
        assert metadata["license"] == skill.license
        assert metadata["metadata.source_urls"] == skill.source_urls


@pytest.mark.parametrize("skill_id", ["../x", "/tmp/x", "unknown"])
def test_registry_rejects_user_paths(skill_id):
    with pytest.raises(SkillAssetError, match="UNKNOWN_SKILL"):
        load_skill(skill_id)


def test_symlink_escape_is_rejected(tmp_path, monkeypatch):
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "SKILL.md").write_text("x")
    root = tmp_path / "skills"; root.mkdir(); (root / "museum-product-explainer").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr("backend.agents.skill_registry.SKILL_ROOT", root)
    with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
        load_skill("museum-product-explainer")


def test_frontmatter_metadata_is_string_only_and_lists_are_rejected():
    valid = "---\nname: x\ndescription: d\nlicense: l\nmetadata:\n  version: 1\n  kind: text\n  source_urls: https://example.test\n---\nbody\n"
    meta, _ = _frontmatter(valid)
    assert all(isinstance(value, str) for value in meta.values())
    listed = valid.replace("source_urls: https://example.test", "source_urls:\n    - https://example.test")
    with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
        _frontmatter(listed)


@pytest.mark.parametrize("text", [
    "bad", "---\nname x\n---\nbody\n", "---\nname: x\n---\n---\nbody\n",
    "---\nname: x\ndescription: d\nlicense: l\nmetadata:\n  version: 1\n  kind: text\n  source_urls: https://example.test\n---\n",
])
def test_corrupt_frontmatter_or_empty_body_is_stable(text):
    with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
        _frontmatter(text)


def test_asset_corruption_errors_are_stable(tmp_path, monkeypatch):
    source = (SKILL_ROOT / "museum-product-explainer" / "SKILL.md").read_text()
    root = tmp_path / "skills"; folder = root / "museum-product-explainer"; folder.mkdir(parents=True)
    monkeypatch.setattr("backend.agents.skill_registry.SKILL_ROOT", root)
    for bad in [source.replace("name: museum-product-explainer", "name: other"), source.replace('version: "1.0.0"', 'version: "2.0.0"'), source.replace("kind: text", "kind: visual"), source.replace("description: Explain", "description: Other"), source.replace("license: LicenseRef-Project-Derived", "license: MIT"), source.replace("source_urls: \"https://github.com/agentskills", "source_urls: \"https://example.invalid"), source.replace("source_urls:", "other_sources:"), source.replace("\n# Museum", "\n\x00# Museum"), source.replace("\n# Museum", "\n" + ("x" * 16001))]:
        (folder / "SKILL.md").write_text(bad)
        with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
            load_skill("museum-product-explainer")
    (folder / "SKILL.md").write_bytes(b"\xff\xfe")
    with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
        load_skill("museum-product-explainer")
    (folder / "SKILL.md").unlink()
    with pytest.raises(SkillAssetError, match="SKILL_ASSET_INVALID"):
        load_skill("museum-product-explainer")
