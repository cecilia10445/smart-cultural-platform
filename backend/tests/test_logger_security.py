import json

from backend.utils import logger


def test_logger_redacts_nested_sensitive_data(monkeypatch, tmp_path):
    log_file = tmp_path / "app.log"
    monkeypatch.setattr(logger, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(logger, "LOG_FILE", str(log_file))
    logger.log_event("security_test", {"password": "secret", "token": "jwt-value", "nested": {"Authorization": "Bearer secret"}, "safe": "kept"})
    text = log_file.read_text(encoding="utf-8")
    record = json.loads(text)
    assert "secret" not in text
    assert "jwt-value" not in text
    assert record["data"]["safe"] == "kept"
    assert record["data"]["nested"]["Authorization"] == "[REDACTED]"
