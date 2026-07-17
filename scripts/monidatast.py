#!/usr/bin/env python3
import json
import math
import random
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, array, struct
from pyspark.sql.types import *
import os

def generate_synthetic_dataset():
    """生成智能文创平台模拟数据集"""
    
    print("=== 开始生成智能文创平台模拟数据集 ===")
    
    # 创建SparkSession
    spark = SparkSession.builder \
        .appName("SyntheticDataGenerator") \
        .config("spark.sql.warehouse.dir", "/user/hive/warehouse") \
        .getOrCreate()
    
    # 设置日志级别
    spark.sparkContext.setLogLevel("ERROR")
    
    # 基础配置
    TOTAL_RECORDS = 100000
    TOTAL_USERS = 3000
    START_DATE = datetime(2025, 9, 8)
    END_DATE = datetime(2025, 10, 11)  # 修改：延长到10月11日
    
    print(f"📊 生成配置: {TOTAL_RECORDS}条记录, {TOTAL_USERS}个用户")
    
    # 1. 用户画像定义
    user_profiles = generate_user_profiles(TOTAL_USERS)
    
    # 2. 风格库定义 (120个娱乐化风格)
    styles = generate_style_library()
    
    # 3. 内容模板定义
    titles, contents, prompts = generate_content_templates()
    
    # 4. 按日期分批生成数据
    generate_data_by_date(spark, TOTAL_RECORDS, user_profiles, styles, titles, contents, prompts, START_DATE, END_DATE)
    
    spark.stop()
    print("=== 模拟数据集生成完成 ===")

def generate_user_profiles(total_users):
    """生成用户画像 - 使用现有用户ID模式"""
    print("👥 生成用户画像...")
    
    user_profiles = []
    
    # 使用现有的用户ID模式 (从已有数据中观察到的模式)
    existing_user_prefixes = ["U", "user", "test", "demo", "creator", "artist"]
    
    # 年龄分布
    age_distribution = {
        "<18": 0.125,   # 12.5%
        "18-24": 0.20,  # 20%
        "25-29": 0.18,  # 18%
        "30-34": 0.10,  # 10%
        "35-39": 0.06,  # 6%
        "40-49": 0.045, # 4.5%
        "50+": 0.05,    # 5%
        "NULL": 0.24    # 24%
    }
    
    # 性别分布
    gender_distribution = {
        "unknown": 0.61,  # 61%
        "female": 0.22,   # 22%
        "male": 0.17      # 17%
    }
    
    # 活跃时段分布 - 修改：调整为深夜党 > 晚间党 >> 下午党 > 上午党
    period_distribution = {
        0: 0.50,  # 深夜党 50% (增加)
        1: 0.05,  # 上午党 5% (减少)
        2: 0.10,  # 下午党 10% (微增)
        3: 0.35   # 晚间党 35% (减少)
    }
    
    # 用户活跃度分布 - 修改：大幅降低高活跃用户比例
    activity_distribution = {
        "high": 0.05,    # 5% 高活跃 (原来是20%) ← 这里改了数值
        "medium": 0.25,  # 25% 中等活跃 (原来是30%) ← 这里改了数值
        "low": 0.70      # 70% 低活跃 (原来是50%) ← 这里改了数值
    }
    
    # 生成用户
    for i in range(total_users):
        # 使用混合用户ID模式
        if i < 1500:  # 50%使用U前缀
            user_id = f"U{random.randint(1000, 9999)}"
        elif i < 2500:  # 33%使用user前缀
            user_id = f"user{random.randint(100, 999)}"
        else:  # 17%使用其他前缀
            prefix = random.choice(["test", "demo", "creator", "artist"])
            user_id = f"{prefix}{random.randint(1, 999)}"
        
        # 分配年龄
        age_group = random.choices(
            list(age_distribution.keys()),
            weights=list(age_distribution.values())
        )[0]
        
        # 分配具体年龄
        if age_group == "<18":
            age = random.randint(13, 17)
        elif age_group == "18-24":
            age = random.randint(18, 24)
        elif age_group == "25-29":
            age = random.randint(25, 29)
        elif age_group == "30-34":
            age = random.randint(30, 34)
        elif age_group == "35-39":
            age = random.randint(35, 39)
        elif age_group == "40-49":
            age = random.randint(40, 49)
        elif age_group == "50+":
            age = random.randint(50, 65)
        else:  # NULL
            age = None
        
        # 分配性别
        gender = random.choices(
            list(gender_distribution.keys()),
            weights=list(gender_distribution.values())
        )[0]
        
        # 分配活跃时段
        active_period = random.choices(
            list(period_distribution.keys()),
            weights=list(period_distribution.values())
        )[0]
        
        # 分配活跃度
        activity_level = random.choices(
            list(activity_distribution.keys()),
            weights=list(activity_distribution.values())
        )[0]
        
        user_profiles.append({
            "user_id": user_id,
            "age": age,
            "gender": gender,
            "active_period": active_period,
            "activity_level": activity_level
        })
    
    print(f"✅ 生成 {len(user_profiles)} 个用户画像")

     # 输出活跃度分布统计
    activity_counts = {"high": 0, "medium": 0, "low": 0}
    for user in user_profiles:
        activity_counts[user["activity_level"]] += 1
    
    print(f"📊 用户活跃度分布:")
    for level, count in activity_counts.items():
        percentage = (count / total_users) * 100
        print(f"  - {level}: {count} 用户 ({percentage:.1f}%)")

    return user_profiles

def generate_style_library():
    """生成120个娱乐化风格"""
    styles = [
        # 艺术幻想类 (35个)
        "二次元", "动漫风", "游戏原画", "像素艺术", "低多边形", 
        "赛博朋克", "蒸汽朋克", "奇幻插画", "科幻未来", "魔幻现实主义",
        "童话风格", "神话史诗", "克苏鲁", "哥特暗黑", "吸血鬼",
        "精灵森林", "巨龙传说", "机甲战士", "星际穿越", "异世界",
        "梦境迷离", "超现实", "抽象艺术", "表现主义", "极简线条",
        "涂鸦街头", "波普艺术", "孟菲斯", "酸性设计", "Y2K千禧风",
        "故障艺术", "光晕效果", "霓虹炫光", "全息投影", "赛博格",
        
        # 情感氛围类 (30个)
        "治愈温暖", "浪漫唯美", "忧郁蓝调", "欢乐庆典", "宁静禅意",
        "神秘诡异", "热血战斗", "怀旧复古", "梦幻童话", "清新自然",
        "奢华璀璨", "简约现代", "民族风情", "节日狂欢", "季节限定",
        "雨天意境", "雪景浪漫", "夏日海滩", "秋日落叶", "春日樱花",
        "冬日暖阳", "星空浩瀚", "海洋深邃", "森林秘境", "沙漠孤寂",
        "都市夜景", "田园牧歌", "校园青春", "恋爱甜蜜", "孤独沉思",
        
        # 潮流文化类 (25个)
        "国潮新风", "日系和风", "韩流时尚", "欧美复古", "港风怀旧",
        "抖音热门", "小红书爆款", "微博同款", "ins网红", "vlog日常",
        "直播效果", "电竞热血", "动漫周边", "偶像应援", "粉丝创作",
        "同人衍生", "虚拟偶像", "元宇宙", "NFT艺术", "数字藏品",
        "AI生成", "算法艺术", "生成艺术", "数据可视化", "交互设计",
        
        # 视觉技术类 (30个)
        "胶片质感", "电影大片", "黑白摄影", "人像精修", "风景调色",
        "微距世界", "光绘涂鸦", "长曝光", "HDR增强", "复古滤镜",
        "日系清新", "欧美胶片", "电影色调", "动画渲染", "3D建模",
        "材质贴图", "光影追踪", "体积光", "粒子效果", "流体模拟",
        "毛发渲染", "卡通渲染", "水墨渲染", "油画厚重", "水彩透明",
        "素描线条", "版画粗犷", "刺绣纹理", "编织质感", "折纸艺术"
    ]
    
    print(f"🎨 生成 {len(styles)} 个风格")
    return styles

def generate_content_templates():
    """生成内容模板"""
    
    # 标题模板 (30个诗意标题)
    titles = [
        "月光下的独白", "星辰与海的对话", "风居住的街道", "时间煮雨", "云深不知处",
        "花开半夏", "夜航船", "山外山", "雾里看花", "镜中缘",
        "浮生若梦", "空谷回音", "流光飞舞", "静水深流", "远山如黛",
        "秋水共长天", "落霞孤鹜", "青石向晚", "竹林听雨", "雪落无声",
        "灯火阑珊", "暮色四合", "晨光熹微", "午后茶香", "夜雨寄北",
        "春风十里", "夏夜流萤", "秋叶静美", "冬日暖阳", "四季轮回"
    ]
    
    # 内容模板 (20个诗意文案)
    contents = [
        # 短文案 (10个)
        "在光的缝隙里，寻找影子的形状。",
        "时间缓缓流淌，记忆静静沉淀。",
        "风吹过的地方，都有故事在生长。",
        "用色彩说话，让画面歌唱。",
        "一花一世界，一图一心情。",
        "灵感如流星，划过创意的夜空。",
        "在虚拟与现实之间，搭建想象的桥梁。",
        "每一个像素，都是情感的容器。",
        "让机器理解美，让人感受温暖。",
        "从数据到诗意，从算法到艺术。",
        
        # 中长文案 (10个)
        "当晨曦的第一缕光穿过云层，万物开始苏醒。在这光与影的交织中，我们捕捉到了时间的痕迹，那些稍纵即逝的美好被永久定格，成为记忆中永不褪色的画面。",
        "海风轻抚着沙滩，浪花在月光下闪烁。远方的灯塔若隐若现，像是梦境中的指引。这一刻，所有的喧嚣都归于平静，只剩下自然最原始的低语。",
        "在城市的天际线上，霓虹与星光争辉。钢筋水泥的丛林里，依然有诗意在生长。每一个窗口都藏着一个故事，每盏灯都在诉说着不同的生活。",
        "秋叶飘零，像是时间的信笺。金黄的银杏，火红的枫叶，在微风中轻轻旋转，最终归于大地。这是自然的轮回，也是生命的礼赞。",
        "雨滴敲打着窗棂，奏出自然的乐章。雾气弥漫的街道上，行人的身影若隐若现。这样的天气最适合回忆，也最适合创造新的记忆。",
        "星空浩瀚，让人感受到自身的渺小。但正是这份渺小，让我们更加珍惜眼前的光亮。每一颗星星都是一个未知的世界，每一次仰望都是一次心灵的旅行。",
        "山间的清晨，雾气如轻纱般缭绕。鸟鸣清脆，溪水潺潺，大自然用它最纯粹的方式唤醒沉睡的世界。在这里，时间仿佛放慢了脚步。",
        "古老的街道，斑驳的墙面，每一处痕迹都在诉说着过往。现代与传统的碰撞，在这里达成了奇妙的和谐。历史不是负担，而是创作的源泉。",
        "数字的世界里，代码如诗般流淌。算法不再是冰冷的公式，而是创造美的工具。在这个虚拟的宇宙中，想象力是唯一的边界。",
        "四季更迭，万物生长。春天的嫩芽，夏日的繁花，秋天的硕果，冬日的寂静。自然用它的方式告诉我们：变化才是永恒的美。"
    ]
    
    # 提示词模板 (有长有短，娱乐性强)
    prompts = [
        # 短提示词
        "一只会跳舞的熊猫",
        "星空下的独角兽",
        "赛博朋克城市夜景", 
        "魔法森林的早晨",
        "蒸汽朋克飞行器",
        "梦幻海底世界",
        "未来科技生活",
        "童话城堡",
        "二次元美少女",
        "机甲战士战斗",
        
        # 中等长度提示词
        "一个穿着汉服的少女在樱花树下弹古筝，唯美古风",
        "赛博朋克风格的东京街头，霓虹灯闪烁，雨夜氛围",
        "奇幻森林中的精灵村落，发光植物，神秘梦幻",
        "蒸汽朋克风格的飞艇在云层中航行，机械细节丰富",
        "未来城市的空中花园，高科技与自然完美融合",
        "魔法学院的大厅，漂浮的蜡烛，古老神秘",
        "海底龙宫，珊瑚建筑，鱼群游弋，梦幻蓝色调",
        "星际旅行，虫洞穿越，宇宙星辰，科幻感十足",
        "童话世界的糖果屋，色彩鲜艳，甜美梦幻",
        "古风武侠，月下对决，水墨风格，意境深远",
        
        # 长提示词
        "在一个遥远的未来世界，人类与AI和谐共处，城市中悬浮的建筑物与自然植被完美融合，展现科技与生态的平衡之美，赛博朋克风格",
        "深秋的枫叶林中，一位身着传统汉服的女子漫步其中，金色的阳光透过红叶洒在她身上，营造出温暖而浪漫的唯美氛围，电影质感",
        "神秘的外星星球上，奇异的植物散发着柔和的光芒，透明的生物在空气中游动，整个场景充满未知与探索的科幻感，超现实风格",
        "蒸汽朋克时代的伦敦，齿轮与机械装置遍布街头，穿着维多利亚时期服装的人们乘坐飞艇穿梭，雾霾中透出铜质的光泽",
        "梦幻的云端之城，建筑由白云和水晶构成，天使与精灵在彩虹间嬉戏，整个画面充满童话般的幻想色彩，治愈温暖风格",
        "末日废土世界，残破的城市废墟中生长着发光的变异植物，幸存者穿着改造的防护服探索，营造出悲壮而希望的独特美学",
        "传统水墨画中的山水意境，但融入了数字科技元素，流动的代码与墨迹交织，展现古今融合的东方哲学，新国风设计",
        "奇幻的地下洞穴，发光的蘑菇森林，地下河流淌着液态宝石，神秘的古老文明遗迹若隐若现，充满探险的神秘氛围"
    ]
    
    print(f"📝 生成 {len(titles)} 个标题, {len(contents)} 个内容, {len(prompts)} 个提示词")
    return titles, contents, prompts

def generate_data_by_date(spark, total_records, user_profiles, styles, titles, contents, prompts, start_date, end_date):
    """按日期分批生成数据"""
    print("📅 按日期分批生成数据...")
    
    date_range = (end_date - start_date).days
    output_dir = "/home/mywork/smart-cultural-platform/data/dataset"
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 定义热门风格 - 修改：按照新的顺序和权重
    hot_styles = ["赛博朋克", "日系清新", "治愈温暖", "电影感", "动漫风", "人像精修", "小红书爆款", "抖音热门"]
    # 热门风格权重 - 修改：明显的阶梯差距，大幅降低数值
    hot_style_weights = [15, 12, 10, 8, 7, 6, 6, 4]  # 总和68
    
    # 计算每日记录数 (非均匀分布)
    daily_records = calculate_daily_records(total_records, date_range)
    
    # 用户行为统计
    user_behavior = {user["user_id"]: {
        "count": 0, 
        "styles": set(),
        "activity_level": user["activity_level"]
    } for user in user_profiles}
    
    # 下载量统计 - 新增：用于确保总体比例100:18
    total_generations = 0
    total_downloads = 0
    
    total_generated = 0
    
    for day in range(date_range + 1):
        current_date = start_date + timedelta(days=day)
        day_records = daily_records[day]
        
        print(f"📊 生成 {current_date.strftime('%Y-%m-%d')} 的数据: {day_records} 条记录")
        
        records = []
        for i in range(day_records):
            # 基于用户活跃度选择用户
            user = select_user_based_on_activity(user_profiles, user_behavior, current_date)
            user_id = user["user_id"]
            user_age = user["age"]
            user_gender = user["gender"]
            user_period = user["active_period"]
            
            # 更新时间行为统计
            user_behavior[user_id]["count"] += 1
            
            # 生成时间戳
            hours_offset = generate_hour_based_on_period(user_period)
            timestamp = current_date + timedelta(hours=hours_offset, 
                                               minutes=random.randint(0, 59),
                                               seconds=random.randint(0, 59))
            
            # 选择风格 (非均匀分布) - 修改：使用权重列表
            style = select_style_with_weights(styles, hot_styles, hot_style_weights, user_behavior[user_id], current_date, day, date_range)
            user_behavior[user_id]["styles"].add(style)
            
            # 生成提示词 (基于用户活跃度)
            prompt = select_prompt_based_on_activity(prompts, user_behavior[user_id]["activity_level"])
            
            # 生成标题和内容
            title = random.choice(titles)
            content = random.choice(contents)
            content_length = len(content)
            
            # 生成图片URL
            image_url = f"/home/mywork/smart-cultural-platform/static/images/image_{random.randint(1, 50):03d}.jpg"
            
            # 生成时间和评分
            generation_time = generate_generation_time(style)
            user_rating = generate_rating(user_age, user_gender, content_length, timestamp.hour)
            
            # 生成下载次数 - 修改：基于总体比例调整
            download_count = generate_download_count_with_global_ratio(style, content_length, user_rating, total_generations, total_downloads)
            
            # 更新全局统计
            total_generations += 1
            total_downloads += download_count
            
            # 生成关键词
            keywords = generate_keywords(prompt, style)
            
            record = {
                "user_id": user_id,
                "event_type": "generate",
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": prompt,
                "style": style,
                "image_url": image_url,
                "generation_time": generation_time,
                "content_length": content_length,
                "captions": keywords,
                "title": title,
                "content": content,
                "user_rating": user_rating,
                "download_count": download_count,
                "user_age": user_age,
                "user_gender": 0 if user_gender == "female" else 1 if user_gender == "male" else None,
                "login_time": timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            records.append(record)
        
        # 保存当天的数据
        if records:
            save_daily_data(spark, records, current_date, output_dir)
            total_generated += len(records)
    
    # 输出最终下载比例
    final_ratio = (total_downloads / total_generations) * 100 if total_generations > 0 else 0
    print(f"📥 最终下载比例: {total_downloads}/{total_generations} = {final_ratio:.1f}% (目标: 18%)")
    
    print(f"✅ 数据生成完成: 总共 {total_generated} 条记录")
    print(f"📁 数据保存在: {output_dir}")

def select_style_with_weights(styles, hot_styles, hot_style_weights, user_behavior, current_date, day, total_days):
    """使用权重列表选择风格，并考虑独立的时间趋势模式"""
    # 每个风格有独立的开始时间、变化周期、随机相位偏移和结束水平
    style_trend_configs = {
        "赛博朋克": {"start_day": 0, "cycle_days": total_days, "pattern": "rising", "phase_shift": 0.15, "end_level": 1.8},
        "日系清新": {"start_day": 5, "cycle_days": total_days - 10, "pattern": "early_peak", "phase_shift": 0.73, "end_level": 0.7},
        "治愈温暖": {"start_day": 10, "cycle_days": total_days, "pattern": "stable_rising", "phase_shift": 0.42, "end_level": 1.3},
        "电影感": {"start_day": 15, "cycle_days": total_days - 5, "pattern": "mid_peak", "phase_shift": 0.89, "end_level": 1.1},
        "动漫风": {"start_day": 8, "cycle_days": total_days, "pattern": "fluctuating", "phase_shift": 0.27, "end_level": 1.0},
        "人像精修": {"start_day": 20, "cycle_days": total_days - 15, "pattern": "late_peak", "phase_shift": 0.56, "end_level": 1.8},
        "小红书爆款": {"start_day": 0, "cycle_days": total_days - 20, "pattern": "declining", "phase_shift": 0.50, "end_level": 2.0},
        "抖音热门": {"start_day": 3, "cycle_days": total_days - 25, "pattern": "rising", "phase_shift": 0.05, "end_level": 2.2}
    }
    
    trend_adjustments = {}
    
    for style in hot_styles:
        config = style_trend_configs.get(style, {"start_day": 0, "cycle_days": total_days, "pattern": "stable", "phase_shift": 0, "end_level": 1.0})
        start_day = config["start_day"]
        cycle_days = config["cycle_days"]
        pattern = config["pattern"]
        phase_shift = config["phase_shift"]
        end_level = config["end_level"]
        
        # 计算在当前趋势周期中的进度（添加相位偏移）
        if day < start_day:
            # 趋势还没开始，使用基础权重
            adjustment = 0.8
        elif day >= start_day + cycle_days:
            # 趋势周期已结束，使用独立的结束水平
            adjustment = end_level
        else:
            # 在趋势周期内，应用相位偏移
            trend_progress = (day - start_day) / cycle_days
            shifted_progress = (trend_progress + phase_shift) % 1.0  # 确保在0-1范围内
            
            if pattern == "rising":
                # 持续上升：从0.8到结束水平
                adjustment = 0.8 + (end_level - 0.8) * shifted_progress
                
            elif pattern == "early_peak":
                # 早期高峰：在进度0.3时达到高峰，然后下降到结束水平
                peak_point = 0.3
                if shifted_progress <= peak_point:
                    adjustment = 0.8 + (1.6 - 0.8) * (shifted_progress / peak_point)
                else:
                    adjustment = 1.6 - (1.6 - end_level) * ((shifted_progress - peak_point) / (1 - peak_point))
                    
            elif pattern == "late_peak":
                # 晚期高峰：在进度0.7时达到高峰，然后下降到结束水平
                peak_point = 0.7
                if shifted_progress <= peak_point:
                    adjustment = 0.8 + (1.5 - 0.8) * (shifted_progress / peak_point)
                else:
                    adjustment = 1.5 - (1.5 - end_level) * ((shifted_progress - peak_point) / (1 - peak_point))
                    
            elif pattern == "mid_peak":
                # 中期高峰：在进度0.5时达到高峰，然后下降到结束水平
                peak_point = 0.5
                if shifted_progress <= peak_point:
                    adjustment = 0.8 + (1.4 - 0.8) * (shifted_progress / peak_point)
                else:
                    adjustment = 1.4 - (1.4 - end_level) * ((shifted_progress - peak_point) / (1 - peak_point))
                    
            elif pattern == "declining":
                # 持续下降：从1.2到结束水平
                adjustment = 1.2 - (1.2 - end_level) * shifted_progress
                
            elif pattern == "fluctuating":
                # 波动：在基础值附近波动，最终收敛到结束水平
                base_fluctuation = 1.0 + 0.4 * math.sin(shifted_progress * 8 * math.pi)
                # 逐渐收敛到结束水平
                convergence_factor = shifted_progress ** 0.5  # 使用平方根让收敛更平缓
                adjustment = base_fluctuation * (1 - convergence_factor) + end_level * convergence_factor
                
            elif pattern == "stable_rising":
                # 稳定上升：从0.9缓慢上升到结束水平
                adjustment = 0.9 + (end_level - 0.9) * shifted_progress
                
            else:  # stable
                adjustment = end_level
        
        # 添加一些随机噪声
        adjustment *= random.uniform(0.9, 1.1)
        trend_adjustments[style] = max(0.3, adjustment)
    
    # 选择热门风格的概率 - 修改：降低热门风格总体比例
    if random.random() < 0.45:  # 降低到45%的概率选择热门风格
        # 应用趋势调整后的权重
        adjusted_weights = [hot_style_weights[i] * trend_adjustments[hot_styles[i]] for i in range(len(hot_styles))]
        adjusted_weights = [max(0.1, w) for w in adjusted_weights]
        
        style = random.choices(hot_styles, weights=adjusted_weights)[0]
    else:
        if user_behavior["styles"] and random.random() < 0.4:
            style = random.choice(list(user_behavior["styles"]))
        else:
            style = random.choice(styles)
    
    return style

def generate_download_count_with_global_ratio(style, content_length, rating, total_generations, total_downloads):
    """生成下载次数，确保总体比例接近100:18"""
    # 基础概率
    base_probability = 0.18  # 目标比例
    
    # 根据当前总体比例动态调整
    current_ratio = (total_downloads / total_generations) if total_generations > 0 else 0
    if current_ratio < 0.16:  # 如果当前比例低于16%，增加概率
        base_probability *= 1.2
    elif current_ratio > 0.20:  # 如果当前比例高于20%，减少概率
        base_probability *= 0.8
    
    # 风格影响
    high_download_styles = ["赛博朋克", "日系清新", "治愈温暖", "电影感", "动漫风"]
    if style in high_download_styles:
        base_probability *= 1.3
    
    # 内容长度影响
    if content_length > 80:
        base_probability *= 1.2
    
    # 评分影响
    if rating > 4.0:
        base_probability *= 1.2
    
    # 生成下载次数
    if random.random() < base_probability:
        if random.random() < 0.15:  # 15%的概率多次下载
            return random.randint(2, 5)
        else:
            return 1
    else:
        return 0

def calculate_daily_records(total_records, date_range):
    """计算每日记录数 (非均匀分布)"""
    daily_records = []
    
    # 9月初活跃度较低，逐渐增加到10月初的高峰
    for day in range(date_range + 1):
        # 使用S曲线增长
        progress = day / date_range
        # S曲线函数，开始增长慢，中间快，最后趋于平稳
        weight = 1 / (1 + (10 ** (-8 * (progress - 0.5))))  # S型曲线
        
        # 添加一些随机波动
        weight *= random.uniform(0.8, 1.2)
        
        day_count = int(weight * (total_records / (date_range + 1)) * 1.2)  # 降低乘数从1.5到1.2
        # 确保每天至少有50条记录
        if day_count < 50:
            day_count = 50
        daily_records.append(day_count)
    
    # 调整总数 - 使用循环累加
    current_total = 0
    for count in daily_records:
        current_total += count
    
    # 计算缩放因子
    scale_factor = total_records / current_total
    
    # 应用缩放并确保最小值
    scaled_records = []
    for count in daily_records:
        scaled_count = int(count * scale_factor)
        if scaled_count < 50:  # 使用if语句而不是max函数
            scaled_count = 50
        scaled_records.append(scaled_count)
    
    # 重新计算总数
    final_total = 0
    for count in scaled_records:
        final_total += count
    
    # 调整最后一天的数量来匹配总数
    diff = total_records - final_total
    scaled_records[-1] += diff
    
    print(f"📈 每日分布: 首日{scaled_records[0]}条, 末日{scaled_records[-1]}条, 总计{final_total + diff}条")
    
    return scaled_records

def select_user_based_on_activity(user_profiles, user_behavior, current_date):
    """基于用户活跃度选择用户"""
    # 高活跃用户有更高概率被选中
    weights = []
    for user in user_profiles:
        user_id = user["user_id"]
        activity_level = user_behavior[user_id]["activity_level"]
        
        if activity_level == "high":
            weight = 2.0  # 高活跃用户权重最高
        elif activity_level == "medium":
            weight = 1.2  # 中等活跃用户
        else:
            weight = 0.9  # 低活跃用户
            
        # 如果用户当天还没生成过，增加权重
        if user_behavior[user_id]["count"] == 0:
            weight *= 1.2
            
        weights.append(weight)
    
    return random.choices(user_profiles, weights=weights)[0]

def select_prompt_based_on_activity(prompts, activity_level):
    """基于用户活跃度选择提示词"""
    # 高活跃用户倾向于使用更长、更具体的提示词
    if activity_level == "high":
        # 70%概率选择中长提示词
        if random.random() < 0.7:
            return random.choice(prompts[10:])  # 中长提示词
        else:
            return random.choice(prompts[:10])  # 短提示词
    else:
        # 低活跃用户更多使用短提示词
        if random.random() < 0.6:
            return random.choice(prompts[:10])  # 短提示词
        else:
            return random.choice(prompts[10:])  # 中长提示词

def generate_hour_based_on_period(period):
    """基于用户活跃时段生成小时"""
    if period == 0:  # 深夜党
        return random.randint(0, 5)
    elif period == 1:  # 上午党
        return random.randint(6, 11)
    elif period == 2:  # 下午党
        return random.randint(12, 17)
    else:  # 晚间党
        return random.randint(18, 23)

def generate_generation_time(style):
    """生成生成时间"""
    fast_styles = ["极简线条", "简约现代", "黑白摄影", "素描线条", "像素艺术"]
    slow_styles = ["3D建模", "油画厚重", "精细插画", "复杂渲染", "多重特效"]
    
    if style in fast_styles:
        return float(round(random.uniform(8, 15), 2))  # 显式转为float
    elif style in slow_styles:
        return float(round(random.uniform(35, 60), 2))
    else:
        return float(round(random.uniform(25, 45), 2))

def generate_rating(age, gender, content_length, hour):
    """生成评分"""
    base_rating = 4.2
    
    if age and age < 25:
        base_rating += random.uniform(0.1, 0.3)
    elif age and age > 40:
        base_rating += random.uniform(0.0, 0.2)
    
    if content_length > 80:
        base_rating += random.uniform(0.1, 0.4)
    
    if hour < 6:
        base_rating += random.uniform(-0.2, 0.3)
    
    rating = base_rating + random.uniform(-0.5, 0.5)
    return float(max(1, min(5, round(rating, 1))))

def generate_keywords(prompt, style):
    """生成高质量关键词"""
    keywords = []
    
    # 1. 添加风格作为第一个关键词
    keywords.append(style)
    
    # 2. 从提示词中提取有意义的关键词
    # 移除标点符号
    clean_prompt = prompt.replace("，", "").replace("。", "").replace("、", "").replace(" ", "")
    
    # 基于提示词内容生成相关关键词
    prompt_keywords = extract_keywords_from_prompt(clean_prompt, style)
    keywords.extend(prompt_keywords)
    
    # 3. 添加风格相关关键词
    style_keywords = get_style_related_keywords(style)
    keywords.extend(style_keywords)
    
    # 4. 去重并限制数量
    unique_keywords = list(set(keywords))
    return unique_keywords[:8]  # 最多8个关键词

def extract_keywords_from_prompt(prompt, style):
    """从提示词中提取关键词"""
    keywords = []
    
    # 基于内容的关键词映射
    content_keywords = {
        "熊猫": ["动物", "可爱", "黑白", "国宝"],
        "星空": ["宇宙", "夜晚", "星星", "天文"],
        "独角兽": ["神话", "梦幻", "魔法", "幻想"],
        "赛博朋克": ["未来", "科技", "霓虹", "都市"],
        "城市夜景": ["建筑", "灯光", "夜晚", "都市"],
        "魔法森林": ["自然", "神秘", "精灵", "奇幻"],
        "蒸汽朋克": ["复古", "机械", "齿轮", "维多利亚"],
        "海底世界": ["海洋", "鱼类", "珊瑚", "蓝色"],
        "未来科技": ["创新", "数字", "智能", "先进"],
        "童话城堡": ["梦幻", "古典", "皇家", "建筑"],
        "二次元": ["动漫", "日系", "萌系", "卡通"],
        "机甲战士": ["机器人", "战斗", "科幻", "机械"],
        "汉服": ["传统", "古风", "中国", "文化"],
        "樱花": ["春天", "花卉", "日本", "浪漫"],
        "古筝": ["音乐", "传统", "乐器", "艺术"],
        "东京": ["日本", "都市", "现代", "亚洲"],
        "精灵": ["奇幻", "魔法", "自然", "神秘"],
        "飞艇": ["飞行", "交通", "复古", "冒险"],
        "空中花园": ["建筑", "自然", "未来", "生态"],
        "龙宫": ["神话", "海洋", "传统", "奇幻"],
        "星际旅行": ["太空", "探索", "科幻", "宇宙"],
        "糖果屋": ["甜美", "童话", "色彩", "梦幻"],
        "武侠": ["动作", "传统", "江湖", "功夫"],
        "AI": ["人工智能", "科技", "未来", "智能"],
        "虫洞": ["宇宙", "物理", "科幻", "时空"],
    }
    
    # 检查提示词中包含哪些关键词
    for key, related_words in content_keywords.items():
        if key in prompt:
            keywords.extend(related_words[:2])  # 每个匹配添加2个相关词
    
    return keywords

def get_style_related_keywords(style):
    """获取风格相关的关键词"""
    style_keyword_map = {
        # 艺术幻想类
        "二次元": ["动漫", "日系", "萌系", "卡通", "插画"],
        "动漫风": ["日本", "动画", "漫画", "角色", "色彩鲜艳"],
        "赛博朋克": ["未来", "科技", "霓虹", "都市", "反乌托邦"],
        "治愈温暖": ["温馨", "柔和", "舒适", "平静", "心灵"],
        "梦幻童话": ["魔法", "奇幻", "甜美", "童年", "想象"],
        
        # 潮流文化类
        "抖音热门": ["流行", "趋势", "短视频", "社交", "年轻"],
        "小红书爆款": ["时尚", "生活", "分享", "精致", "网红"],
        "ins网红": ["摄影", "滤镜", "简约", "高级", "社交"],
        
        # 视觉技术类
        "电影大片": ["cinematic", "震撼", "专业", "镜头", "叙事"],
        "人像精修": ["摄影", "美颜", "细节", "专业", "肖像"],
        "胶片质感": ["复古", "怀旧", "颗粒", "经典", "模拟"],
        
        # 情感氛围类
        "浪漫唯美": ["爱情", "温柔", "诗意", "感性", "艺术"],
        "忧郁蓝调": ["深沉", "情感", "思考", "内省", "文艺"],
        "热血战斗": ["激情", "动作", "力量", "斗志", "激烈"],
        
        # 新增风格
        "日系清新": ["清新", "自然", "简约", "日式", "治愈"],
        "电影感": ["电影", "叙事", "镜头感", "氛围", "故事性"],
    }
    
    # 返回风格相关关键词，如果没有匹配则返回空列表
    return style_keyword_map.get(style, [])

def save_daily_data(spark, records, date, output_dir):
    """保存每日数据"""
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
        StructField("user_rating", DoubleType(), True),
        StructField("download_count", IntegerType(), True),
        StructField("user_age", IntegerType(), True),
        StructField("user_gender", IntegerType(), True),
        StructField("login_time", StringType(), True)
    ])
    
    df = spark.createDataFrame(records, schema)
    
    # 按日期保存
    date_str = date.strftime("%Y%m%d")
    output_path = f"{output_dir}/daily_{date_str}.json"
    df.write.mode("overwrite").json(output_path)

if __name__ == "__main__":
    generate_synthetic_dataset()