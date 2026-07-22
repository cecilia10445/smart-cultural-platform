-- Non-destructive MySQL baseline for the synchronous Flask application.
-- Application credentials and grants are intentionally managed separately.

CREATE DATABASE IF NOT EXISTS aigc_platform
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE aigc_platform;

CREATE TABLE IF NOT EXISTS generation_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    `timestamp` DATETIME(6) NOT NULL,
    prompt TEXT NULL,
    style VARCHAR(100) NULL,
    image_url VARCHAR(2048) NULL,
    title VARCHAR(255) NULL,
    content LONGTEXT NULL,
    generation_time DECIMAL(12,3) NULL,
    content_length INT UNSIGNED NULL,
    user_rating DECIMAL(3,2) NULL,
    download_count INT UNSIGNED NOT NULL DEFAULT 0,
    user_age TINYINT UNSIGNED NULL,
    user_gender TINYINT UNSIGNED NULL,
    login_time DATETIME(6) NULL,
    data_origin VARCHAR(20) NULL DEFAULT 'production',
    generation_kind VARCHAR(48) NULL,
    prompt_template_version VARCHAR(64) NULL,
    brief_json JSON NULL,
    response_json JSON NULL,
    PRIMARY KEY (id),
    KEY idx_generation_logs_user_timestamp (user_id, `timestamp`),
    KEY idx_generation_logs_timestamp (`timestamp`),
    KEY idx_generation_logs_style_timestamp (style, `timestamp`),
    KEY idx_generation_logs_event_timestamp (event_type, `timestamp`),
    CONSTRAINT chk_generation_logs_data_origin
        CHECK (data_origin IS NULL OR data_origin IN ('production', 'synthetic', 'test', 'public'))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
