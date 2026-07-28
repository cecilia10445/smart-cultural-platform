from __future__ import annotations

import json

from evaluation import round17c_real_run as real


def test_real_gate_blocks_before_provider_or_secret_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("ROUND17C_REAL_RUN_AUTHORIZED", raising=False)
    run = real.orchestrate(real_flag=False, root=tmp_path)
    assert json.loads((run / "manifest.json").read_text())["stable_error"] == "REAL_MODEL_NOT_AUTHORIZED"


def test_config_requires_explicit_deepseek_endpoint_without_guessing(monkeypatch):
    monkeypatch.delenv("ROUND17C_DEEPSEEK_BASE_URL", raising=False)
    try:
        real.resolve_config()
    except Exception as exc:
        assert getattr(exc, "code", None) == "ROUND17C_DEEPSEEK_CONFIGURATION_REQUIRED"
    else:
        raise AssertionError("DeepSeek endpoint must not be guessed")
