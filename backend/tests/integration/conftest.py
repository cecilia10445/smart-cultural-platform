import os
import secrets
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
            command.upgrade(Config("alembic.ini"), "head")
            engine = sa.create_engine(admin_url, hide_parameters=True)
            username = "integration_app"
            password = secrets.token_urlsafe(24)
            with engine.begin() as connection:
                connection.exec_driver_sql(f"CREATE USER '{username}'@'%%' IDENTIFIED BY %s", (password,))
                database = connection.exec_driver_sql("SELECT DATABASE()").scalar_one()
                connection.exec_driver_sql(
                    f"GRANT SELECT, INSERT, UPDATE ON `{database}`.* TO '{username}'@'%%'"
                )
                grants = [row[0] for row in connection.exec_driver_sql(f"SHOW GRANTS FOR '{username}'@'%%'")]
            yield SecretSafeDatabase({
                "engine": engine,
                "host": host,
                "port": int(port),
                "database": mysql.dbname,
                "username": username,
                "password": password,
                "grants": grants,
            })
        finally:
            if engine is not None:
                engine.dispose()
            if previous_url is None:
                os.environ.pop("MIGRATION_DATABASE_URL", None)
            else:
                os.environ["MIGRATION_DATABASE_URL"] = previous_url
