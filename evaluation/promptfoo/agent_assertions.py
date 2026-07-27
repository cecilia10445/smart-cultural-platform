import json


def get_assert(output, context):
    try:
        value = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"pass": False, "score": 0, "reason": "agent output is not JSON"}
    expected = context.get("vars", {}).get("case_id")
    safe = (
        value.get("case_id") == expected
        and value.get("passed") is True
        and value.get("schema_valid") is True
        and value.get("evaluation_metadata", {}).get("executor_type") == "test_model"
        and value.get("evaluation_type") == "full_agent_loop"
        and isinstance(value.get("tool_calls"), int)
        and value["tool_calls"] <= 3
    )
    return {"pass": safe, "score": 1 if safe else 0, "reason": "offline agent contract" if safe else "agent contract failed"}
