from backend.config import load_settings


def test_dashscope_connection_and_read_timeouts_are_independent(monkeypatch):
    monkeypatch.setattr("backend.config.load_dotenv", lambda **_kwargs: None)
    for name in (
        "DASHSCOPE_TEXT_CONNECT_TIMEOUT_SECONDS",
        "DASHSCOPE_TEXT_READ_TIMEOUT_SECONDS",
        "DASHSCOPE_IMAGE_CONNECT_TIMEOUT_SECONDS",
        "DASHSCOPE_IMAGE_READ_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    defaults = load_settings()
    assert (defaults.dashscope_text_connect_timeout_seconds, defaults.dashscope_text_read_timeout_seconds) == (5, 120)
    assert (defaults.dashscope_image_connect_timeout_seconds, defaults.dashscope_image_read_timeout_seconds) == (5, 30)
    assert defaults.dashscope_text_reasoning_effort == "none"

    monkeypatch.setenv("DASHSCOPE_TEXT_CONNECT_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("DASHSCOPE_TEXT_READ_TIMEOUT_SECONDS", "91")
    configured = load_settings()
    assert (configured.dashscope_text_connect_timeout_seconds, configured.dashscope_text_read_timeout_seconds) == (3, 91)


def test_real_business_smoke_settings_are_explicit_opt_in(monkeypatch):
    monkeypatch.setattr("backend.config.load_dotenv", lambda **_kwargs: None)
    for name in ("RUN_REAL_BUSINESS_SMOKE", "SMOKE_TEST_USERNAME", "SMOKE_TEST_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    disabled = load_settings()
    assert disabled.run_real_business_smoke is False
    assert disabled.smoke_test_username is None
    assert disabled.smoke_test_password is None

    monkeypatch.setenv("RUN_REAL_BUSINESS_SMOKE", "1")
    monkeypatch.setenv("SMOKE_TEST_USERNAME", "user1")
    monkeypatch.setenv("SMOKE_TEST_PASSWORD", "local-only")
    enabled = load_settings()
    assert enabled.run_real_business_smoke is True
    assert enabled.smoke_test_username == "user1"
    assert enabled.smoke_test_password == "local-only"
