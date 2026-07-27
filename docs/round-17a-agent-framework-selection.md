# Round 17A Agent Framework Gate

## Decision

Pydantic AI is the sole agent framework for Round 17A. The implementation pins
`pydantic-ai-slim[openai]==2.14.1` and adds no LangGraph, OpenAI Agents SDK,
CrewAI, AutoGen, or second agent runtime.

The pin was installed successfully in an isolated Python 3.10 environment with
the repository's Flask 2.3.3, OpenAI 2.46.0, and Pydantic 2.13.4. The package
imports `Agent`, `TestModel`, and `FunctionModel` without changing repository
files or contacting a model endpoint. The same dependency was then installed
in the existing project virtualenv only for offline tests.

## Official-source review

| Option | Maintenance/release signal | License and Python | Relevant capabilities | Decision |
| --- | --- | --- | --- | --- |
| Pydantic AI | Active official docs and GitHub; pinned 2.14.1 is available on PyPI (2.15.0 was current during review) | MIT; Python 3.10 compatible | Pydantic structured output, function tools, OpenAI-compatible providers, `TestModel` and `FunctionModel` | **Selected** |
| LangGraph | Active LangChain project and official Python docs | MIT; Python >=3.10 | Graph orchestration and tool nodes; would add a second runtime and broader state surface | Rejected for this MVP |
| OpenAI Agents SDK | Active official OpenAI docs/GitHub | MIT; Python 3.9+ | Agents, tools, guardrails, structured outputs; introduces another agent runtime | Rejected for this MVP |

Sources reviewed:

- [Pydantic AI installation](https://pydantic.dev/docs/ai/overview/install/), [structured output](https://pydantic.dev/docs/ai/core-concepts/output/), and [testing with TestModel/FunctionModel](https://pydantic.dev/docs/ai/guides/testing/)
- [Pydantic AI GitHub](https://github.com/pydantic/pydantic-ai) and [pydantic-ai-slim on PyPI](https://pypi.org/project/pydantic-ai-slim/)
- [LangGraph installation](https://docs.langchain.com/oss/python/langgraph/install) and [official GitHub](https://github.com/langchain-ai/langgraph)
- [OpenAI Agents SDK documentation](https://openai.github.io/openai-agents-python/) and [official GitHub](https://github.com/openai/openai-agents-python)

Pydantic AI's OpenAI provider supports an OpenAI-compatible `base_url`, so a
future explicitly authorized DashScope-compatible channel can be configured
without changing the routing contract. Round 17A does not configure or call
that channel; `run_skill_routing` requires an injected model and returns the
stable `REAL_AGENT_DISABLED` error otherwise.

## Controlled MVP boundary

`backend/agents/skill_routing.py` contains the fixed registry (three text and
three visual skills), a Pydantic `SkillRoutingOutput`, and one agent with only
`retrieve_cultural_sources(query, top_k)` and `load_generation_skill(skill_id)`.
IDs and versions are allow-listed; file paths, arbitrary skill text, downloads,
URLs, shell, SQL, network tools, credentials, and parallel calls are absent.
The run uses no automatic retries, a four-request limit, a three-tool-call
limit, and at most one skill per kind. RAG evidence is returned as data and is
never merged into trusted skill instructions. Citations must be a subset of
retrieved source IDs.

Round 17A is an offline Agent/Registry/test slice only. It does not replace or
call the production v2 generation endpoint, add a migration, persist output, or
create a generic runner or report generator.

## v2 review correction

The service boundary now requires the complete loop `retrieve -> load(text) ->
load(visual) -> structured output`. A valid allow-listed ID without a matching
load record returns `SKILL_NOT_LOADED`; the registry must contain exactly one
text and one visual Skill, and retrieval must have occurred in this run.
Tests distinguish framework/policy contract checks from complete offline Agent
loop self-tests driven by a deterministic Pydantic `TestModel`. Promptfoo Agent
cases also use `run_skill_routing` and are labeled `executor_type=test_model`,
`data_origin=test`, `measurement_scope=harness_self_test`. No real-model Agent
evaluation has occurred.
