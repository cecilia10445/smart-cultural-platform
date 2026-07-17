-- 创建数据库
CREATE DATABASE IF NOT EXISTS aigc_platform;
USE aigc_platform;

-- 用户画像表
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id STRING,
    favorite_styles ARRAY<STRING>,
    total_generations INT,
    last_active TIMESTAMP
) STORED AS PARQUET;

-- 生成日志表
CREATE TABLE IF NOT EXISTS generation_logs (
    user_id STRING,
    event_type STRING,
    timestamp TIMESTAMP,
    prompt STRING,
    style STRING,
    image_url STRING,
    generation_time DOUBLE,
    content_length INT,
    title STRING,
    content STRING,
    captions ARRAY<STRING>,  -- 添加captions字段
    prompt_length INT        -- 添加prompt_length字段
) STORED AS PARQUET;

-- 插入一些测试数据（如果表为空）
INSERT INTO aigc_platform.generation_logs VALUES
('U1001', 'generate', CURRENT_TIMESTAMP, '夏日海滩', '清新', 'http://example.com/1.jpg', 5.2, 150, '夏日海滩', '海滩描述'),
('U1002', 'generate', CURRENT_TIMESTAMP, '未来城市', '赛博朋克', 'http://example.com/2.jpg', 6.1, 180, '未来城市', '城市描述'),
('U1001', 'generate', DATE_SUB(CURRENT_TIMESTAMP, 1), '星空夜景', '浪漫', 'http://example.com/3.jpg', 4.8, 160, '星空夜景', '星空描述');