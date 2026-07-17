#!/usr/bin/env python3
import os
import sys
try:
    from pyhive import hive
except ImportError:
    hive = None
import pandas as pd
from datetime import datetime, timedelta
import logging
try:
    from config import load_settings
except ImportError:
    from backend.config import load_settings

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(backend_dir)
sys.path.append(project_root)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HiveService:
    def __init__(self, host=None, port=None, username=None, database=None, settings=None):
        settings = settings or load_settings()
        self.host = host or settings.hive_host
        self.port = port or settings.hive_port
        self.username = username or settings.hive_username
        self.database = database or settings.hive_database
        self.connection = None

    def connect(self):
        """连接Hive数据库"""
        try:
            if hive is None:
                logger.error("PyHive is not installed")
                return False
            self.connection = hive.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                database=self.database
            )
            logger.info("✅ Hive连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ Hive连接失败: {e}")
            return False

    def execute_query(self, query, return_df=True):
        """执行Hive查询"""
        try:
            if not self.connection:
                if not self.connect():
                    return None
        
            cursor = self.connection.cursor()
        
            # 添加这些关键的MapReduce配置
            cursor.execute("SET mapreduce.job.classpath=/usr/local/hadoop/share/hadoop/mapreduce/*:/usr/local/hadoop/share/hadoop/mapreduce/lib/*:/usr/local/hadoop/share/hadoop/common/*:/usr/local/hadoop/share/hadoop/common/lib/*:/usr/local/hadoop/share/hadoop/hdfs/*:/usr/local/hadoop/share/hadoop/hdfs/lib/*:/usr/local/hadoop/share/hadoop/yarn/*:/usr/local/hadoop/share/hadoop/yarn/lib/*")
        
            cursor.execute("SET mapreduce.application.classpath=/usr/local/hadoop/share/hadoop/mapreduce/*:/usr/local/hadoop/share/hadoop/mapreduce/lib/*:/usr/local/hadoop/share/hadoop/common/*:/usr/local/hadoop/share/hadoop/common/lib/*:/usr/local/hadoop/share/hadoop/hdfs/*:/usr/local/hadoop/share/hadoop/hdfs/lib/*:/usr/local/hadoop/share/hadoop/yarn/*:/usr/local/hadoop/share/hadoop/yarn/lib/*")
        
            # 内存配置
            cursor.execute("SET mapreduce.map.memory.mb=512")
            cursor.execute("SET mapreduce.reduce.memory.mb=512")
            cursor.execute("SET yarn.app.mapreduce.am.resource.mb=512")
        
            cursor.execute("SET mapreduce.framework.name=yarn")
            cursor.execute("SET mapred.job.tracker=yarn")
        
            cursor.execute(query)

            if return_df:
                # 获取列名（去除反引号，确保后续处理列名一致）
                columns = [desc[0].strip('`') for desc in cursor.description]
                # 获取数据
                data = cursor.fetchall()
                if data:
                    df = pd.DataFrame(data, columns=columns)
                    return df
                else:
                    return pd.DataFrame(columns=columns)
            else:
                return cursor.fetchall()
            
        except Exception as e:
            logger.error(f"❌ Hive查询执行失败: {e}")
            logger.error(f"查询语句: {query}")
            return None

    def add_backticks_to_fields(self, fields):
        """
        通用函数：给字段列表中的每个字段名自动加反引号，规避Hive关键字冲突
        :param fields: 原始字段名列表（如 ["timestamp", "prompt"]）
        :return: 带反引号的字段字符串（如 "`timestamp`, `prompt`"）
        """
        if not isinstance(fields, list) or len(fields) == 0:
            return ""
        # 遍历字段，给每个字段包裹反引号，再用逗号连接
        quoted_fields = [f"`{field}`" for field in fields]
        return ", ".join(quoted_fields)

    def get_user_history(self, user_id):
        """获取用户历史记录（使用通用加反引号函数）"""
        try:
            if not self.connect():
                print(f"⚠️ Hive连接失败，使用模拟数据 for {user_id}")
                return None
        
            # 1. 定义需要查询的字段列表
            query_fields = [
                "timestamp", "prompt", "style", "image_url", "title",
                "content", "generation_time", "content_length", "captions"
            ]
            # 2. 调用通用函数，自动给所有字段加反引号
            quoted_fields = self.add_backticks_to_fields(query_fields)
        
            # 3. 生成查询语句（条件字段也加反引号）
            query = f"""
            SELECT 
                {quoted_fields}
            FROM `aigc_platform`.`generation_logs` 
            WHERE `user_id` = '{user_id}'
            ORDER BY `timestamp` DESC
            LIMIT 50
            """
        
            print(f"📜 执行查询: {user_id}")
            history_df = self.execute_query(query)
        
            if history_df is not None and not history_df.empty:
                history_data = history_df.to_dict('records')
                print(f"✅ 查询成功，返回 {len(history_data)} 条记录")
                return history_data
            else:
                print(f"ℹ️ 用户 {user_id} 无历史记录")
                return []
            
        except Exception as e:
            print(f"❌ 查询历史记录失败，使用模拟数据: {e}")
            return None
    
    def get_mock_history(self, user_id):
        """生成模拟历史记录数据"""
        import random
        from datetime import datetime, timedelta
        
        if user_id in ["U1001", "user123"]:
            # 真实用户返回空数组（没有历史记录）
            return []
        elif user_id.startswith('U') and user_id[1:].isdigit() and int(user_id[1:]) <= 1000:
            # 模拟用户返回Flickr30K模拟数据
            mock_history = []
            styles = ["realistic", "cinematic", "vibrant", "artistic"]
            
            for i in range(5):
                days_ago = random.randint(1, 30)
                timestamp = (datetime.now() - timedelta(days=days_ago)).isoformat()
                
                mock_history.append({
                    'timestamp': timestamp,
                    'prompt': f'Beautiful landscape with mountains and lakes {i}',
                    'style': random.choice(styles),
                    'image_url': f'/api/flickr/image/{user_id}/sample_{i}.jpg',
                    'title': f'Scenic View {i}',
                    'content': 'This is an AI-generated description of a beautiful landscape.',
                    'generation_time': round(random.uniform(2.0, 8.0), 2),
                    'content_length': 150,
                    'captions': ['A stunning view of nature', 'Peaceful landscape scene']
                })
            
            return mock_history
        else:
            return []
    
    def get_dashboard_stats(self):
        """获取运营面板统计数据（增强版，使用通用加反引号函数）"""
        try:
            # 1. 总生成次数（字段加反引号）
            total_fields = ["event_type"]
            quoted_total_fields = self.add_backticks_to_fields(total_fields)
            total_generations_query = f"""
            SELECT COUNT(*) as `total_generations` 
            FROM `aigc_platform`.`generation_logs` 
            WHERE {quoted_total_fields} = 'generate'
            """
            total_df = self.execute_query(total_generations_query)
            total_generations = total_df['total_generations'].iloc[0] if total_df is not None and not total_df.empty else 0
            
            # 2. 数据来源统计（字段加反引号）
            source_fields = ["event_type", "user_id", "timestamp"]
            quoted_source_fields = self.add_backticks_to_fields(source_fields)
            data_source_query = f"""
            SELECT 
                COUNT(*) as `total_records`,
                COUNT(DISTINCT `user_id`) as `unique_users`,
                MIN(`timestamp`) as `earliest_record`,
                MAX(`timestamp`) as `latest_record`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate'
            """
            source_stats = self.execute_query(data_source_query)
            
            # 3. 活跃用户数（字段加反引号）
            active_fields = ["event_type", "user_id", "timestamp"]
            quoted_active_fields = self.add_backticks_to_fields(active_fields)
            active_users_query = f"""
            SELECT COUNT(DISTINCT `user_id`) as `active_users` 
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `timestamp` >= DATE_SUB(CURRENT_DATE, 7)
            """
            active_df = self.execute_query(active_users_query)
            active_users = active_df['active_users'].iloc[0] if active_df is not None and not active_df.empty else 0
            
            # 4. 平均生成时间（字段加反引号）
            avg_fields = ["event_type", "generation_time"]
            quoted_avg_fields = self.add_backticks_to_fields(avg_fields)
            avg_time_query = f"""
            SELECT AVG(`generation_time`) as `avg_generation_time` 
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `generation_time` > 0
            """
            avg_time_df = self.execute_query(avg_time_query)
            avg_generation_time = round(avg_time_df['avg_generation_time'].iloc[0], 2) if avg_time_df is not None and not avg_time_df.empty else 0
            
            # 5. 最受欢迎的风格（字段加反引号）
            style_fields = ["event_type", "style"]
            quoted_style_fields = self.add_backticks_to_fields(style_fields)
            popular_style_query = f"""
            SELECT `style`, COUNT(*) as `count` 
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `style` IS NOT NULL AND `style` != ''
            GROUP BY `style` 
            ORDER BY `count` DESC 
            LIMIT 1
            """
            style_df = self.execute_query(popular_style_query)
            popular_style = style_df['style'].iloc[0] if style_df is not None and not style_df.empty else "暂无数据"
            
            # 6. 生成成功率（字段加反引号）
            success_fields = ["event_type", "generation_time"]
            quoted_success_fields = self.add_backticks_to_fields(success_fields)
            success_rate_query = f"""
            SELECT 
                ROUND(
                    (SUM(CASE WHEN `generation_time` > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 
                    1
                ) as `success_rate` 
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate'
            """
            success_df = self.execute_query(success_rate_query)
            success_rate = success_df['success_rate'].iloc[0] if success_df is not None and not success_df.empty else 0
            
            stats = {
                'totalGenerations': int(total_generations),
                'activeUsers': int(active_users),
                'avgGenerationTime': avg_generation_time,
                'popularStyle': popular_style,
                'successRate': success_rate,
                'uniqueUsers': int(source_stats['unique_users'].iloc[0]) if source_stats is not None else 0,
                'dataRange': f"{source_stats['earliest_record'].iloc[0] if source_stats is not None else 'N/A'} 至 {source_stats['latest_record'].iloc[0] if source_stats is not None else 'N/A'}"
            }
            
            logger.info(f"📊 获取运营统计数据: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取运营统计数据失败: {e}")
            return None
    
    def get_large_scale_analysis(self):
        """针对大数据集的分析（使用通用加反引号函数）"""
        try:
            # 1. 用户活跃度分层（字段加反引号）
            user_tier_query = f"""
            SELECT 
                CASE 
                    WHEN `generation_count` >= 100 THEN '重度用户'
                    WHEN `generation_count` >= 50 THEN '中度用户' 
                    WHEN `generation_count` >= 10 THEN '轻度用户'
                    ELSE '新用户'
                END as `user_tier`,
                COUNT(*) as `user_count`,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(DISTINCT `user_id`) FROM `aigc_platform`.`generation_logs`), 1) as `percentage`
            FROM (
                SELECT `user_id`, COUNT(*) as `generation_count`
                FROM `aigc_platform`.`generation_logs` 
                WHERE `event_type` = 'generate'
                GROUP BY `user_id`
            ) `user_stats`
            GROUP BY 
                CASE 
                    WHEN `generation_count` >= 100 THEN '重度用户'
                    WHEN `generation_count` >= 50 THEN '中度用户' 
                    WHEN `generation_count` >= 10 THEN '轻度用户'
                    ELSE '新用户'
                END
            ORDER BY `user_count` DESC
            """
            user_tier_df = self.execute_query(user_tier_query)
            
            # 2. 时间段分析（字段加反引号）
            time_analysis_query = f"""
            SELECT 
                HOUR(`timestamp`) as `hour`,
                COUNT(*) as `generation_count`,
                COUNT(DISTINCT `user_id`) as `active_users`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate'
            GROUP BY HOUR(`timestamp`)
            ORDER BY `hour`
            """
            time_analysis_df = self.execute_query(time_analysis_query)
            
            return {
                'userTiers': user_tier_df.to_dict('records') if user_tier_df is not None else [],
                'timeAnalysis': time_analysis_df.to_dict('records') if time_analysis_df is not None else []
            }
            
        except Exception as e:
            logger.error(f"❌ 大规模数据分析失败: {e}")
            return None

    def get_trend_data(self, days=7):
        """获取趋势数据（使用通用加反引号函数）"""
        try:
            trend_query = f"""
            SELECT 
                DATE(`timestamp`) as `date`,
                COUNT(*) as `daily_generations`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `timestamp` >= DATE_SUB(CURRENT_DATE, {days})
            GROUP BY DATE(`timestamp`)
            ORDER BY `date`
            """
            trend_df = self.execute_query(trend_query)
            
            if trend_df is None or trend_df.empty:
                dates = [(datetime.now() - timedelta(days=i)).strftime('%m-%d') for i in range(days-1, -1, -1)]
                values = [0] * days
                return {'labels': dates, 'values': values}
            
            trend_df['date_str'] = trend_df['date'].apply(lambda x: x.strftime('%m-%d') if hasattr(x, 'strftime') else x)
            return {
                'labels': trend_df['date_str'].tolist(),
                'values': trend_df['daily_generations'].tolist()
            }
            
        except Exception as e:
            logger.error(f"❌ 获取趋势数据失败: {e}")
            return None
    
    def get_hot_keywords(self, limit=10):
        """获取热门关键词（使用通用加反引号函数）"""
        try:
            # 字段加反引号
            keywords_query = f"""
            SELECT 
                `prompt`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `prompt` IS NOT NULL
            LIMIT 100
            """
            prompts_df = self.execute_query(keywords_query)
            
            if prompts_df is None or prompts_df.empty:
                return []
            
            from collections import Counter
            import re
            all_words = []
            for prompt in prompts_df['prompt']:
                words = re.findall(r'[\u4e00-\u9fa5]{2,}', str(prompt))
                all_words.extend(words)
            
            word_counter = Counter(all_words)
            hot_keywords = []
            for word, count in word_counter.most_common(limit):
                hot_keywords.append({
                    'word': word,
                    'count': count,
                    'trend': '→',
                    'change': 0
                })
            return hot_keywords
            
        except Exception as e:
            logger.error(f"❌ 获取热门关键词失败: {e}")
            return []
    
    def get_style_distribution(self):
        """获取风格分布（使用通用加反引号函数）"""
        try:
            style_query = f"""
            SELECT 
                `style`,
                COUNT(*) as `count`,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM `aigc_platform`.`generation_logs` WHERE `event_type` = 'generate'), 1) as `percentage`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate' 
            AND `style` IS NOT NULL AND `style` != ''
            GROUP BY `style`
            ORDER BY `count` DESC
            LIMIT 8
            """
            style_df = self.execute_query(style_query)
            
            if style_df is None or style_df.empty:
                return []
            return style_df.to_dict('records')
            
        except Exception as e:
            logger.error(f"❌ 获取风格分布失败: {e}")
            return []
    
    def get_user_activities(self, limit=10):
        """获取用户活跃度（使用通用加反引号函数）"""
        try:
            user_activity_query = f"""
            SELECT 
                `user_id`,
                COUNT(*) as `generation_count`,
                MAX(`timestamp`) as `last_active`
            FROM `aigc_platform`.`generation_logs` 
            WHERE `event_type` = 'generate'
            GROUP BY `user_id`
            ORDER BY `generation_count` DESC
            LIMIT {limit}
            """
            activity_df = self.execute_query(user_activity_query)
            
            if activity_df is None or activity_df.empty:
                return []
            
            user_activities = []
            for _, row in activity_df.iterrows():
                last_active = row['last_active']
                if pd.isna(last_active):
                    last_active_desc = '从未活跃'
                else:
                    if isinstance(last_active, str):
                        last_active = pd.to_datetime(last_active)
                    days_ago = (datetime.now() - last_active).days
                    if days_ago == 0:
                        last_active_desc = '今天'
                    elif days_ago == 1:
                        last_active_desc = '1天前'
                    else:
                        last_active_desc = f'{days_ago}天前'
                
                user_activities.append({
                    'userId': row['user_id'],
                    'username': row['user_id'].replace('U', '用户'),
                    'generationCount': int(row['generation_count']),
                    'lastActive': last_active_desc,
                    'preferredStyle': '待分析'
                })
            return user_activities
            
        except Exception as e:
            logger.error(f"❌ 获取用户活跃度失败: {e}")
            return []
    
    def get_personalized_recommendations(self, user_id, limit=10):
        """获取个性化推荐"""
        try:
            # 1. 基于用户历史的风格推荐
            style_rec_query = f"""
            SELECT `style`, `popularity_score` 
            FROM `aigc_platform`.`popular_styles` 
            WHERE `style` NOT IN (
                SELECT DISTINCT `style` FROM `aigc_platform`.`enhanced_generation_logs` 
                WHERE `user_id` = '{user_id}'
            )
            ORDER BY `popularity_score` DESC 
            LIMIT {limit}
            """
            style_recommendations = self.execute_query(style_rec_query)
            
            # 2. 热门关键词推荐
            keyword_rec_query = f"""
            SELECT `keyword`, `style`, `hot_score`
            FROM `aigc_platform`.`keyword_recommendations`
            ORDER BY `hot_score` DESC
            LIMIT {limit}
            """
            keyword_recommendations = self.execute_query(keyword_rec_query)
            
            # 3. 相似用户喜欢的风格
            similar_users_query = f"""
            SELECT `preferred_styles`, `user_type`
            FROM `aigc_platform`.`user_profiles_enhanced`
            WHERE `user_id` = '{user_id}'
            """
            user_profile = self.execute_query(similar_users_query)
            
            recommendations = {
                'style_recommendations': style_recommendations.to_dict('records') if style_recommendations is not None else [],
                'keyword_recommendations': keyword_recommendations.to_dict('records') if keyword_recommendations is not None else [],
                'user_type': user_profile['user_type'].iloc[0] if user_profile is not None and not user_profile.empty else 'new_user'
            }
            
            return recommendations
            
        except Exception as e:
            logger.error(f"❌ 获取个性化推荐失败: {e}")
            return None
    
    def get_trending_analysis_dashboard(self):
        """获取运营端趋势分析数据"""
        try:
            dashboard_data = {}
            
            # 1. 风格分布饼图数据
            style_pie_query = """
            SELECT `style` as `name`, `count` as `value`, `percentage`
            FROM `aigc_platform`.`style_distribution`
            ORDER BY `count` DESC
            LIMIT 10
            """
            style_pie_data = self.execute_query(style_pie_query)
            dashboard_data['style_distribution'] = style_pie_data.to_dict('records') if style_pie_data is not None else []
            
            # 2. 时间趋势折线图数据
            trend_line_query = """
            SELECT `date`, `style`, `daily_count` as `value`
            FROM `aigc_platform`.`time_trends`
            WHERE `date` >= DATE_SUB(CURRENT_DATE, 30)
            ORDER BY `date`
            """
            trend_line_data = self.execute_query(trend_line_query)
            dashboard_data['time_trends'] = self.process_trend_data(trend_line_data)
            
            # 3. 用户行为柱形图数据
            user_behavior_query = """
            SELECT 
                CASE `age_range`
                    WHEN 0 THEN '未知'
                    WHEN 1 THEN '<18'
                    WHEN 2 THEN '18-24'
                    WHEN 3 THEN '25-29'
                    WHEN 4 THEN '30-34'
                    WHEN 5 THEN '35-39'
                    WHEN 6 THEN '40-49'
                    ELSE '50+'
                END as `age_group`,
                CASE `gender`
                    WHEN 0 THEN '女性'
                    WHEN 1 THEN '男性'
                    ELSE '未知'
                END as `gender`,
                `generation_count` as `count`,
                `avg_satisfaction` as `satisfaction`
            FROM `aigc_platform`.`user_behavior`
            ORDER BY `generation_count` DESC
            """
            user_behavior_data = self.execute_query(user_behavior_query)
            dashboard_data['user_behavior'] = user_behavior_data.to_dict('records') if user_behavior_data is not None else []
            
            # 4. 内容质量分析
            content_quality_query = """
            SELECT `content_quality` as `quality`, `count`, `avg_satisfaction`
            FROM `aigc_platform`.`content_quality`
            ORDER BY `count` DESC
            """
            content_quality_data = self.execute_query(content_quality_query)
            dashboard_data['content_quality'] = content_quality_data.to_dict('records') if content_quality_data is not None else []
            
            # 5. 热门关键词词云数据
            keyword_cloud_query = """
            SELECT `keyword`, `hot_score` as `value`
            FROM `aigc_platform`.`keyword_recommendations`
            ORDER BY `hot_score` DESC
            LIMIT 50
            """
            keyword_cloud_data = self.execute_query(keyword_cloud_query)
            dashboard_data['keyword_cloud'] = keyword_cloud_data.to_dict('records') if keyword_cloud_data is not None else []
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"❌ 获取趋势分析数据失败: {e}")
            return None
    
    def process_trend_data(self, trend_df):
        """处理趋势数据为前端需要的格式"""
        if trend_df is None or trend_df.empty:
            return {'labels': [], 'datasets': []}
        
        # 按风格分组数据
        styles = trend_df['style'].unique()
        datasets = []
        
        for style in styles:
            style_data = trend_df[trend_df['style'] == style]
            datasets.append({
                'label': style,
                'data': style_data['value'].tolist(),
                'dates': style_data['date'].tolist()
            })
        
        # 获取所有日期作为x轴标签
        all_dates = sorted(trend_df['date'].unique())
        
        return {
            'labels': all_dates,
            'datasets': datasets
        }
    
    
    def get_trending_recommendations(self, limit=8):
        """获取热门推荐（用户端）"""
        try:
            # 热门风格推荐
            popular_styles_query = f"""
            SELECT `style`, `popularity_score`, `avg_satisfaction`
            FROM `aigc_platform`.`popular_styles`
            ORDER BY `popularity_score` DESC
            LIMIT {limit}
            """
            popular_styles = self.execute_query(popular_styles_query)
            
            # 热门关键词推荐
            popular_keywords_query = f"""
            SELECT `keyword`, `style`, `hot_score`
            FROM `aigc_platform`.`keyword_recommendations`
            ORDER BY `hot_score` DESC
            LIMIT {limit}
            """
            popular_keywords = self.execute_query(popular_keywords_query)
            
            trending_data = {
                'popular_styles': popular_styles.to_dict('records') if popular_styles is not None else [],
                'popular_keywords': popular_keywords.to_dict('records') if popular_keywords is not None else []
            }
            
            return trending_data
            
        except Exception as e:
            logger.error(f"❌ 获取热门推荐失败: {e}")
            return {
                'popular_styles': [
                    {'style': '赛博朋克', 'popularity_score': 95, 'avg_satisfaction': 4.5},
                    {'style': '水彩画风', 'popularity_score': 88, 'avg_satisfaction': 4.3},
                    {'style': '电影感', 'popularity_score': 82, 'avg_satisfaction': 4.2}
                ],
                'popular_keywords': [
                    {'keyword': '夏日', 'style': '清新', 'hot_score': 92},
                    {'keyword': '星空', 'style': '浪漫', 'hot_score': 87},
                    {'keyword': '未来城市', 'style': '赛博朋克', 'hot_score': 85}
                ]
            }
    
    def close(self):
        """关闭连接"""
        if self.connection:
            self.connection.close()
            logger.info("✅ Hive连接已关闭")

# 创建全局实例
hive_service = HiveService()
