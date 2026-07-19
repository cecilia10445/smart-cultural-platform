# Data Pipeline Contract

## Implemented boundary

MySQL `aigc_platform.generation_logs` is the source of truth for online generation events. Spark must never drop, truncate, recreate, or overwrite it. Round 09 versions the source schema, the Hive ODS target contract, batch controls, and safety checks. It does not move production data or produce analytics tables; extraction, aggregation, and controlled result writeback belong to Round 10.

## MySQL source fields

| Field | MySQL type | Nullable | Meaning |
|---|---|---:|---|
| id | BIGINT UNSIGNED | no | Monotonic database primary key |
| user_id | VARCHAR(64) | no | Application user identifier |
| event_type | VARCHAR(32) | no | Business event type |
| timestamp | DATETIME(6) | no | Business event time |
| prompt | TEXT | yes | User prompt |
| style | VARCHAR(100) | yes | Requested style |
| image_url | VARCHAR(2048) | yes | Generated image location |
| title | VARCHAR(255) | yes | Generated title |
| content | LONGTEXT | yes | Generated text |
| generation_time | DECIMAL(12,3) | yes | Generation duration |
| content_length | INT UNSIGNED | yes | Generated content length |
| user_rating | DECIMAL(3,2) | yes | User rating |
| download_count | INT UNSIGNED | no | Download count, default 0 |
| user_age | TINYINT UNSIGNED | yes | Reported age |
| user_gender | TINYINT UNSIGNED | yes | Existing coded gender value |
| login_time | DATETIME(6) | yes | Login time associated with event |
| data_origin | VARCHAR(20) | yes | Provenance classification |
| created_at | DATETIME(6) | no | Database first-insert time |
| updated_at | DATETIME(6) | no | Database last-update time |

`timestamp` is supplied by the business event. `created_at` is assigned when MySQL first stores the row. `updated_at` is assigned by MySQL and automatically changes when a stored row changes.

Rows that existed before migration 0002 cannot recover their historical database write or update times. MySQL assigns migration-time defaults when the columns are added. The first incremental synchronization must treat these rows as an initialization snapshot; the populated values must not be described as original business creation times.

## MySQL to Hive ODS mapping

MySQL integer identifiers and unsigned counters map to Hive `BIGINT`; `TINYINT UNSIGNED` maps to `SMALLINT`; character, text, and long-text fields map to `STRING`; decimals retain their precision and scale; MySQL `DATETIME(6)` maps to Hive `TIMESTAMP`. The ODS adds `etl_batch_id`, `ingested_at`, and the extraction-day partition `extract_date`. Hive cannot preserve MySQL unsigned semantics, so range validation is a data-quality responsibility.

The ODS table is `aigc_platform.ods_generation_logs`. The legacy Hive `generation_logs` table is not altered by Round 09 and must not be treated as the new ODS contract.

## Incremental watermark

Incremental extraction uses the ordered pair `(updated_at, id)`. A pure `id` watermark is insufficient because rating and download operations update existing rows. The next batch selects values strictly after the previous pair in lexicographic order and records both start and end pairs.

## Batch and quality controls

`etl_batches` transitions from `RUNNING` to either `SUCCEEDED` or `FAILED`. It records the composite watermark, source/Hive/output counts, times, and a stable `error_code`. The error code must never contain credentials, a database URL, or a stack trace.

`data_quality_results` stores batch-scoped checks with status `PASSED` or `FAILED`. Initial checks are source-to-Hive row count, non-null source primary keys, watermark ordering, and output row count when an output is produced.

## Data origin

- `production`: real online application event.
- `test`: controlled automated or manual verification data.
- `synthetic`: explicitly generated artificial data.
- `public`: imported public dataset data.

Only production records may be represented as production analytics. Test, synthetic, and public records require explicit filtering or separately labelled outputs.

## Deferred work

Round 09 does not implement MySQL extraction, ODS loading, Spark aggregation, analytics result tables, retries, or production scheduling. Round 10 must implement and verify those operations before the repository can claim an end-to-end data pipeline.
