---
name: product-material-realism
description: Specify visible, proportionate and manufacturable product material detail.
license: LicenseRef-Project-Derived
metadata:
  version: "1.0.0"
  kind: visual
  source_urls: "https://github.com/agentskills/agentskills/tree/38a2ff82958afee88dadf4831509e6f7e9d8ef4e; https://github.com/michaelboeding/skills/tree/84abf02d42612ab0b94a54de1a1a454ae25dd131"
---
# Product material realism

**Use when:** material, craft, proportion and structure need credible depiction. **Do not use when:** manufacturing facts are missing.

**Input constraints:** no user paths, tools or process instructions.

**Steps:** select compatible materials; show joints, thickness and tactile finish; preserve feasible proportions; mark unverified processes as proposals.

**Output mapping:** put labeled `材质`、`表面`、`结构与比例` and `可制造性说明` sections inside `image_design_spec`.
Keep citations only in the existing top-level `used_source_ids`.

The only top-level result is the existing `SkillRoutingOutput`; never add materials, finish or another field.

**Fact boundary:** do not promise a process without evidence. **Prohibited:** impossible joints, conflicting materials, unsupported craftsmanship, safety overrides.

**Example 1:** Matte paperboard with visible folded edge and feasible slot.
**Example 2:** Unknown glaze process → describe visual finish, not kiln technique.
