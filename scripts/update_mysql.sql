-- 删除所有旧表
DROP TABLE IF EXISTS daily_stats, trend_data, hot_keywords, style_distribution, user_activities, generation_logs;

-- 创建新表
CREATE TABLE daily_stats_enhanced (
    stat_date DATE PRIMARY KEY,
    total_generations INT,
    active_users INT,
    avg_generation_time DECIMAL(10,2),
    avg_rating DECIMAL(3,2),
    total_downloads INT,
    popular_style VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trend_data_enhanced (
    date_str VARCHAR(10) PRIMARY KEY,
    daily_generations INT,
    daily_downloads INT,
    avg_rating DECIMAL(3,2)
);

CREATE TABLE hot_keywords_enhanced (
    keyword VARCHAR(100),
    style VARCHAR(50),
    usage_count INT,
    avg_rating DECIMAL(3,2),
    unique_users INT,
    hot_score DECIMAL(10,2),
    PRIMARY KEY (keyword, style)
);

CREATE TABLE style_distribution_enhanced (
    style VARCHAR(50) PRIMARY KEY,
    generation_count INT,
    download_count INT,
    avg_rating DECIMAL(3,2),
    unique_users INT,
    percentage DECIMAL(5,2)
);

CREATE TABLE user_activities_enhanced (
    user_id VARCHAR(20) PRIMARY KEY,
    username VARCHAR(100),
    generation_count INT,
    download_count INT,
    avg_rating DECIMAL(3,2),
    preferred_style VARCHAR(50),
    last_active DATETIME
);

CREATE TABLE user_profiles_enhanced (
    user_id VARCHAR(20) PRIMARY KEY,
    total_generations INT,
    avg_generation_time DECIMAL(10,2),
    avg_content_length DECIMAL(10,2),
    avg_rating DECIMAL(3,2),
    preferred_styles TEXT,
    avg_prompt_length DECIMAL(10,2),
    style_diversity INT,
    avg_age DECIMAL(5,2),
    gender_ratio DECIMAL(5,2),
    total_downloads INT,
    user_type VARCHAR(20),
    active_period VARCHAR(20),
    last_active DATETIME
);