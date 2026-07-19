-- Non-destructive Hive ODS contract. This script never inserts sample data.
CREATE DATABASE IF NOT EXISTS ${HIVE_DATABASE};

CREATE TABLE IF NOT EXISTS ${HIVE_DATABASE}.ods_generation_logs (
    id BIGINT COMMENT 'MySQL BIGINT UNSIGNED primary key',
    user_id STRING,
    event_type STRING,
    `timestamp` TIMESTAMP COMMENT 'Business event time',
    prompt STRING,
    style STRING,
    image_url STRING,
    title STRING,
    content STRING,
    generation_time DECIMAL(12,3),
    content_length BIGINT COMMENT 'MySQL INT UNSIGNED',
    user_rating DECIMAL(3,2),
    download_count BIGINT COMMENT 'MySQL INT UNSIGNED',
    user_age SMALLINT COMMENT 'MySQL TINYINT UNSIGNED',
    user_gender SMALLINT COMMENT 'MySQL TINYINT UNSIGNED',
    login_time TIMESTAMP,
    data_origin STRING,
    created_at TIMESTAMP COMMENT 'Database insert time',
    updated_at TIMESTAMP COMMENT 'Database last-update time',
    ingested_at TIMESTAMP COMMENT 'Time this row entered the ODS partition'
)
PARTITIONED BY (
    extract_date DATE COMMENT 'UTC calendar date on which the incremental extraction ran',
    etl_batch_id BIGINT COMMENT 'etl_batches.batch_id used for this extraction'
)
STORED AS PARQUET
TBLPROPERTIES (
    'comment'='ODS copy of MySQL generation_logs, no synthetic fallback data'
);
