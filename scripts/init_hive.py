#!/usr/bin/env python3
import argparse
import os
import sys
import re

from pyhive import hive


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HIVE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_hive_config():
    names = ("HIVE_HOST", "HIVE_PORT", "HIVE_USERNAME", "HIVE_DATABASE")
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing required Hive settings: " + ", ".join(missing))
    if not HIVE_IDENTIFIER.fullmatch(os.environ["HIVE_DATABASE"]):
        raise RuntimeError("HIVE_DATABASE must be a simple Hive identifier")
    try:
        port = int(os.environ["HIVE_PORT"])
    except ValueError as error:
        raise RuntimeError("HIVE_PORT must be an integer") from error
    return {
        "host": os.environ["HIVE_HOST"],
        "port": port,
        "username": os.environ["HIVE_USERNAME"],
        "database": os.environ["HIVE_DATABASE"],
    }


def read_statements(database):
    path = os.path.join(SCRIPT_DIR, "hive_setup.sql")
    with open(path, "r", encoding="utf-8") as sql_file:
        sql = sql_file.read().replace("${HIVE_DATABASE}", database)
        return [statement.strip() for statement in sql.split(";") if statement.strip()]


def init_hive_tables(dry_run=False):
    config = load_hive_config()
    statements = read_statements(config["database"])
    if dry_run:
        for number, statement in enumerate(statements, start=1):
            print(f"statement {number}: {statement}")
        return True

    connection = None
    cursor = None
    try:
        connection = hive.connect(**config)
        cursor = connection.cursor()
        for statement in statements:
            cursor.execute(statement)
        print("Hive ODS schema initialization succeeded")
        return True
    except Exception as error:
        print(f"Hive ODS schema initialization failed ({type(error).__name__})", file=sys.stderr)
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description="Initialize the non-destructive Hive ODS schema")
    parser.add_argument("--dry-run", action="store_true", help="print SQL statements without connecting")
    args = parser.parse_args()
    return 0 if init_hive_tables(dry_run=args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
