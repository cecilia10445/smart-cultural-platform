# scripts/preprocess_ernie_dataset.sh
#!/bin/bash

# ==============================================
# ERNIE数据集预处理脚本（独立运行，不影响实时日志）
# ==============================================

PROJECT_ROOT="/home/mywork/smart-cultural-platform"
DATASET_DIR="$PROJECT_ROOT/data/ernie_dataset"
RAW_DATA_DIR="$DATASET_DIR/raw"
PROCESSED_DATA_DIR="$DATASET_DIR/processed"

echo "=== ERNIE数据集预处理 ==="

# 创建目录
mkdir -p $RAW_DATA_DIR $PROCESSED_DATA_DIR

# 检查数据集文件
DATASET_FILE="$RAW_DATA_DIR/ERNIE_creative_dataset.json"
if [ ! -f "$DATASET_FILE" ]; then
    echo "❌ ERNIE数据集文件不存在: $DATASET_FILE"
    echo "📥 请从百度AI Studio下载数据集并放置到该路径"
    echo "💡 下载后运行: ./scripts/preprocess_ernie_dataset.sh"
    exit 1
fi

echo "✅ 找到ERNIE数据集文件"

# 创建Python预处理脚本
cat > $DATASET_DIR/preprocess_ernie.py << 'EOF'
#!/usr/bin/env python3
import json
import random
from datetime import datetime, timedelta
import os

def load_existing_users():
    """从现有用户数据加载1000个真实用户"""
    users_file = "/home/mywork/smart-cultural-platform/backend/data/test_users.json"
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        users = data.get('users', []) + data.get('admins', [])
        return [user['user_id'] for user in users if user.get('user_id')]
    except Exception as e:
        print(f"❌ 加载用户数据失败: {e}")
        return [f"U{1000 + i}" for i in range(1, 1001)]

def preprocess_ernie_dataset():
    """预处理ERNIE创意数据集，转换为项目格式"""
    
    input_file = "raw/ERNIE_creative_dataset.json"
    output_file = "processed/ernie_platform_logs.json"
    
    print("📖 读取ERNIE数据集...")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            # 假设ERNIE数据集是JSON数组或每行一个JSON对象
            content = f.read().strip()
            if content.startswith('['):
                dataset = json.loads(content)
            else:
                # 每行一个JSON对象
                dataset = [json.loads(line) for line in content.split('\n') if line.strip()]
    except Exception as e:
        print(f"❌ 读取ERNIE数据集失败: {e}")
        print("💡 请确保数据集格式正确")
        return
    
    print(f"✅ 成功加载 {len(dataset)} 条ERNIE数据")
    
    # 加载现有用户
    user_ids = load_existing_users()
    print(f"👥 使用 {len(user_ids)} 个真实用户")
    
    # 风格列表（与项目保持一致）
    styles = ["清新", "赛博朋克", "水彩画", "电影感", "复古", "现代", "极简", "奢华", "商务", "可爱"]
    
    # 转换为项目日志格式
    converted_logs = []
    
    for i, item in enumerate(dataset):
        # 随机分配真实用户和时间（过去30天内）
        user_id = random.choice(user_ids)
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        timestamp = (datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)).isoformat()
        
        # 从ERNIE数据中提取字段（根据实际数据集结构调整）
        prompt = item.get("prompt") or item.get("text") or item.get("input") or f"主题{i}"
        style = item.get("style") or random.choice(styles)
        content = item.get("content") or item.get("output") or item.get("generated_text") or f"这是关于{prompt}的创意内容"
        
        # 构建日志条目（与现有日志格式完全一致）
        log_entry = {
            "timestamp": timestamp,
            "event_type": "generate",
            "user_id": user_id,
            "data": {
                "user_id": user_id,
                "prompt": prompt,
                "style": style,
                "image_url": f"https://example.com/ernie/image_{i % 1000}.jpg",
                "captions": [
                    content[:50] + "..." if len(content) > 50 else content,
                    f"{prompt}的创意表达",
                    f"从{style}视角看{prompt}"
                ],
                "generation_time": round(random.uniform(1.5, 6.0), 2),
                "content_length": len(content),
                "title": f"{prompt}的{style}创作"
            }
        }
        
        converted_logs.append(log_entry)
        
        # 进度显示
        if i % 10000 == 0 and i > 0:
            print(f"🔄 已处理 {i} 条数据...")
    
    # 保存转换后的数据
    with open(output_file, 'w', encoding='utf-8') as f:
        for log in converted_logs:
            f.write(json.dumps(log, ensure_ascii=False) + '\n')
    
    print(f"✅ ERNIE数据集预处理完成！共生成 {len(converted_logs)} 条日志")
    print(f"📁 输出文件: {output_file}")

if __name__ == "__main__":
    preprocess_ernie_dataset()
EOF

# 运行预处理脚本
cd $DATASET_DIR
python3 preprocess_ernie.py

if [ $? -eq 0 ] && [ -f "$PROCESSED_DATA_DIR/ernie_platform_logs.json" ]; then
    echo "✅ ERNIE数据集预处理成功"
    echo "🚀 现在可以运行: ./scripts/upload_to_hdfs.sh --import-ernie"
else
    echo "❌ ERNIE数据集预处理失败"
    exit 1
fi