from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_spark_entry_is_disabled_and_cannot_write_online_source():
    source = (ROOT / "scripts" / "spark_etl.py").read_text(encoding="utf-8")
    assert "Legacy Spark ETL is disabled pending the Round 10 incremental pipeline" in source
    assert '.jdbc(mysql_url, "generation_logs"' not in source
    assert '"user": "root"' not in source
    assert '"password": "123456"' not in source
    assert "jdbc:mysql://localhost:3306/aigc_platform" not in source


def test_hive_contract_has_no_sample_insert_or_destructive_source_sql():
    hive_sql = (ROOT / "scripts" / "hive_setup.sql").read_text(encoding="utf-8").upper()
    assert "ODS_GENERATION_LOGS" in hive_sql
    assert "INSERT INTO" not in hive_sql
    assert "DROP TABLE" not in hive_sql
    assert "TRUNCATE" not in hive_sql


def test_destructive_legacy_mysql_script_has_no_executable_reference():
    assert not (ROOT / "scripts" / "update_mysql.sql").exists()
    executable_files = list((ROOT / "scripts").glob("*.py")) + list((ROOT / "scripts").glob("*.sh"))
    for path in executable_files:
        assert "update_mysql.sql" not in path.read_text(encoding="utf-8")


def test_legacy_spark_script_exits_before_importing_pyspark():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "spark_etl.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Legacy Spark ETL is disabled pending the Round 10 incremental pipeline" in result.stderr
