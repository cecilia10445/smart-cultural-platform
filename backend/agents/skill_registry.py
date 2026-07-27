"""Fixed, read-only Agent Skills registry with safe progressive loading."""

from dataclasses import dataclass
from pathlib import Path


class SkillAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class Skill:
    skill_id: str
    kind: str
    version: str
    description: str
    provenance: str
    license: str
    source_urls: str


SKILL_ROOT = Path(__file__).with_name("skills")
SKILLS = {
    "museum-product-explainer": Skill("museum-product-explainer", "text", "1.0.0", "Explain a cultural product with verified provenance boundaries.", "project adaptation; Agent Skills", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e"),
    "retail-product-copy": Skill("retail-product-copy", "text", "1.0.0", "Write restrained audience and use-case led cultural retail copy.", "project adaptation; Marketing Skills", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://github.com/coreyhaines31/marketingskills/tree/c21a984a56da10fb6085e6334f6f60929220a4da"),
    "social-cultural-story": Skill("social-cultural-story", "text", "1.0.0", "Create a clear, rhythmic, lightweight cultural knowledge story.", "project adaptation; Marketing Skills", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://github.com/coreyhaines31/marketingskills/tree/c21a984a56da10fb6085e6334f6f60929220a4da"),
    "heritage-motif-translation": Skill("heritage-motif-translation", "visual", "1.0.0", "Translate verified heritage motifs into contemporary product relationships.", "project original adaptation", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e"),
    "product-material-realism": Skill("product-material-realism", "visual", "1.0.0", "Specify visible, proportionate and manufacturable product material detail.", "project adaptation; design review", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://github.com/michaelboeding/skills/tree/84abf02d42612ab0b94a54de1a1a454ae25dd131"),
    "commercial-product-presentation": Skill("commercial-product-presentation", "visual", "1.0.0", "Build a neutral-background commercial product image specification.", "project adaptation; Alibaba Cloud Wan", "LicenseRef-Project-Derived", "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://help.aliyun.com/en/model-studio/text-to-image-prompt; https://help.aliyun.com/en/model-studio/wan-image-generation-api-reference"),
}


def catalog() -> str:
    for skill_id in SKILLS:
        _read_asset(skill_id, body_required=False)
    return "; ".join(f"{s.skill_id} ({s.kind} {s.version}): {s.description}" for s in SKILLS.values())


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    try:
        if not text.startswith("---\n") or text.count("\n---\n") != 1:
            raise SkillAssetError("SKILL_ASSET_INVALID")
        end = text.find("\n---\n", 4)
        lines, body = text[4:end].splitlines(), text[end + 5:]
        if not body.strip():
            raise SkillAssetError("SKILL_ASSET_INVALID")
        data, meta, in_meta = {}, {}, False
        for line in lines:
            if not line.strip():
                continue
            if line == "metadata:":
                in_meta = True
                continue
            if in_meta and line.startswith("  "):
                if ":" not in line or line.startswith("    "):
                    raise SkillAssetError("SKILL_ASSET_INVALID")
                key, value = line.strip().split(":", 1)
                value = value.strip().strip('"')
                if not key or not value or key in meta:
                    raise SkillAssetError("SKILL_ASSET_INVALID")
                meta[key] = value
                continue
            if in_meta or ":" not in line:
                raise SkillAssetError("SKILL_ASSET_INVALID")
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip().strip('"')
            if not key or not value or key in data:
                raise SkillAssetError("SKILL_ASSET_INVALID")
            data[key] = value
        if set(data) != {"name", "description", "license"} or set(meta) != {"version", "kind", "source_urls"}:
            raise SkillAssetError("SKILL_ASSET_INVALID")
        if not all(isinstance(v, str) for v in (*data.values(), *meta.values())) or not meta["source_urls"].startswith("http"):
            raise SkillAssetError("SKILL_ASSET_INVALID")
        data.update({f"metadata.{k}": v for k, v in meta.items()})
        return data, body
    except (AttributeError, IndexError, TypeError, ValueError, UnicodeError) as error:
        raise SkillAssetError("SKILL_ASSET_INVALID") from error


def _read_asset(skill_id: str, *, body_required: bool = True) -> tuple[dict[str, str], str]:
    skill = SKILLS.get(skill_id)
    if not skill:
        raise SkillAssetError("UNKNOWN_SKILL")
    try:
        root, folder = SKILL_ROOT.resolve(), SKILL_ROOT / skill_id
        path = folder / "SKILL.md"
        resolved = path.resolve(strict=True)
        if folder.is_symlink() or path.is_symlink() or resolved.parent != folder.resolve() or root not in resolved.parents:
            raise SkillAssetError("SKILL_ASSET_INVALID")
        text = path.read_text(encoding="utf-8")
        if len(text) > 16000 or "\x00" in text:
            raise SkillAssetError("SKILL_ASSET_INVALID")
        meta, body = _frontmatter(text)
    except (OSError, UnicodeError) as error:
        raise SkillAssetError("SKILL_ASSET_INVALID") from error
    expected = (skill_id, skill.kind, skill.version, skill.description, skill.license, skill.source_urls)
    actual = (meta["name"], meta["metadata.kind"], meta["metadata.version"], meta["description"], meta["license"], meta["metadata.source_urls"])
    if actual != expected:
        raise SkillAssetError("SKILL_ASSET_INVALID")
    return meta, body if body_required else ""


def load_skill(skill_id: str) -> str:
    _, body = _read_asset(skill_id)
    return body.strip()
