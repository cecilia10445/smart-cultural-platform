#!/usr/bin/env python3
import json
import random
import os
import tarfile
from datetime import datetime, timedelta

def load_real_users_from_file():
    """从用户数据文件加载真实的用户信息"""
    users_file = "/home/mywork/smart-cultural-platform/backend/data/test_users.json"  # 根据你的实际路径调整
    
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            users_data = json.load(f)
        
        # 只返回普通用户，排除管理员
        real_users = [user for user in users_data['users'] if user['user_id'].startswith('U')]
        print(f"✅ 加载了 {len(real_users)} 个真实用户")
        return real_users
        
    except Exception as e:
        print(f"❌ 加载真实用户数据失败: {e}")
        return []

def get_image_list_from_archive(archive_path):
    """从压缩包获取图片文件列表（不解压）"""
    image_files = []
    try:
        with tarfile.open(archive_path, 'r') as tar:
            for member in tar.getmembers():
                if member.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_files.append(member.name)
        return image_files
    except Exception as e:
        print(f"❌ 读取压缩包失败: {e}")
        return []

def parse_flickr_token_file(token_file_path):
    """解析Flickr30K的.token标注文件"""
    annotations = {}
    
    print(f"📖 解析标注文件: {token_file_path}")
    
    try:
        with open(token_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) == 2:
                    image_key, caption = parts
                    
                    if '#' in image_key:
                        image_name, caption_id = image_key.split('#')
                        image_name = image_name.strip()
                        
                        if image_name not in annotations:
                            annotations[image_name] = []
                        
                        annotations[image_name].append(caption.strip())
        
        print(f"✅ 解析成功！共 {len(annotations)} 张图片，总标注数: {sum(len(caps) for caps in annotations.values())}")
        return annotations
        
    except Exception as e:
        print(f"❌ 解析标注文件失败: {e}")
        return {}

def preprocess_flickr_dataset():
    """预处理Flickr30K数据集，使用真实用户数据进行分配"""
    
    token_file_path = "/home/mywork/smart-cultural-platform/data/flickr30k_dataset/raw/annotations/results_20130124.token"
    image_archive = "/home/mywork/smart-cultural-platform/data/flickr30k_dataset/compressed/flickr30k.tar.gz"
    output_file = "/home/mywork/smart-cultural-platform/data/processed/flickr_platform_logs.json"
    
    # 解析标注文件
    annotations = parse_flickr_token_file(token_file_path)
    
    if not annotations:
        print("❌ 无法解析标注文件")
        return
    
    # 获取压缩包中的图片列表
    print("📷 扫描图片压缩包...")
    image_files = get_image_list_from_archive(image_archive)
    print(f"✅ 找到 {len(image_files)} 张图片")
    
    # 加载真实用户数据
    real_users = load_real_users_from_file()
    if not real_users:
        print("❌ 无法加载真实用户数据，使用模拟用户")
        real_users = [{"user_id": f"U{i:04d}"} for i in range(1, 1001)]
    
    print(f"👥 使用 {len(real_users)} 个真实用户")
    
    # 英文风格列表
    styles = ["写实风格", "电影感", "鲜明色彩", "艺术感", "自然风格", "赛博朋克", 
          "极简主义", "戏剧化", "专业摄影", "水彩画风", "奇幻风格", "复古风"]
    
    # 转换为项目日志格式
    converted_logs = []
    processed_count = 0
    
    # 创建用户活动计数器
    user_activity = {user['user_id']: 0 for user in real_users}
    
    # 随机分配数据集给用户
    all_image_items = list(annotations.items())
    random.shuffle(all_image_items)  # 随机打乱数据集
    
    for image_name, captions in all_image_items:
        if processed_count >= 20000:  # 限制处理数量
            break
            
        # 随机选择一个用户（加权随机，让活动较少的用户有更高概率被选中）
        inactive_users = [uid for uid, count in user_activity.items() if count == min(user_activity.values())]
        user_id = random.choice(inactive_users)
        user_activity[user_id] += 1
        
        # 找到用户完整信息
        user_info = next((user for user in real_users if user['user_id'] == user_id), {})
        
        # 随机时间（过去30天内）
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        timestamp = (datetime.now() - timedelta(days=days_ago, hours=hours_ago)).isoformat()
        
        # 使用第一个标注作为prompt
        prompt = captions[0] if captions else f"Image description {processed_count}"
        
        # 构建图片访问URL
        image_url = f"/api/flickr/image/{user_id}/{image_name}"
        
        # 生成标题和内容
        title = prompt[:40] + "..." if len(prompt) > 40 else prompt
        content = f"This image shows: {prompt}. The scene captures authentic moments with natural composition and realistic details that make it visually engaging."
        
        # 使用其他标注作为captions
        other_captions = captions[1:4] if len(captions) > 1 else captions
        while len(other_captions) < 3:
            other_captions.append(f"Another perspective of this scene")
        
        # 构建日志条目
        log_entry = {
            "timestamp": timestamp,
            "event_type": "generate",
            "user_id": user_id,
            "user_info": user_info,  # 包含完整的用户信息
            "data": {
                "user_id": user_id,
                "prompt": prompt,
                "style": random.choice(styles),
                "image_url": image_url,
                "image_path": image_name,
                "archive_path": "compressed/flickr30k-images.tar",
                "captions": other_captions[:3],
                "generation_time": round(random.uniform(2.0, 8.0), 2),
                "content_length": len(content),
                "title": title,
                "content": content,
                "user_rating": random.randint(1, 5),           # ← 新增：用户评分
                "download_count": random.randint(0, 10),       # ← 新增：下载次数
                "user_age": user_info.get('age_range', random.randint(18, 65)) if user_info else random.randint(18, 65),  # ← 新增：用户年龄
                "user_gender": user_info.get('gender', random.randint(0, 1)) if user_info else random.randint(0, 1),      # ← 新增：用户性别
                "login_time": timestamp,                       # ← 新增：登录时间
                "generation_time": round(random.uniform(2.0, 8.0), 2)
            }
        }
        
        converted_logs.append(log_entry)
        processed_count += 1
        
        # 进度显示
        if processed_count % 1000 == 0:
            print(f"🔄 已处理 {processed_count} 条数据...")
    
    # 保存转换后的数据
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for log in converted_logs:
            f.write(json.dumps(log, ensure_ascii=False) + '\n')
    
    # 输出分配统计
    print(f"\n📊 用户活动统计:")
    active_users = sum(1 for count in user_activity.values() if count > 0)
    avg_activity = sum(user_activity.values()) / len(real_users)
    print(f"   活跃用户: {active_users}/{len(real_users)}")
    print(f"   平均每用户活动数: {avg_activity:.1f}")
    print(f"   最多活动的用户: {max(user_activity.values())} 次")
    print(f"   最少活动的用户: {min(user_activity.values())} 次")
    
    print(f"\n✅ Flickr30K数据集预处理完成！共生成 {len(converted_logs)} 条真实标注日志")
    print(f"📁 输出文件: {output_file}")
    
    # 显示一些样本
    print("\n📊 样本数据:")
    for i, log in enumerate(converted_logs[:2]):
        print(f"样本 {i+1}:")
        print(f"  用户: {log['data']['user_id']}")
        print(f"  提示: {log['data']['prompt'][:60]}...")
        print(f"  图片: {log['data']['image_url']}")
        print()

if __name__ == "__main__":
    preprocess_flickr_dataset()