"""Runtime configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_algorithm: str
    dashscope_api_key: str | None
    dashscope_openai_base_url: str
    dashscope_api_base_url: str
    dashscope_text_model: str
    dashscope_text_reasoning_effort: str
    dashscope_image_model: str
    dashscope_image_size: str
    dashscope_text_connect_timeout_seconds: int
    dashscope_text_read_timeout_seconds: int
    dashscope_image_connect_timeout_seconds: int
    dashscope_image_read_timeout_seconds: int
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str | None
    mysql_database: str
    mysql_connect_timeout_seconds: int
    mysql_read_timeout_seconds: int
    mysql_write_timeout_seconds: int
    run_real_business_smoke: bool
    smoke_test_username: str | None
    smoke_test_password: str | None
    hive_host: str
    hive_port: int
    hive_username: str
    hive_database: str


def load_settings():
    # The application configuration lives next to this module, not necessarily
    # in the process working directory (for example Flask CLI starts at repo root).
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
    return Settings(
        jwt_secret=os.getenv("JWT_SECRET", ""),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
        dashscope_openai_base_url=os.getenv("DASHSCOPE_OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/"),
        dashscope_api_base_url=os.getenv("DASHSCOPE_API_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").rstrip("/"),
        dashscope_text_model=os.getenv("DASHSCOPE_TEXT_MODEL", "qwen3.7-plus"),
        dashscope_image_model=os.getenv("DASHSCOPE_IMAGE_MODEL", "wan2.6-t2i"),
        dashscope_text_reasoning_effort=os.getenv("DASHSCOPE_TEXT_REASONING_EFFORT", "none"),
        dashscope_image_size=os.getenv("DASHSCOPE_IMAGE_SIZE", "1280*1280"),
        dashscope_text_connect_timeout_seconds=_int_env("DASHSCOPE_TEXT_CONNECT_TIMEOUT_SECONDS", 5),
        dashscope_text_read_timeout_seconds=_int_env("DASHSCOPE_TEXT_READ_TIMEOUT_SECONDS", 120),
        dashscope_image_connect_timeout_seconds=_int_env("DASHSCOPE_IMAGE_CONNECT_TIMEOUT_SECONDS", 5),
        dashscope_image_read_timeout_seconds=_int_env("DASHSCOPE_IMAGE_READ_TIMEOUT_SECONDS", 30),
        mysql_host=os.getenv("MYSQL_HOST", "localhost"),
        mysql_port=_int_env("MYSQL_PORT", 3306),
        mysql_user=os.getenv("MYSQL_USER", "root"),
        mysql_password=os.getenv("MYSQL_PASSWORD") or None,
        mysql_database=os.getenv("MYSQL_DATABASE", "aigc_platform"),
        mysql_connect_timeout_seconds=_int_env("MYSQL_CONNECT_TIMEOUT_SECONDS", 5),
        mysql_read_timeout_seconds=_int_env("MYSQL_READ_TIMEOUT_SECONDS", 10),
        mysql_write_timeout_seconds=_int_env("MYSQL_WRITE_TIMEOUT_SECONDS", 10),
        run_real_business_smoke=_bool_env("RUN_REAL_BUSINESS_SMOKE"),
        smoke_test_username=os.getenv("SMOKE_TEST_USERNAME") or None,
        smoke_test_password=os.getenv("SMOKE_TEST_PASSWORD") or None,
        hive_host=os.getenv("HIVE_HOST", "localhost"),
        hive_port=_int_env("HIVE_PORT", 10000),
        hive_username=os.getenv("HIVE_USERNAME", "mywork"),
        hive_database=os.getenv("HIVE_DATABASE", "aigc_platform"),
    )
