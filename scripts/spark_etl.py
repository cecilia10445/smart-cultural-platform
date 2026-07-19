#!/usr/bin/env python3
"""Retired legacy ETL entry point; Round 10 owns the replacement pipeline."""
import sys


DISABLED_MESSAGE = "Legacy Spark ETL is disabled pending the Round 10 incremental pipeline"


def main():
    raise RuntimeError(DISABLED_MESSAGE)


if __name__ == "__main__":
    print(DISABLED_MESSAGE, file=sys.stderr)
    raise SystemExit(1)


import json
import os
from datetime import datetime, timedelta

def legacy_pipeline_body():
    print("=== 智能文创平台增强版Spark ETL与推荐系统 ===")
    
    spark = SparkSession.builder \
        .appName("AIGCPlatformEnhancedETL") \
        .config("spark.sql.warehouse.dir", "/user/hive/warehouse") \
        .config("spark.jars", "/usr/local/hive/lib/mysql-connector-j-8.0.33.jar") \
        .config("spark.driver.extraJavaOptions", "-Dlog4j.configuration=file:log4j.properties") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")

    # 1. 读取所有数据源
    print("=== 1. 读取数据源 ===")
    all_dfs = []
    
    try:
        dataset_path = "/home/mywork/smart-cultural-platform/data/dataset/daily_*.json"
        synthetic_data = spark.read.json(dataset_path)
        print(f"📊 模拟数据集记录数: {synthetic_data.count()}")
    
        if synthetic_data.count() > 0:
            synthetic_processed = process_logs_data(synthetic_data, 'synthetic')
            all_dfs.append(synthetic_processed)
    except Exception as e:
        print(f"⚠️ 模拟数据集处理失败: {e}")
        import traceback
        traceback.print_exc()

    # 实时日志
    try:
        realtime_logs = spark.read.json("hdfs://localhost:9000/user/logs/aigc_platform/app_*.log")
        print(f"📊 实时日志原始记录数: {realtime_logs.count()}")
        
        if realtime_logs.count() > 0:
            realtime_processed = process_logs_data(realtime_logs, 'realtime')
            all_dfs.append(realtime_processed)
    except Exception as e:
        print(f"⚠️ 实时日志处理失败: {e}")
    
    

    # Flickr30K数据集 - 增强处理
    try:
        flickr_logs = spark.read.json("hdfs://localhost:9000/user/logs/aigc_platform/flickr_data/*.json")
        print(f"📊 Flickr30K原始记录数: {flickr_logs.count()}")
        
        if flickr_logs.count() > 0:
            flickr_processed = process_logs_data(flickr_logs, 'flickr')
            all_dfs.append(flickr_processed)
            
    except Exception as e:
        print(f"⚠️ Flickr30K数据集处理失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 合并数据
    if all_dfs:
        combined_df = all_dfs[0]
        for i, df in enumerate(all_dfs[1:]):
            print(f"🔄 合并数据集 {i+2}, 记录数: {df.count()}")
            combined_df = combined_df.unionByName(df)
    else:
        # 创建包含新字段的空DataFrame
        combined_df = create_empty_dataframe(spark)
        print("⚠️ 无数据可用，使用空DataFrame")
    
    print(f"📊 合并后总记录数: {combined_df.count()}")
    
    # 2. 数据增强 - 添加新字段
    print("=== 2. 数据增强 ===")
    enhanced_df = enhance_data(combined_df)
    
    # 3. 特征工程
    print("=== 3. 特征工程 ===")
    feature_df = feature_engineering(enhanced_df)
    
    # 4. 用户画像和聚类
    print("=== 4. 用户画像与聚类 ===")
    user_profiles = build_user_profiles_with_clustering(feature_df)
    
    # 5. 推荐算法（基于用户分群的协同过滤）
    print("=== 5. 推荐算法训练 ===")
    recommendation_models = train_enhanced_recommendation_models(feature_df, user_profiles)
    
    # 6. 运营端数据分析
    print("=== 6. 运营端数据分析 ===")
    dashboard_data = generate_dashboard_data(feature_df, user_profiles, recommendation_models)
    
    # 7. 用户端推荐数据
    print("=== 7. 用户端推荐数据生成 ===")
    user_recommendations = generate_user_recommendations(feature_df, user_profiles, recommendation_models)
    
    # 8. 保存结果到MySQL
    print("=== 8. 保存结果到MySQL ===")
    save_results_to_mysql(spark, dashboard_data, user_recommendations, user_profiles, enhanced_df)
    
    spark.stop()
    print("=== 增强版ETL完成 ===")

from pyspark.sql.types import StructType

def process_logs_data(df, source_type='realtime'):
    """处理日志数据 - 增强版，支持多种数据源"""
    try:
        # 检查数据列结构
        print(f"🔍 处理{source_type}数据，列名: {df.columns}")

         # ==================== 新增：处理模拟数据集 ====================
        if source_type == 'synthetic':
            print("✅ 模拟数据集已包含完整字段，直接返回")
            # 模拟数据集已经有所有字段，直接返回，只需要过滤event_type
            processed = df.filter(col("event_type").isin(["generate", "download"]))
            print(f"📊 synthetic处理结果: {processed.count()} 条记录")
            return processed
        # ==================== 新增结束 ====================
        
        # -------------------------- 修复1：正确检查结构体子字段存在性 --------------------------
        # 初始化字段存在性为 False
        has_user_rating = False
        has_download_count = False
        has_user_age = False
        has_user_gender = False
        has_login_time = False
        
        # 检查 data 字段是否存在且是结构体类型
        if 'data' in df.columns:
            data_schema = df.schema['data'].dataType  # 获取 data 字段的 schema
            if isinstance(data_schema, StructType):  # 确认是结构体类型
                # 获取 data 结构体的所有子字段名
                data_fields = [field.name for field in data_schema.fields]
                # 判断子字段是否存在
                has_user_rating = 'user_rating' in data_fields
                has_download_count = 'download_count' in data_fields
                has_user_age = 'user_age' in data_fields
                has_user_gender = 'user_gender' in data_fields
                has_login_time = 'login_time' in data_fields
        
        print(f"📊 字段存在性检查 - user_rating: {has_user_rating}, download_count: {has_download_count}, user_age: {has_user_age}, user_gender: {has_user_gender}, login_time: {has_login_time}")
        
        # -------------------------- 修复2：访问子字段时增加安全判断 --------------------------
        if source_type == 'flickr':
            if 'data' in df.columns:
                flickr_processed = df.select(
                    col("user_id"),
                    lit("generate").alias("event_type"),
                    col("timestamp"),
                    # 安全访问 data 子字段：存在则用，不存在则设为 null
                    col("data.prompt").alias("prompt") if 'prompt' in data_fields else lit(None).alias("prompt"),
                    col("data.style").alias("style") if 'style' in data_fields else lit(None).alias("style"),
                    col("data.image_url").alias("image_url") if 'image_url' in data_fields else lit(None).alias("image_url"),
                    col("data.generation_time").alias("generation_time") if 'generation_time' in data_fields else lit(None).alias("generation_time"),
                    col("data.content_length").alias("content_length") if 'content_length' in data_fields else lit(None).alias("content_length"),
                    col("data.captions").alias("captions") if 'captions' in data_fields else lit(None).alias("captions"),
                    col("data.title").alias("title") if 'title' in data_fields else lit(None).alias("title"),
                    col("data.content").alias("content") if 'content' in data_fields else lit(None).alias("content"),
                    # 处理不存在的 user_rating 等字段：直接设为 null 或默认值（不再访问 data.user_rating）
                    lit(None).alias("user_rating"),  # 原始数据无该字段，设为 null
                    lit(0).alias("download_count"),  # 无该字段，默认 0
                    lit(None).alias("user_age"),
                    lit(None).alias("user_gender"),
                    lit(None).alias("login_time")
                )
            else:
                # 无 data 字段的处理逻辑不变（略）
                flickr_processed = df.select(
                    col("user_id"),
                    lit("generate").alias("event_type"),
                    col("timestamp"),
                    col("prompt"),
                    col("style"),
                    col("image_url"),
                    col("generation_time"),
                    col("content_length"),
                    col("captions"),
                    col("title"),
                    col("content"),
                    lit(None).alias("user_rating"),
                    lit(0).alias("download_count"),
                    lit(None).alias("user_age"),
                    lit(None).alias("user_gender"),
                    lit(None).alias("login_time")
                )
            
            return flickr_processed
            
        else:
            # 实时日志数据处理
            # 先获取 data 结构体的子字段列表（避免后续重复判断）
            data_fields = [field.name for field in df.schema['data'].dataType.fields] if ('data' in df.columns and isinstance(df.schema['data'].dataType, StructType)) else []
            
            processed = df.select(
                # 安全获取 user_id（优先 data.user_id，其次顶层 user_id）
                when(col("data.user_id").isNotNull() & col("data.user_id").isin(data_fields), col("data.user_id"))
                    .otherwise(col("user_id")).alias("user_id"),
                col("event_type"),
                col("timestamp"),
                # 安全访问 data 子字段
                col("data.prompt").alias("prompt") if 'prompt' in data_fields else lit(None).alias("prompt"),
                col("data.style").alias("style") if 'style' in data_fields else lit(None).alias("style"),
                col("data.image_url").alias("image_url") if 'image_url' in data_fields else lit(None).alias("image_url"),
                col("data.generation_time").alias("generation_time") if 'generation_time' in data_fields else lit(None).alias("generation_time"),
                col("data.content_length").alias("content_length") if 'content_length' in data_fields else lit(None).alias("content_length"),
                col("data.captions").alias("captions") if 'captions' in data_fields else lit(None).alias("captions"),
                col("data.title").alias("title") if 'title' in data_fields else lit(None).alias("title"),
                col("data.content").alias("content") if 'content' in data_fields else lit(None).alias("content"),
                # 处理不存在的字段：直接设为 null 或默认值
                lit(None).alias("user_rating"),
                lit(0).alias("download_count"),
                lit(None).alias("user_age"),
                lit(None).alias("user_gender"),
                lit(None).alias("login_time"),
            ).filter(col("event_type").isin(["generate", "download"]))
            
            print(f"📊 {source_type}处理结果: {processed.count()} 条记录")
            return processed
            
    except Exception as e:
        print(f"❌ 处理{source_type}数据失败: {e}")
        import traceback
        traceback.print_exc()
        # 返回与原始数据结构一致的空 DataFrame（避免合并报错）
        return df.sql_ctx.sparkSession.createDataFrame([], df.schema)

def create_empty_dataframe(spark):
    """创建包含所有字段的空DataFrame"""
    schema = StructType([
        StructField("user_id", StringType(), True),
        StructField("event_type", StringType(), True),
        StructField("timestamp", StringType(), True),
        StructField("prompt", StringType(), True),
        StructField("style", StringType(), True),
        StructField("image_url", StringType(), True),
        StructField("generation_time", DoubleType(), True),
        StructField("content_length", IntegerType(), True),
        StructField("captions", ArrayType(StringType()), True),
        StructField("title", StringType(), True),
        StructField("content", StringType(), True),
        StructField("user_rating", IntegerType(), True),
        StructField("download_count", IntegerType(), True),
        StructField("user_age", IntegerType(), True),
        StructField("user_gender", IntegerType(), True),
        StructField("login_time", StringType(), True)
    ])
    return spark.createDataFrame([], schema)

def enhance_data(df):
    """数据增强 - 添加新字段，优先使用真实数据"""
    from pyspark.sql.functions import rand, when, lit
    
    enhanced_df = df \
        .withColumn("prompt_length", length(col("prompt"))) \
        .withColumn("content_quality",
                   when(col("content_length") > 80, "high")
                   .when(col("content_length") > 40, "medium")
                   .otherwise("low")) \
        .withColumn("user_rating", # 用户评分：只有缺失时才生成随机值
                   when(col("user_rating").isNotNull(), col("user_rating"))
                   .otherwise((rand() * 4 + 1).cast("int"))) \
        .withColumn("download_count", # 下载次数：优先使用真实数据，缺失时随机生成
                   when(col("download_count").isNotNull(), col("download_count"))
                   .when(rand() > 0.8, (rand() * 100).cast("int"))
                   .otherwise(0)) \
        .withColumn("user_age", # 用户年龄：只有缺失时才生成随机值
                   when(col("user_age").isNotNull(), col("user_age"))
                   .when(rand() > 0.1, (rand() * 50 + 18).cast("int"))
                   .otherwise(None)) \
        .withColumn("user_gender", # 用户性别：只有缺失时才生成随机值
                   when(col("user_gender").isNotNull(), col("user_gender"))
                   .when(rand() > 0.1, (rand() * 2).cast("int"))
                   .otherwise(None))\
        .withColumn("login_time", # 确保login_time是字符串类型
                   when(col("login_time").isNotNull(), col("login_time"))
                   .otherwise(lit("")))
    
    print("✅ 数据增强完成")
    # 显示数据统计
    print(f"📊 真实评分数量: {enhanced_df.filter(col('user_rating').isNotNull()).count()}")
    print(f"📊 真实下载记录数量: {enhanced_df.filter(col('download_count') > 0).count()}")
    print(f"📊 真实年龄数量: {enhanced_df.filter(col('user_age').isNotNull()).count()}")
    print(f"📊 真实性别数量: {enhanced_df.filter(col('user_gender').isNotNull()).count()}")
    
    return enhanced_df

def feature_engineering(df):
    """特征工程 - 确保不丢失用户数据"""
    print("🔧 开始特征工程...")
    original_count = df.count()
    original_users = df.select("user_id").distinct().count()
    
    try:
        # 中文提示词分词 - 但不要过滤掉没有中文的数据
        chinese_prompts = df.filter(col("prompt").rlike("[\u4e00-\u9fa5]"))
        english_prompts = df.filter(~col("prompt").rlike("[\u4e00-\u9fa5]"))
        
        print(f"📝 中文提示词: {chinese_prompts.count()} 条")
        print(f"📝 英文提示词: {english_prompts.count()} 条")
        
        if chinese_prompts.count() > 0:
            from pyspark.ml.feature import Tokenizer, StopWordsRemover
            tokenizer = Tokenizer(inputCol="prompt", outputCol="words")
            remover = StopWordsRemover(inputCol="words", outputCol="keywords")
            
            pipeline = Pipeline(stages=[tokenizer, remover])
            model = pipeline.fit(chinese_prompts)
            chinese_processed = model.transform(chinese_prompts)
        else:
            chinese_processed = chinese_prompts.withColumn("keywords", lit(None)).withColumn("words", lit(None))
        
        # 英文数据保持不变，添加空的关键词列和words列
        english_processed = english_prompts.withColumn("keywords", lit(None)).withColumn("words", lit(None))
        
        # 重新合并数据 - 确保列数一致
        if chinese_processed.count() > 0 and english_processed.count() > 0:
            # 选择相同的列
            common_columns = chinese_processed.columns
            english_processed_selected = english_processed.select(common_columns)
            processed_df = chinese_processed.union(english_processed_selected)
        elif chinese_processed.count() > 0:
            processed_df = chinese_processed
        else:
            processed_df = english_processed
        
        print(f"🔄 合并后记录数: {processed_df.count()}")
        
    except Exception as e:
        print(f"❌ 分词处理失败: {e}")
        # 如果分词失败，直接添加空的关键词列和words列
        processed_df = df.withColumn("keywords", lit(None)).withColumn("words", lit(None))
    
    try:
        # 风格编码 - 处理所有风格，包括英文风格
        from pyspark.ml.feature import StringIndexer
        style_indexer = StringIndexer(inputCol="style", outputCol="style_index")
        style_model = style_indexer.fit(processed_df)
        processed_df = style_model.transform(processed_df)
        
        print(f"🎨 风格数量: {processed_df.select('style').distinct().count()}")
        
    except Exception as e:
        print(f"❌ 风格编码失败: {e}")
        processed_df = processed_df.withColumn("style_index", lit(0))
    
    try:
        # 时间特征 - 确保时间格式正确
        from pyspark.sql.functions import hour, dayofweek
        processed_df = processed_df \
            .withColumn("hour", 
                       when(col("timestamp").isNotNull(), hour(col("timestamp")))
                       .otherwise(lit(12))) \
            .withColumn("day_of_week",
                       when(col("timestamp").isNotNull(), dayofweek(col("timestamp")))
                       .otherwise(lit(1))) \
            .withColumn("is_weekend", 
                       when((col("day_of_week") == 1) | (col("day_of_week") == 7), 1)
                       .otherwise(0))
        
    except Exception as e:
        print(f"❌ 时间特征处理失败: {e}")
        processed_df = processed_df \
            .withColumn("hour", lit(12)) \
            .withColumn("day_of_week", lit(1)) \
            .withColumn("is_weekend", lit(0))
    
    # 最终检查
    final_count = processed_df.count()
    final_users = processed_df.select("user_id").distinct().count()
    
    print(f"✅ 特征工程完成")
    print(f"📊 记录数变化: {original_count} -> {final_count}")
    print(f"👥 用户数变化: {original_users} -> {final_users}")
    
    if final_users < original_users:
        print(f"⚠️ 警告: 特征工程过程中丢失了 {original_users - final_users} 个用户")
        # 显示丢失的用户
        original_users_set = df.select("user_id").distinct()
        final_users_set = processed_df.select("user_id").distinct()
        lost_users = original_users_set.subtract(final_users_set)
        print("⚠️ 丢失的用户:")
        lost_users.show(20, truncate=False)
    
    return processed_df

def build_user_profiles_with_clustering(df):
    """构建用户画像并加入KMeans聚类"""
    print("👥 开始用户画像构建与聚类...")
    
    # 基础用户画像
    user_base_profiles = df.groupBy("user_id").agg(
        count("*").alias("total_generations"),
        avg("generation_time").alias("avg_generation_time"),
        avg("content_length").alias("avg_content_length"),
        avg("user_rating").alias("avg_rating"),
        collect_set("style").alias("preferred_styles"),
        avg("prompt_length").alias("avg_prompt_length"),
        countDistinct("style").alias("style_diversity"),
        avg("user_age").alias("avg_age"),
        avg("user_gender").alias("gender_ratio"),
        sum("download_count").alias("total_downloads"),
        avg("hour").alias("avg_active_hour"),
        max("timestamp").alias("last_active")
    )
    
    # 处理年龄分段
    user_base_profiles = user_base_profiles.withColumn(
        "age_range",
        when(col("avg_age").isNull(), 0)
        .when(col("avg_age") < 18, 1)
        .when(col("avg_age") <= 24, 2)
        .when(col("avg_age") <= 29, 3)
        .when(col("avg_age") <= 34, 4)
        .when(col("avg_age") <= 39, 5)
        .when(col("avg_age") <= 49, 6)
        .otherwise(7)
    )
    
    # 处理活跃时间段
    user_base_profiles = user_base_profiles.withColumn(
        "active_period",
        when(col("avg_active_hour") < 6, 0)  # 深夜党
        .when(col("avg_active_hour") < 12, 1)  # 上午党
        .when(col("avg_active_hour") < 18, 2)  # 下午党
        .otherwise(3)  # 晚间党
    )
    
    # 用户分群特征工程
    feature_columns = [
        "total_generations", 
        "avg_generation_time", 
        "avg_content_length",
        "avg_rating", 
        "avg_prompt_length", 
        "style_diversity",
        "total_downloads",
        "avg_active_hour"
    ]
    
    # 处理缺失值
    user_features = user_base_profiles
    for col_name in feature_columns:
        user_features = user_features.fillna(0, subset=[col_name])
    
    # 特征向量化
    assembler = VectorAssembler(inputCols=feature_columns, outputCol="features")
    user_features_vector = assembler.transform(user_features)
    
    # KMeans聚类 (4个用户群体)
    kmeans = KMeans(k=4, seed=42, featuresCol="features", predictionCol="user_cluster")
    kmeans_model = kmeans.fit(user_features_vector)
    user_profiles_with_cluster = kmeans_model.transform(user_features_vector)
    
    # 添加用户类型标签
    user_profiles_final = user_profiles_with_cluster.withColumn(
        "user_type",
        when(col("user_cluster") == 0, "高活跃创作型")
        .when(col("user_cluster") == 1, "普通体验型") 
        .when(col("user_cluster") == 2, "高质量偏好型")
        .otherwise("低频探索型")
    )
    
    print(f"✅ 用户画像构建完成，共 {user_profiles_final.count()} 个用户")
    print("📊 用户分群分布:")
    user_profiles_final.groupBy("user_cluster", "user_type").count().show()
    
    return user_profiles_final

def train_enhanced_recommendation_models(df, user_profiles):
    """基于用户分群的增强推荐算法"""
    models = {}
    
    try:
        # 获取用户分群信息
        user_clusters = user_profiles.select("user_id", "user_cluster")
        
        # 创建用户-风格评分矩阵（包含分群信息）
        style_ratings_with_cluster = df.join(user_clusters, "user_id", "left") \
            .groupBy("user_id", "user_cluster", "style").agg(
                count("*").alias("interaction_count"),
                avg("user_rating").alias("avg_rating"),
                sum("download_count").alias("total_downloads"),
                avg("generation_time").alias("avg_generation_time")
            ).withColumn("final_rating", 
                       col("interaction_count") * 0.2 + 
                       col("avg_rating") * 0.4 +
                       col("total_downloads") * 0.3 +
                       (1.0 / (col("avg_generation_time") + 0.1)) * 0.1)
        
        # 为每个用户分群训练独立的ALS模型
        for cluster_id in range(4):
            cluster_data = style_ratings_with_cluster.filter(col("user_cluster") == cluster_id)
            
            if cluster_data.count() > 0:
                # 用户和风格索引
                user_indexer = StringIndexer(inputCol="user_id", outputCol="user_id_numeric")
                style_indexer = StringIndexer(inputCol="style", outputCol="style_index_numeric")
                
                pipeline = Pipeline(stages=[user_indexer, style_indexer])
                indexer_model = pipeline.fit(cluster_data)
                cluster_data_indexed = indexer_model.transform(cluster_data)
                
                # ALS模型训练
                als = ALS(
                    maxIter=10,
                    regParam=0.01,
                    userCol="user_id_numeric",
                    itemCol="style_index_numeric",
                    ratingCol="final_rating",
                    coldStartStrategy="drop",
                    nonnegative=True
                )
                
                als_model = als.fit(cluster_data_indexed)
                models[f'als_cluster_{cluster_id}'] = {
                    'model': als_model,
                    'indexer': indexer_model,
                    'cluster_data': cluster_data_indexed
                }
                
                print(f"✅ 分群 {cluster_id} ALS模型训练完成，用户数: {cluster_data_indexed.select('user_id').distinct().count()}")
        
        # 热门风格推荐（全局）
        popular_styles = df.groupBy("style").agg(
            count("*").alias("generation_count"),
            avg("user_rating").alias("avg_rating"),
            sum("download_count").alias("total_downloads"),
            countDistinct("user_id").alias("unique_users"),
            avg("generation_time").alias("avg_generation_time")
        ).withColumn("popularity_score",
                   col("generation_count") * 0.3 + 
                   col("avg_rating") * 0.3 +
                   col("total_downloads") * 0.2 +
                   col("unique_users") * 0.2)
        
        models['popular_styles'] = popular_styles
        
        # 关键词推荐
        keyword_recs = extract_popular_keywords(df)
        models['keyword_recommendations'] = keyword_recs
        
    except Exception as e:
        print(f"❌ 增强推荐模型训练失败: {e}")
        import traceback
        traceback.print_exc()
    
    return models

def generate_dashboard_data(df, user_profiles, recommendation_models):
    """生成运营端仪表盘数据 - 使用全部历史数据"""
    dashboard_data = {}
    
    # 1. 用户画像仪表盘数据
    print("📊 生成用户画像仪表盘数据...")
    
    # 年龄分布 - 使用全部用户数据
    age_distribution = user_profiles.groupBy("age_range").agg(
        count("*").alias("age_count")
    ).orderBy("age_range")
    
    # 性别比例 - 使用全部用户数据
    gender_distribution = user_profiles.withColumn(
        "gender_category",
        when(col("gender_ratio").isNull(), 2)
        .when(col("gender_ratio") < 0.4, 0)  # 女性
        .when(col("gender_ratio") > 0.6, 1)  # 男性
        .otherwise(2)  # 未知
    ).groupBy("gender_category").agg(
        count("*").alias("gender_count")
    )
    
    # 活跃时间段分布 - 使用全部用户数据
    active_period_distribution = user_profiles.groupBy("active_period").agg(
        count("*").alias("period_count")
    )
    
    dashboard_data['age_distribution'] = age_distribution
    dashboard_data['gender_distribution'] = gender_distribution
    dashboard_data['active_period_distribution'] = active_period_distribution
    
    # 2. 用户行为分析 - 按日期聚合全部历史数据
    print("📈 生成用户行为数据...")
    
    # 获取所有日期的用户行为数据
    all_time_behavior = df.groupBy(date_format("timestamp", "yyyy-MM-dd").alias("stat_date")) \
        .agg(
            count("*").alias("generation_count"),
            sum("download_count").alias("download_count"),
            countDistinct("user_id").alias("active_users")
        ).orderBy("stat_date")
    
    dashboard_data['recent_behavior'] = all_time_behavior
    
    # 3. 风格热度排行 - 使用全部历史数据
    print("🔥 生成风格热度排行...")
    style_popularity_all_time = df.groupBy("style") \
        .agg(
            count("*").alias("generation_count"),
            sum("download_count").alias("download_count"),
            avg("user_rating").alias("avg_rating"),
            countDistinct("user_id").alias("unique_users")
        ).orderBy(col("generation_count").desc()) \
        .limit(10) \
        .withColumn("popularity_rank", row_number().over(Window.orderBy(col("generation_count").desc())))
    
    dashboard_data['style_popularity'] = style_popularity_all_time
    
    # 4. 风格趋势分析 - 使用全部历史数据
    print("📅 生成风格趋势...")
    style_trend_all_time = df.groupBy(
            date_format("timestamp", "yyyy-MM-dd").alias("stat_date"),
            "style"
        ).agg(
            count("*").alias("daily_count"),
            sum("download_count").alias("daily_downloads"),
            avg("user_rating").alias("avg_rating")
        ).orderBy("stat_date", "style")
    
    dashboard_data['style_trend'] = style_trend_all_time
    
    # 5. 用户满意度分布 - 使用全部历史数据
    print("⭐ 生成用户满意度分布...")
    rating_dist = df.groupBy(round(col("user_rating")).alias("rating")) \
        .agg(count("*").alias("rating_count")) \
        .withColumn("percentage", round(col("rating_count") * 100 / df.count(), 2)) \
        .orderBy("rating")
    
    dashboard_data['rating_distribution'] = rating_dist
    
    # 6. 热门关键词分析 - 使用全部历史数据
    print("🔑 生成热门关键词分析...")
    if 'keyword_recommendations' in recommendation_models:
        top_keywords = recommendation_models['keyword_recommendations'] \
            .orderBy(col("hot_score").desc()) \
            .limit(10)
        
        # 为每个关键词获取全部趋势数据
        keyword_trend_data = {}
        keyword_list = [row['keyword'] for row in top_keywords.collect()]
        
        for keyword in keyword_list[:5]:  # 只处理前5个关键词的趋势
            keyword_trend = df.filter(
                array_contains(col("keywords"), keyword) | col("prompt").contains(keyword)
            ).groupBy(date_format("timestamp", "yyyy-MM-dd").alias("stat_date")) \
             .agg(count("*").alias("daily_usage")) \
             .orderBy("stat_date")
            
            trend_dict = {row['stat_date']: row['daily_usage'] for row in keyword_trend.collect()}
            keyword_trend_data[keyword] = trend_dict
        
        top_keywords_with_trend = top_keywords.withColumn(
            "trend_data", 
            lit(str(keyword_trend_data))  # 简化处理，实际应该用JSON格式
        )
        
        dashboard_data['keyword_analysis'] = top_keywords_with_trend
    
    # 7. 生成效率分析 - 使用全部历史数据
    print("⏱️ 生成效率分析...")
    efficiency_bins = df.withColumn(
        "time_range",
        when(col("generation_time") < 5, "0-5秒")
        .when(col("generation_time") < 10, "5-10秒")
        .when(col("generation_time") < 20, "10-20秒")
        .when(col("generation_time") < 30, "20-30秒")
        .otherwise("30秒以上")
    ).groupBy("time_range").agg(
        count("*").alias("range_count")
    ).withColumn("percentage", round(col("range_count") * 100 / df.count(), 2))
    
    dashboard_data['generation_efficiency'] = efficiency_bins
    
    print("✅ 运营端仪表盘数据生成完成")
    return dashboard_data

def generate_user_recommendations(df, user_profiles, recommendation_models):
    """生成用户端个性化推荐数据"""
    user_recommendations = {}
    
    try:
        # 1. 个性化风格推荐
        print("🎯 生成个性化风格推荐...")
        
        all_user_recommendations = []
        
        # 为每个用户分群生成推荐
        for cluster_id in range(4):
            if f'als_cluster_{cluster_id}' in recommendation_models:
                cluster_model = recommendation_models[f'als_cluster_{cluster_id}']
                als_model = cluster_model['model']
                cluster_data = cluster_model['cluster_data']
                
                # 为群组内用户生成推荐
                user_recs = als_model.recommendForAllUsers(5)
                
                # 转换推荐结果
                user_indexer_model = cluster_model['indexer'].stages[0]
                style_indexer_model = cluster_model['indexer'].stages[1]
                
                # 获取用户ID映射
                user_mapping = cluster_data.select("user_id", "user_id_numeric").distinct()
                style_mapping = cluster_data.select("style", "style_index_numeric").distinct()
                
                # 展开推荐结果
                user_recs_expanded = user_recs.select(
                    "user_id_numeric",
                    explode("recommendations").alias("rec")
                ).select(
                    "user_id_numeric",
                    col("rec.style_index_numeric").alias("style_index_numeric"),
                    col("rec.rating").alias("recommendation_score")
                )
                
                # 关联回实际用户ID和风格名称
                user_recs_final = user_recs_expanded \
                    .join(user_mapping, "user_id_numeric") \
                    .join(style_mapping, "style_index_numeric") \
                    .select(
                        "user_id",
                        "style",
                        "recommendation_score"
                    ).withColumn("reason", lit(f"同类型用户偏好"))
                
                all_user_recommendations.append(user_recs_final)
        
        # 合并所有分群的推荐结果
        if all_user_recommendations:
            personalized_recommendations = all_user_recommendations[0]
            for rec_df in all_user_recommendations[1:]:
                personalized_recommendations = personalized_recommendations.union(rec_df)
            
            user_recommendations['style_recommendations'] = personalized_recommendations
        
        # 2. 用户热门关键词
        print("🔑 生成用户关键词偏好...")
        user_keyword_prefs = df.groupBy("user_id", "keywords").agg(
            count("*").alias("usage_count")
        ).filter(col("keywords").isNotNull() & (size(col("keywords")) > 0)) \
         .select("user_id", explode("keywords").alias("keyword")) \
         .groupBy("user_id", "keyword").agg(
             count("*").alias("usage_count")
         ).withColumn("preference_score", col("usage_count") * 1.0) \
         .orderBy("user_id", col("preference_score").desc())
        
        user_recommendations['keyword_preferences'] = user_keyword_prefs
        
        print("✅ 用户端推荐数据生成完成")
        
    except Exception as e:
        print(f"❌ 用户推荐生成失败: {e}")
        import traceback
        traceback.print_exc()
    
    return user_recommendations

def extract_popular_keywords(df):
    """提取热门关键词 - 支持中英文"""
    try:
        # 方法1: 使用现有的keywords列（中文数据）
        chinese_keywords_df = df.filter(col("keywords").isNotNull() & (size(col("keywords")) > 0))
        
        # 方法2: 为英文数据从prompt生成关键词
        english_prompts_df = df.filter(
            (col("keywords").isNull() | (size(col("keywords")) == 0)) & 
            col("prompt").isNotNull()
        )
        
        print(f"📝 中文关键词数据: {chinese_keywords_df.count()} 条")
        print(f"📝 英文提示词数据: {english_prompts_df.count()} 条")
        
        all_keywords_dfs = []
        
        # 处理中文关键词
        if chinese_keywords_df.count() > 0:
            chinese_keywords = chinese_keywords_df.select(
                "user_id", "style", "user_rating",
                explode(col("keywords")).alias("keyword")
            ).filter(col("keyword").isNotNull() & (col("keyword") != ""))
            all_keywords_dfs.append(chinese_keywords)
        
        # 为英文提示词生成关键词
        if english_prompts_df.count() > 0:
            from pyspark.sql.functions import split, lower, regexp_replace, length
            
            english_keywords = english_prompts_df.select(
                "user_id", "style", "user_rating",
                explode(
                    split(
                        regexp_replace(
                            lower(regexp_replace(col("prompt"), r'[^\w\s]', ' ')), 
                        r'\s+', ' '),
                    ' ')
                ).alias("keyword")
            ).filter(
                (col("keyword") != "") & 
                (length(col("keyword")) > 2) &  # 过滤掉太短的词
                (~col("keyword").rlike(r'^\d+$'))  # 过滤掉纯数字
            )
            all_keywords_dfs.append(english_keywords)
        
        # 合并所有关键词
        if not all_keywords_dfs:
            print("⚠️ 没有可提取的关键词数据")
            # 直接创建空DataFrame，不使用get_keywords_schema函数
            from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
            schema = StructType([
                StructField("keyword", StringType(), True),
                StructField("style", StringType(), True),
                StructField("usage_count", IntegerType(), True),
                StructField("avg_rating", DoubleType(), True),
                StructField("avg_rating", IntegerType(), True),
                StructField("hot_score", DoubleType(), True)
            ])
            return df.sql_ctx.sparkSession.createDataFrame([], schema)
        
        if len(all_keywords_dfs) == 1:
            keywords_df = all_keywords_dfs[0]
        else:
            keywords_df = all_keywords_dfs[0].union(all_keywords_dfs[1])
        
        print(f"🔑 总关键词数量: {keywords_df.count()}")
        
        # 过滤常见英文停用词
        english_stopwords = ["the", "and", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "this", "that", "these", "those", "it", "its", "they", "them", "their", "what", "which", "who", "whom", "where", "when", "why", "how","his","her"]
        
        keywords_filtered = keywords_df.filter(~lower(col("keyword")).isin(english_stopwords))
        
        print(f"🔑 过滤后关键词数量: {keywords_filtered.count()}")
        
        if keywords_filtered.count() == 0:
            print("⚠️ 过滤后没有有效关键词")
            from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
            schema = StructType([
                StructField("keyword", StringType(), True),
                StructField("style", StringType(), True),
                StructField("usage_count", IntegerType(), True),
                StructField("avg_rating", DoubleType(), True),
                StructField("unique_users", IntegerType(), True),
                StructField("hot_score", DoubleType(), True)
            ])
            return df.sql_ctx.sparkSession.createDataFrame([], schema)
        
        # 计算关键词热度
        keyword_popularity = keywords_filtered.groupBy("keyword", "style").agg(
            count("*").alias("usage_count"),
            avg("user_rating").alias("avg_rating"),
            countDistinct("user_id").alias("unique_users")
        ).withColumn("hot_score",
                   col("usage_count") * 0.5 +
                   col("avg_rating") * 0.4 +
                   col("unique_users") * 0.1)
        
        # 显示热门关键词样本
        if keyword_popularity.count() > 0:
            print("🔥 热门英文关键词样本:")
            keyword_popularity.orderBy(col("hot_score").desc()).select(
                "keyword", "style", "hot_score"
            ).show(10, truncate=False)
        
        return keyword_popularity
        
    except Exception as e:
        print(f"❌ 关键词提取失败: {e}")
        import traceback
        traceback.print_exc()
        # 直接创建空DataFrame
        from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
        schema = StructType([
            StructField("keyword", StringType(), True),
            StructField("style", StringType(), True),
            StructField("usage_count", IntegerType(), True),
            StructField("avg_rating", DoubleType(), True),
            StructField("unique_users", IntegerType(), True),
            StructField("hot_score", DoubleType(), True)
        ])
        return df.sql_ctx.sparkSession.createDataFrame([], schema)


    return user_profiles


def load_mysql_jdbc_config():
    """Load analytics-output JDBC settings without supplying credential defaults."""
    names = ("SPARK_MYSQL_JDBC_URL", "SPARK_MYSQL_USER", "SPARK_MYSQL_PASSWORD")
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing required Spark MySQL settings: " + ", ".join(missing))
    return os.environ["SPARK_MYSQL_JDBC_URL"], {
        "user": os.environ["SPARK_MYSQL_USER"],
        "password": os.environ["SPARK_MYSQL_PASSWORD"],
        "driver": "com.mysql.cj.jdbc.Driver",
    }


def save_results_to_mysql(spark, dashboard_data, user_recommendations, user_profiles, enhanced_df):
    """保存结果到MySQL的aigc_platform数据库"""
    
    mysql_url, mysql_properties = load_mysql_jdbc_config()
    
    try:
        print("💾 开始保存数据到MySQL aigc_platform数据库...")
        
        # 1. 保存运营端仪表盘数据
        # 用户画像仪表盘数据
        if 'age_distribution' in dashboard_data:
            dashboard_data['age_distribution'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_age_distribution", properties=mysql_properties)
            print("✅ 年龄分布数据保存完成")
        
        if 'gender_distribution' in dashboard_data:
            dashboard_data['gender_distribution'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_gender_distribution", properties=mysql_properties)
            print("✅ 性别分布数据保存完成")
        
        if 'active_period_distribution' in dashboard_data:
            dashboard_data['active_period_distribution'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_active_period_distribution", properties=mysql_properties)
            print("✅ 活跃时段分布数据保存完成")
        
        # 近7天用户行为分析
        if 'recent_behavior' in dashboard_data:
            dashboard_data['recent_behavior'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_behavior_7days", properties=mysql_properties)
            print("✅ 7天用户行为数据保存完成")
        
        # 风格热度排行
        if 'style_popularity' in dashboard_data:
            dashboard_data['style_popularity'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "style_popularity_30days", properties=mysql_properties)
            print("✅ 风格热度排行数据保存完成")
        
        # 30日风格趋势
        if 'style_trend' in dashboard_data:
            dashboard_data['style_trend'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "style_trend_30days", properties=mysql_properties)
            print("✅ 30日风格趋势数据保存完成")
        
        # 用户满意度分布
        if 'rating_distribution' in dashboard_data:
            dashboard_data['rating_distribution'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "rating_distribution", properties=mysql_properties)
            print("✅ 评分分布数据保存完成")
        
        # 热门关键词分析
        if 'keyword_analysis' in dashboard_data:
            dashboard_data['keyword_analysis'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "keyword_analysis", properties=mysql_properties)
            print("✅ 关键词分析数据保存完成")
        
        # 生成效率分析
        if 'generation_efficiency' in dashboard_data:
            dashboard_data['generation_efficiency'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "generation_efficiency", properties=mysql_properties)
            print("✅ 生成效率数据保存完成")
        
        # 2. 保存用户端推荐数据
        if 'style_recommendations' in user_recommendations:
            user_recommendations['style_recommendations'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_style_recommendations", properties=mysql_properties)
            print("✅ 用户风格推荐数据保存完成")
        
        if 'keyword_preferences' in user_recommendations:
            user_recommendations['keyword_preferences'].write \
                .mode("overwrite") \
                .jdbc(mysql_url, "user_keyword_preferences", properties=mysql_properties)
            print("✅ 用户关键词偏好数据保存完成")
        
        # 3. 保存用户画像详情（用于后续分析）
        user_profiles.select(
            "user_id", "total_generations", "avg_generation_time", 
            "avg_content_length", "avg_rating", "avg_prompt_length",
            "style_diversity", "avg_age", "gender_ratio", "total_downloads",
            "age_range", "active_period", "user_cluster", "user_type", "last_active"
        ).write.mode("overwrite") \
         .jdbc(mysql_url, "user_profiles", properties=mysql_properties)
        print("✅ 用户画像数据保存完成")
        
        print("🎉 所有数据成功保存到MySQL aigc_platform数据库!")
        
        # 验证数据 - 显示各表记录数
        print("\n📊 数据保存统计:")
        table_records = {
            "user_age_distribution": dashboard_data.get('age_distribution'),
            "user_gender_distribution": dashboard_data.get('gender_distribution'),
            "user_active_period_distribution": dashboard_data.get('active_period_distribution'),
            "user_behavior_7days": dashboard_data.get('recent_behavior'),
            "style_popularity_30days": dashboard_data.get('style_popularity'),
            "style_trend_30days": dashboard_data.get('style_trend'),
            "rating_distribution": dashboard_data.get('rating_distribution'),
            "keyword_analysis": dashboard_data.get('keyword_analysis'),
            "generation_efficiency": dashboard_data.get('generation_efficiency'),
            "user_style_recommendations": user_recommendations.get('style_recommendations'),
            "user_keyword_preferences": user_recommendations.get('keyword_preferences'),
            "user_profiles": user_profiles
        }
        
        for table_name, data in table_records.items():
            if data is not None:
                try:
                    count = data.count()
                    print(f"  {table_name}: {count} 条记录")
                except:
                    print(f"  {table_name}: 无法统计记录数")
        
    except Exception as e:
        print(f"❌ 保存到MySQL失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
