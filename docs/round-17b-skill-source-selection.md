# Round 17B Skill source selection

Checked 2026-07-28; commits are immutable audit pins.

| Source | Commit / licence / status | Decision |
| --- | --- | --- |
| https://github.com/agentskills/agentskills | `38a2ff82958afee88dadf4831509e6f7e9d8ef4e`; code Apache-2.0, docs CC-BY-4.0; active open specification | Adopt folder `SKILL.md`, YAML frontmatter and discovery→activation progressive disclosure. `skills-ref` is documented as demonstration-only, so it is not a runtime dependency. |
| https://github.com/coreyhaines31/marketingskills | `c21a984a56da10fb6085e6334f6f60929220a4da`; MIT; active multi-skill repository | Adapt product positioning, audience/use-case, benefit hierarchy, copy editing and lightweight social clarity only. Omit SaaS pages, CRO, funnels, urgency, sales claims and installation tooling. |
| Alibaba Cloud Wan documentation | Wan prompt guide and Wan2.6 API, current official docs | Adapt positive/negative prompt separation and subject, material, composition, view, light and background vocabulary. No API integration, key handling or image execution is introduced. |
| https://github.com/michaelboeding/skills | `84abf02d42612ab0b94a54de1a1a454ae25dd131`; MIT; personal collection with scripts/dependencies | Reject whole-repository adoption: it assumes agents, scripts, dependencies and image generation. Borrow only the review dimensions of form, user, material and manufacturability. |

Project-original adaptations are the cultural-fact/citation boundary, no-instruction-execution policy, deterministic presentation-mode preservation, fixed server allow-list, and the six concise Chinese cultural-product workflows. No third-party repository or Skill body is copied.
