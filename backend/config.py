"""Runtime configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_algorithm: str
    dashscope_api_key: str | None
    dashscope_text_timeout_seconds: int
    dashscope_image_timeout_seconds: int
    dashscope_poll_timeout_seconds: int
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str | None
    mysql_database: str
    mysql_connect_timeout_seconds: int
    mysql_read_timeout_seconds: int
    mysql_write_timeout_seconds: int
    hive_host: str
    hive_port: int
    hive_username: str
    hive_database: str


def load_settings():
    load_dotenv()
    return Settings(
        jwt_secret=os.getenv("JWT_SECRET", ""),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
        dashscope_text_timeout_seconds=_int_env("DASHSCOPE_TEXT_TIMEOUT_SECONDS", 20),
        dashscope_image_timeout_seconds=_int_env("DASHSCOPE_IMAGE_TIMEOUT_SECONDS", 30),
        dashscope_poll_timeout_seconds=_int_env("DASHSCOPE_POLL_TIMEOUT_SECONDS", 30),
        mysql_host=os.getenv("MYSQL_HOST", "localhost"),
        mysql_port=_int_env("MYSQL_PORT", 3306),
        mysql_user=os.getenv("MYSQL_USER", "root"),
        mysql_password=os.getenv("MYSQL_PASSWORD") or None,
        mysql_database=os.getenv("MYSQL_DATABASE", "aigc_platform"),
        mysql_connect_timeout_seconds=_int_env("MYSQL_CONNECT_TIMEOUT_SECONDS", 5),
        mysql_read_timeout_seconds=_int_env("MYSQL_READ_TIMEOUT_SECONDS", 10),
        mysql_write_timeout_seconds=_int_env("MYSQL_WRITE_TIMEOUT_SECONDS", 10),
        hive_host=os.getenv("HIVE_HOST", "localhost"),
        hive_port=_int_env("HIVE_PORT", 10000),
        hive_username=os.getenv("HIVE_USERNAME", "mywork"),
        hive_database=os.getenv("HIVE_DATABASE", "aigc_platform"),
    )
