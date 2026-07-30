#!/usr/bin/env python3
"""Deliberately opt-in, redacted DashScope Runtime smoke preflight.

This runner never enables a provider itself.  It is safe to run in CI because
it exits before any network or database operation unless the caller explicitly
sets AGENT_RUNTIME_ALLOW_REAL_MODEL=true.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from backend.agents.runtime.providers import RuntimeProviderError, build_runtime_model


def main() -> int:
    if os.getenv("AGENT_RUNTIME_ALLOW_REAL_MODEL", "").lower() not in {"1", "true", "yes", "on"}:
        print(json.dumps({"ok": False, "code": "RUNTIME_REAL_MODEL_DISABLED"}))
        return 2
    try:
        model = build_runtime_model()
    except RuntimeProviderError as error:
        print(json.dumps({"ok": False, "code": error.code}))
        return 3
    # The HTTP/database orchestration is intentionally delegated to the route
    # composition.  Printing model/provider metadata only keeps this helper
    # usable as a controlled preflight without recording prompt/tool content.
    print(json.dumps({"ok": True, "provider": "dashscope", "model": getattr(model, "model_name", "configured"),
                      "network_call": False, "code": "RUNTIME_SMOKE_READY"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
