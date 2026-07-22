import json
from datetime import datetime
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(backend_dir)

LOG_DIR = os.path.join(project_root, "data", "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
SENSITIVE_KEYS = {"password", "password_hash", "token", "jwt", "authorization", "api_key", "dashscope_api_key"}


def sanitize_data(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else sanitize_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_data(item) for item in value]
    return value

def log_event(event_type, data):
    """记录用户行为日志"""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,  # generate/edit/rate/save
        "user_id": data.get('user_id', 'anonymous'),  # 后续接入用户系统
        "session_id": data.get('session_id', ''),
        "data": sanitize_data(data)
    }
    
    try:
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        code = data.get("code")
        stage = data.get("stage")
        summary = f" event={event_type}"
        if code:
            summary += f" code={code}"
        if stage:
            summary += f" stage={stage}"
        print(f"✅ 日志记录成功:{summary}")
        return True
    except Exception as e:
        print(f"❌ 日志记录失败: {e}")
        return False

def log_generation(user_id, prompt, style, image_url, captions, generation_time):
    """专门记录生成行为的日志"""
    data = {
        'user_id': user_id,
        'prompt': prompt,
        'style': style,
        'image_url': image_url,
        'captions': captions,
        'generation_time': generation_time,  # 生成耗时
        'content_length': sum(len(caption) for caption in captions)  # 内容长度
    }
    return log_event('generate', data)

def log_rating(user_id, content_id, rating):
    """记录用户评分"""
    data = {
        'user_id': user_id,
        'content_id': content_id,
        'rating': rating
    }
    return log_event('rate', data)
