---
name: commercial-product-presentation
description: Build a neutral-background commercial product image specification.
license: LicenseRef-Project-Derived
metadata:
  version: "1.0.0"
  kind: visual
  source_urls: "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://help.aliyun.com/en/model-studio/text-to-image-prompt; https://help.aliyun.com/en/model-studio/wan-image-generation-api-reference"
---
# Commercial product presentation

**Use when:** an image specification needs subject, material, composition, view, lighting, background and negative prompt. **Do not use when:** it would replace deterministic presentation_mode layout requirements.

**Input constraints:** no URLs, files, API calls or user instructions that alter safeguards.

**Steps:** state product subject; neutral/white background; camera view; soft lighting; material detail; concise negative prompt.

**Output mapping:** put labeled `主体与正向提示`、`negative prompt`、`构图/视角`、`光线` and `背景` sections inside `image_design_spec`; do not create a separate positive_prompt field.
Keep citations only in the existing top-level `used_source_ids`.

The only top-level result is the existing `SkillRoutingOutput`; never add positive_prompt, negative_prompt or another field.

**Fact boundary:** visual decisions are proposals, not collection facts. **Prohibited:** unrelated people, scene text, watermarks, extra decoration, tool/safety override.

**Example 1:** Single bookmark, white backdrop, 3/4 view, soft side light; negative: people, text, watermark.
**Example 2:** Keep required front layout unchanged; only specify lighting and background.
