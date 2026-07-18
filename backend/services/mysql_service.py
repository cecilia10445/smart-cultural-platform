#!/usr/bin/env python3
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
import logging
try:
    import pymysql
except ImportError:
    pymysql = None
from typing import List, Dict, Any, Optional
import json
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

class MySQLService:
    def __init__(self, host=None, port=None, username=None, password=None, database=None, settings=None):
        settings = settings or load_settings()
        self.host = host or settings.mysql_host
        self.port = port or settings.mysql_port
        self.username = username or settings.mysql_user
        self.password = password if password is not None else settings.mysql_password
        self.database = database or settings.mysql_database
        self.connection = None
        self.last_connect_time = 0
        self.connect_timeout = settings.mysql_connect_timeout_seconds

    def connect(self):
        """连接MySQL数据库 - 现在只用于检查连接是否可用"""
        test_connection = None
        try:
            if pymysql is None:
                logger.error("PyMySQL is not installed")
                return False
            # 测试连接是否可用
            test_connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=self.connect_timeout,
                read_timeout=load_settings().mysql_read_timeout_seconds,
                write_timeout=load_settings().mysql_write_timeout_seconds,
            )
            
            # 测试连接
            with test_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            logger.info("✅ MySQL连接测试成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ MySQL连接测试失败: {e}")
            return False
        finally:
            if test_connection:
                test_connection.close()

    def execute_insert(self, query, params=None, max_retries=2):
        """Execute one INSERT and return its generated primary key."""
        if pymysql is None:
            logger.error("MySQL insert failed: PyMySQL is not installed")
            return None

        transient_error_codes = {2006, 2013, 2055}
        for attempt in range(max_retries + 1):
            connection = None
            try:
                settings = load_settings()
                connection = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.username,
                    password=self.password,
                    database=self.database,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=True,
                    connect_timeout=self.connect_timeout,
                    read_timeout=settings.mysql_read_timeout_seconds,
                    write_timeout=settings.mysql_write_timeout_seconds,
                )
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    return cursor.lastrowid
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as error:
                error_code = error.args[0] if error.args else 0
                if error_code not in transient_error_codes or attempt >= max_retries:
                    logger.error("MySQL insert failed (code=%s)", error_code)
                    return None
                logger.warning(
                    "Transient MySQL insert failure; retrying (code=%s, attempt=%s/%s)",
                    error_code,
                    attempt + 1,
                    max_retries + 1,
                )
                time.sleep(1)
            except Exception as error:
                error_code = error.args[0] if error.args and isinstance(error.args[0], int) else "unknown"
                logger.error("MySQL insert failed (code=%s)", error_code)
                return None
            finally:
                if connection:
                    connection.close()

        return None

    def execute_query(self, query, params=None, max_retries=2):
        """执行MySQL查询，每次创建新连接避免竞争"""
        connection = None
        if pymysql is None:
            logger.error("PyMySQL is not installed")
            return None
        for attempt in range(max_retries + 1):
            try:
                # 每次都创建新连接，避免连接复用问题
                connection = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.username,
                    password=self.password,
                    database=self.database,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=True,
                    connect_timeout=self.connect_timeout,
                    read_timeout=load_settings().mysql_read_timeout_seconds,
                    write_timeout=load_settings().mysql_write_timeout_seconds,
                )
                
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    if query.strip().upper().startswith('SELECT'):
                        result = cursor.fetchall()
                    else:
                        result = cursor.rowcount
                    
                    return result
                    
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
                error_code = e.args[0] if e.args else 0
                
                # 如果是连接相关的错误
                if error_code in (2006, 2013, 2055):  # MySQL连接错误代码
                    logger.warning(f"⚠️ MySQL连接错误 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                else:
                    logger.warning(f"⚠️ MySQL操作错误 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                    
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"❌ MySQL查询执行失败: {e}")
                    return None
                    
            except Exception as e:
                logger.error("❌ MySQL查询执行失败 (type=%s)", type(e).__name__)
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None
            finally:
                if connection:
                    connection.close()
                
        return None

    def check_connection_health(self):
        """检查连接健康状态 - 现在总是返回True，因为每次查询都新建连接"""
        return True  # 由于每次查询都新建连接，健康检查不再必要

    def get_user_history(self, user_id):
        """直接获取用户历史记录，简化逻辑"""
        try:
            # 直接查询generation_logs表，不检查表是否存在
            history_query = """
            SELECT 
                timestamp,
                prompt,
                style,
                image_url,
                title,
                content,
                generation_time,
                content_length,
                user_rating,
                download_count,
                user_age,
                user_gender
            FROM generation_logs 
            WHERE user_id = %s AND event_type = 'generate'  # 关键修改：只查询生成记录
            ORDER BY timestamp DESC
            LIMIT 50
            """
            
            history_result = self.execute_query(history_query, (user_id,))
            
            if history_result is None:
                logger.warning(f"⚠️ 用户 {user_id} 历史记录查询返回None")
                return None
            
            if not history_result:
                logger.info(f"ℹ️ 用户 {user_id} 暂无历史记录")
                return []
            
            # 处理longtext字段和类型转换
            processed_history = []
            for item in history_result:
                try:
                    # 处理timestamp字段
                    timestamp = item['timestamp']
                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    # 处理数值字段，添加更健壮的类型检查
                    generation_time = 0
                    if item['generation_time'] is not None:
                        try:
                            generation_time = float(item['generation_time'])
                        except (ValueError, TypeError):
                            generation_time = 0
                    
                    content_length = 0
                    if item['content_length'] is not None:
                        try:
                            content_length = int(item['content_length'])
                        except (ValueError, TypeError):
                            content_length = 0
                    
                    user_rating = None
                    if item['user_rating'] is not None:
                        try:
                            user_rating = float(item['user_rating'])
                        except (ValueError, TypeError):
                            user_rating = None
                    
                    download_count = 0
                    if item['download_count'] is not None:
                        try:
                            download_count = int(item['download_count'])
                        except (ValueError, TypeError):
                            download_count = 0
                    
                    user_age = None
                    if item['user_age'] is not None:
                        try:
                            user_age = int(item['user_age'])
                        except (ValueError, TypeError):
                            user_age = None
                    
                    user_gender = None
                    if item['user_gender'] is not None:
                        try:
                            user_gender = int(item['user_gender'])
                        except (ValueError, TypeError):
                            user_gender = None
                    
                    processed_item = {
                        'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                        'prompt': str(item['prompt']) if item['prompt'] else '',
                        'style': str(item['style']) if item['style'] else '通用',
                        'image_url': str(item['image_url']) if item['image_url'] else '',
                        'title': str(item['title']) if item['title'] else '',
                        'content': str(item['content']) if item['content'] else '',
                        'generation_time': generation_time,
                        'content_length': content_length,
                        'user_rating': user_rating,
                        'download_count': download_count,
                        'user_age': user_age,
                        'user_gender': user_gender
                    }
                    processed_history.append(processed_item)
                except Exception as e:
                    logger.error(f"❌ 处理历史记录项时出错: {e}")
                    continue
            
            logger.info(f"✅ 成功获取用户 {user_id} 的历史记录，共 {len(processed_history)} 条")
            return processed_history
            
        except Exception as e:
            logger.error(f"❌ 从MySQL获取用户历史记录失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_user_profile_dashboard(self, start_date=None, end_date=None):
        """获取用户画像仪表盘数据"""
        try:
            dashboard_data = {}
            
            # 构建日期条件 - 只对有日期字段的表使用
            date_condition = ""
            date_params = ()
            if start_date and end_date:
                date_condition = " WHERE stat_date BETWEEN %s AND %s"
                date_params = (start_date, end_date)
            
            # 1. 年龄分布 - 静态数据，不需要日期条件 ✅
            age_query = """
            SELECT 
                age_range,
                age_count as count
            FROM user_age_distribution 
            ORDER BY age_range
            """
            
            age_result = self.execute_query(age_query)
            
            # 计算百分比
            total_age_count = sum([item['count'] for item in age_result]) if age_result else 1
            
            age_range_mapping = {
                0: '未知',
                1: '18岁以下', 
                2: '18-24岁',
                3: '25-29岁',
                4: '30-34岁', 
                5: '35-39岁',
                6: '40-49岁',
                7: '50岁以上'
            }
            
            dashboard_data['age_distribution'] = [
                {
                    'age_range': age_range_mapping.get(item['age_range'], f'分段{item["age_range"]}'),
                    'count': int(item['count']),
                    'percentage': round(float(item['count']) / total_age_count * 100, 2)
                }
                for item in age_result
            ] if age_result else []

            # 2. 性别比例 - 静态数据，不需要日期条件 ✅
            gender_query = """
            SELECT 
                gender_category,
                gender_count as count
            FROM user_gender_distribution 
            ORDER BY gender_category
            """
            
            gender_result = self.execute_query(gender_query)
            
            # 计算百分比
            total_gender_count = sum([item['count'] for item in gender_result]) if gender_result else 1
            
            gender_mapping = {
                0: 'female',
                1: 'male', 
                2: 'unknown'
            }
            
            dashboard_data['gender_distribution'] = [
                {
                    'gender': gender_mapping.get(item['gender_category'], 'unknown'),
                    'count': int(item['count']),
                    'percentage': round(float(item['count']) / total_gender_count * 100, 2)
                }
                for item in gender_result
            ] if gender_result else []

            # 3. 活跃时间段分布 - 静态数据，不需要日期条件 ✅
            active_period_query = """
            SELECT 
                active_period,
                period_count as count
            FROM user_active_period_distribution 
            ORDER BY active_period
            """
            
            period_result = self.execute_query(active_period_query)
            
            # 计算百分比
            total_period_count = sum([item['count'] for item in period_result]) if period_result else 1
            
            period_mapping = {
                0: '深夜党 (0-6点)',
                1: '上午党 (6-12点)', 
                2: '下午党 (12-18点)',
                3: '晚间党 (18-24点)'
            }
            
            dashboard_data['active_period_distribution'] = [
                {
                    'period': period_mapping.get(item['active_period'], f'时段{item["active_period"]}'),
                    'count': int(item['count']),
                    'percentage': round(float(item['count']) / total_period_count * 100, 2)
                }
                for item in period_result
            ] if period_result else []

            # 4. 用户行为分析 - 需要日期条件 ✅ (user_behavior_7days表有stat_date字段)
            if date_condition:
                behavior_query = f"""
                SELECT 
                    stat_date as date,
                    generation_count,
                    download_count,
                    active_users
                FROM user_behavior_7days 
                {date_condition}
                ORDER BY stat_date
                """
            else:
                behavior_query = """
                SELECT 
                    stat_date as date,
                    generation_count,
                    download_count,
                    active_users
                FROM user_behavior_7days 
                ORDER BY stat_date DESC
                LIMIT 7
                """
            
            behavior_result = self.execute_query(behavior_query, date_params if date_condition else None)
            if behavior_result:
                # 如果有日期条件，按日期排序；否则按默认排序
                if date_condition:
                    sorted_result = sorted(behavior_result, key=lambda x: x['date'])
                else:
                    sorted_result = sorted(behavior_result, key=lambda x: x['date'])  # 按日期正序
                
                dashboard_data['user_behavior_7days'] = {
                    'labels': [item['date'].strftime('%m-%d') if hasattr(item['date'], 'strftime') else str(item['date']) for item in sorted_result],
                    'generation_data': [int(item['generation_count']) for item in sorted_result],
                    'download_data': [int(item['download_count']) for item in sorted_result],
                    'active_users': [int(item['active_users']) for item in sorted_result]
                }
            else:
                dashboard_data['user_behavior_7days'] = {
                    'labels': [], 
                    'generation_data': [], 
                    'download_data': [],
                    'active_users': []
                }

            # 5. 风格热度排行TOP10 - 这个表没有stat_date字段，不能使用日期条件 ❌
            style_popularity_query = """
            SELECT 
                style,
                generation_count as usage_count,
                popularity_rank
            FROM style_popularity_30days 
            ORDER BY popularity_rank 
            LIMIT 10
            """
            
            style_result = self.execute_query(style_popularity_query)
            dashboard_data['style_popularity'] = [
                {
                    'style': item['style'],
                    'usage_count': int(item['usage_count']),
                    'rank': int(item['popularity_rank'])
                }
                for item in style_result
            ] if style_result else []

            # 6. 30日风格趋势分析 - 这个表有stat_date字段，可以使用日期条件 ✅
            if date_condition:
                style_trend_query = f"""
                SELECT 
                    stat_date as date,
                    style,
                    daily_count as usage_count
                FROM style_trend_30days 
                {date_condition}
                ORDER BY stat_date, style
                """
            else:
                style_trend_query = """
                SELECT 
                    stat_date as date,
                    style,
                    daily_count as usage_count
                FROM style_trend_30days 
                ORDER BY stat_date DESC 
                LIMIT 90  # 取最近90条确保有足够数据
                """
            
            trend_result = self.execute_query(style_trend_query, date_params if date_condition else None)
            if trend_result:
                # 按日期和风格组织数据
                trend_data = {}
                all_dates = set()
                
                for item in trend_result:
                    date_str = item['date'].strftime('%m-%d') if hasattr(item['date'], 'strftime') else str(item['date'])
                    style = item['style']
                    all_dates.add(date_str)
                    
                    if date_str not in trend_data:
                        trend_data[date_str] = {}
                    trend_data[date_str][style] = int(item['usage_count'])
                
                # 获取TOP5风格
                top_styles = [item['style'] for item in dashboard_data['style_popularity'][:5]]
                
                # 构建趋势数据集
                datasets = []
                sorted_dates = sorted(all_dates)
                
                for style in top_styles:
                    style_data = []
                    for date in sorted_dates:
                        style_data.append(trend_data.get(date, {}).get(style, 0))
                    
                    datasets.append({
                        'label': style,
                        'data': style_data
                    })
                
                dashboard_data['style_trend_30days'] = {
                    'labels': sorted_dates,
                    'datasets': datasets
                }
            else:
                dashboard_data['style_trend_30days'] = {'labels': [], 'datasets': []}

            # 7. 用户满意度评分分布 - 这个表没有stat_date字段，不能使用日期条件 ❌
            rating_query = """
            SELECT 
                rating,
                rating_count as count,
                percentage
            FROM rating_distribution 
            ORDER BY rating
            """
            
            rating_result = self.execute_query(rating_query)
            dashboard_data['rating_distribution'] = [
                {
                    'rating': int(item['rating']) if item['rating'] is not None else 0,
                    'count': int(item['count']),
                    'percentage': float(item['percentage']) if item['percentage'] is not None else 0
                }
                for item in rating_result
            ] if rating_result else []

            # 8. 热门关键词词云及趋势 - 这个表没有stat_date字段，不能使用日期条件 ❌
            keyword_query = """
            SELECT 
                keyword,
                usage_count as frequency,
                trend_data,
                hot_score
            FROM keyword_analysis 
            ORDER BY hot_score DESC 
            LIMIT 10
            """
            
            keyword_result = self.execute_query(keyword_query)
            keyword_data = []
            if keyword_result:
                print(f"从数据库获取到 {len(keyword_result)} 个关键词")
                for item in keyword_result:
                    print(f"处理关键词: {item['keyword']}, 频率: {item['frequency']}")
                    keyword_info = {
                        'keyword': item['keyword'],
                        'frequency': int(item['frequency']),
                        'hot_score': float(item['hot_score']) if item['hot_score'] is not None else 0,
                        'trend': {}
                    }
                    
                    # 解析趋势数据
                    if item['trend_data']:
                        try:
                            trend_str = item['trend_data'].strip()
                            if trend_str.startswith('{') and trend_str.endswith('}'):
                                try:
                                    trend_data = json.loads(trend_str)
                                except json.JSONDecodeError:
                                    trend_str_fixed = trend_str.replace("'", '"')
                                    try:
                                        trend_data = json.loads(trend_str_fixed)
                                    except json.JSONDecodeError:
                                        trend_data = self.parse_trend_data_manually(trend_str)
                            else:
                                # 如果不是标准JSON格式，尝试手动解析
                                trend_data = self.parse_trend_data_manually(trend_str)
                            keyword_info['trend'] = trend_data
                        except Exception as e:
                            logger.warning(f"解析趋势数据失败: {e}")
                            keyword_info['trend'] = {}
                    keyword_data.append(keyword_info)
            
            dashboard_data['hot_keywords'] = keyword_data

            # 9. 生成效率分析 - 这个表没有stat_date字段，不能使用日期条件 ❌
            efficiency_query = """
            SELECT 
                time_range,
                range_count as count,
                percentage
            FROM generation_efficiency 
            ORDER BY time_range
            """
            
            efficiency_result = self.execute_query(efficiency_query)
            dashboard_data['generation_efficiency'] = [
                {
                    'time_range': item['time_range'],
                    'count': int(item['count']),
                    'percentage': float(item['percentage']) if item['percentage'] is not None else 0
                }
                for item in efficiency_result
            ] if efficiency_result else []

            logger.info("✅ 用户画像仪表盘数据获取成功")
            return dashboard_data
            
        except Exception as e:
            logger.error(f"❌ 获取用户画像仪表盘数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_personalized_recommendations(self, user_id, limit=10):
        """获取用户个性化推荐"""
        try:
            # 基于协同过滤的用户风格推荐 - 直接从user_style_recommendations表获取
            style_recommendation_query = """
            SELECT 
                style,
                recommendation_score,
                reason
            FROM user_style_recommendations 
            WHERE user_id = %s 
            ORDER BY recommendation_score DESC 
            LIMIT %s
            """
            
            style_result = self.execute_query(style_recommendation_query, (user_id, limit))
            
            # 用户关键词偏好 - 直接从user_keyword_preferences表获取
            keyword_preference_query = """
            SELECT 
                keyword,
                preference_score,
                usage_count
            FROM user_keyword_preferences 
            WHERE user_id = %s 
            ORDER BY preference_score DESC 
            LIMIT %s
            """
            
            keyword_result = self.execute_query(keyword_preference_query, (user_id, limit))
            
            # 热门关键词（全局） - 直接从keyword_analysis表获取
            hot_keywords_query = """
            SELECT 
                keyword,
                usage_count as frequency,
                hot_score
            FROM keyword_analysis 
            ORDER BY hot_score DESC 
            LIMIT %s
            """
            
            hot_keyword_result = self.execute_query(hot_keywords_query, (limit,))
            
            recommendations = {
                'style_recommendations': [
                    {
                        'style': item['style'],
                        'score': float(item['recommendation_score']) if item['recommendation_score'] is not None else 0,
                        'reason': item['reason']
                    }
                    for item in style_result
                ] if style_result else [],
                
                'personalized_keywords': [
                    {
                        'keyword': item['keyword'],
                        'score': float(item['preference_score']),
                        'usage_count': int(item['usage_count']),
                        'type': '个性化偏好'
                    }
                    for item in keyword_result
                ] if keyword_result else [],
                
                'hot_keywords': [
                    {
                        'keyword': item['keyword'],
                        'frequency': int(item['frequency']),
                        'hot_score': float(item['hot_score']) if item['hot_score'] is not None else 0,
                        'type': '全网热门'
                    }
                    for item in hot_keyword_result
                ] if hot_keyword_result else []
            }
            
            logger.info(f"✅ 用户 {user_id} 个性化推荐获取成功")
            return recommendations
            
        except Exception as e:
            logger.error(f"❌ 获取用户个性化推荐失败: {e}")
            return None

    def get_dashboard_stats(self, start_date=None, end_date=None):
        """获取运营面板统计数据"""
        try:
            # 构建日期条件
            date_condition = ""
            date_params = ()
            if start_date and end_date:
                date_condition = " WHERE timestamp BETWEEN %s AND %s"
                date_params = (start_date, end_date)
            else:
                # 默认最近7天
                date_condition = " WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
                date_params = ()

            # 获取用户总数 - 从user_profiles表（静态数据，不受日期影响）
            total_users_query = "SELECT COUNT(*) as total FROM user_profiles"
            total_users_result = self.execute_query(total_users_query)
            total_users = total_users_result[0]['total'] if total_users_result else 0
            
             # 获取总生成次数 - 从generation_logs表
            if date_condition:
                total_generations_query = f"SELECT COUNT(*) as total FROM generation_logs {date_condition} AND event_type = 'generate'"
                total_generations_result = self.execute_query(total_generations_query, date_params)
            else:
                total_generations_query = "SELECT COUNT(*) as total FROM generation_logs WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND event_type = 'generate'"
                total_generations_result = self.execute_query(total_generations_query)
            
            total_generations = total_generations_result[0]['total'] if total_generations_result else 0
        
            # 获取活跃用户数 - 从generation_logs表，使用DISTINCT去重
            if date_condition:
                active_users_query = f"SELECT COUNT(DISTINCT user_id) as active_users FROM generation_logs {date_condition} AND event_type = 'generate'"
                active_users_result = self.execute_query(active_users_query, date_params)
            else:
                active_users_query = "SELECT COUNT(DISTINCT user_id) as active_users FROM generation_logs WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND event_type = 'generate'"
                active_users_result = self.execute_query(active_users_query)
            
            active_users = active_users_result[0]['active_users'] if active_users_result else 0
            
            # 获取平均评分 - 从rating_distribution表计算（静态数据，不受日期影响）
            avg_rating_query = """
            SELECT 
                ROUND(SUM(rating * rating_count) / SUM(rating_count), 2) as avg_rating
            FROM rating_distribution
            WHERE rating > 0 AND rating_count > 0
            """
            avg_rating_result = self.execute_query(avg_rating_query)
            avg_rating = avg_rating_result[0]['avg_rating'] if avg_rating_result and avg_rating_result[0]['avg_rating'] is not None else 0
            
            stats = {
                'totalUsers': int(total_users),
                'totalGenerations': int(total_generations),
                'activeUsers': int(active_users),
                'avgRating': float(avg_rating),
                'satisfactionRate': round(float(avg_rating) / 5 * 100, 1),
                'dateRange': f"{start_date} 至 {end_date}" if start_date and end_date else "最近7天"
            }
            
            logger.info(f"📊 获取MySQL运营统计数据: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取MySQL运营统计数据失败: {e}")
            return None
    
    def close(self):
        """关闭连接"""
        if self.connection:
            self.connection.close()
            logger.info("✅ MySQL连接已关闭")

# 创建全局实例
mysql_service = MySQLService()
