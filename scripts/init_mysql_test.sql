-- Non-destructive database setup for opt-in MySQL integration tests.
-- The application account must already exist; credentials are managed outside Git.

CREATE DATABASE IF NOT EXISTS aigc_platform_test
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS aigc_platform_test.generation_logs
    LIKE aigc_platform.generation_logs;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON aigc_platform_test.*
    TO 'lily'@'localhost';
