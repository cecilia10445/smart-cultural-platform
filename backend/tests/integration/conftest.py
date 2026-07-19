import os
import secrets
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote_plus

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from testcontainers.mysql import MySqlContainer


class SecretSafeDatabase(dict):
    def __repr__(self):
        return "<disposable MySQL test database; credentials redacted>"


@pytest.fixture(scope="session")
def mysql_container_database():
    if os.getenv("RUN_MYSQL_INTEGRATION") != "1":
        pytest.skip("set RUN_MYSQL_INTEGRATION=1 to start the disposable MySQL container")

    with MySqlContainer("mysql:8.0", dialect="pymysql") as mysql:
        host = mysql.get_container_host_ip()
        port = mysql.get_exposed_port(3306)
        admin_url = f"mysql+pymysql://root:{quote_plus(mysql.root_password)}@{host}:{port}/{mysql.dbname}"
        previous_url = os.environ.get("MIGRATION_DATABASE_URL")
        os.environ["MIGRATION_DATABASE_URL"] = admin_url
        engine = None
        try:
            engine = sa.create_engine(admin_url, hide_parameters=True)
            command.upgrade(Config("alembic.ini"), "0001")
            historical_expected = {
                "user_id": "history-user", "event_type": "generate",
                "timestamp": datetime(2026, 1, 1, 0, 0, 0),
                "prompt": "historical prompt", "style": "historical-style",
                "image_url": None, "title": "historical title", "content": "historical content",
                "generation_time": Decimal("1.250"), "content_length": 17,
                "user_rating": None, "download_count": 2, "user_age": None,
                "user_gender": None, "login_time": None, "data_origin": "test",
            }
            with engine.begin() as connection:
                result = connection.execute(sa.text(
                    """INSERT INTO generation_logs
                    (user_id,event_type,timestamp,prompt,style,image_url,title,content,
                     generation_time,content_length,user_rating,download_count,user_age,
                     user_gender,login_time,data_origin)
                    VALUES (:user_id,:event_type,:timestamp,:prompt,:style,:image_url,:title,
                            :content,:generation_time,:content_length,:user_rating,:download_count,
                            :user_age,:user_gender,:login_time,:data_origin)"""
                ), historical_expected)
                historical_expected["id"] = result.lastrowid
            command.upgrade(Config("alembic.ini"), "head")
            username = "integration_app"
            password = secrets.token_urlsafe(24)
            etl_username = "integration_etl"
            etl_password = secrets.token_urlsafe(24)
            with engine.begin() as connection:
                connection.exec_driver_sql(f"CREATE USER '{username}'@'%%' IDENTIFIED BY %s", (password,))
                database = connection.exec_driver_sql("SELECT DATABASE()").scalar_one()
                connection.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON `{database}`.* TO '{username}'@'%%'"
                )
                connection.exec_driver_sql(f"CREATE USER '{etl_username}'@'%%' IDENTIFIED BY %s", (etl_password,))
                for table, privileges in {
                    "alembic_version": "SELECT", "generation_logs": "SELECT",
                    "etl_batches": "SELECT, INSERT, UPDATE", "data_quality_results": "SELECT, INSERT",
                }.items():
                    connection.exec_driver_sql(f"GRANT {privileges} ON `{database}`.`{table}` TO '{etl_username}'@'%%'")
                grants = [row[0] for row in connection.exec_driver_sql(f"SHOW GRANTS FOR '{username}'@'%%'")]
                etl_grants = [row[0] for row in connection.exec_driver_sql(f"SHOW GRANTS FOR '{etl_username}'@'%%'")]
            yield SecretSafeDatabase({
                "engine": engine,
                "host": host,
                "port": int(port),
                "database": mysql.dbname,
                "username": username,
                "password": password,
                "admin_password": mysql.root_password,
                "etl_username": etl_username,
                "etl_password": etl_password,
                "etl_grants": etl_grants,
                "grants": grants,
                "historical_expected": historical_expected,
            })
        finally:
            if engine is not None:
                engine.dispose()
            if previous_url is None:
                os.environ.pop("MIGRATION_DATABASE_URL", None)
            else:
                os.environ["MIGRATION_DATABASE_URL"] = previous_url
