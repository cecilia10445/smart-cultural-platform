import time
import os
import json
import jwt
import hmac
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from config import load_settings
except ImportError:
    from backend.config import load_settings

app = Flask(__name__)
CORS(app)

# JWT配置
settings = load_settings()
JWT_SECRET = settings.jwt_secret
JWT_ALGORITHM = settings.jwt_algorithm

# 设置项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = current_dir
project_root = os.path.dirname(backend_dir)
frontend_dir = os.path.join(project_root, "frontend")

print(f"📁 项目根目录: {project_root}")
print(f"📁 前端目录: {frontend_dir}")

# 用户数据加载函数
def load_users_data():
    """加载用户数据"""
    users_file = os.path.join(backend_dir, "data", "test_users.json")
    
    if os.path.exists(users_file):
        with open(users_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 创建默认用户数据
        default_users = {
            "users": [
                {"user_id": "U1001", "username": "user1", "password_hash": generate_password_hash("user1"), "role": "user", "name": "用户一", "age_range": "25-30", "gender": "female"},
                {"user_id": "U1002", "username": "user2", "password_hash": generate_password_hash("user2"), "role": "user", "name": "用户二", "age_range": "20-35", "gender": "female"},
                {"user_id": "U1003", "username": "user3", "password_hash": generate_password_hash("user3"), "role": "user", "name": "用户三", "age_range": "30-35", "gender": "male"}
            ],
            "admins": [
                {"user_id": "A2001", "username": "admin1", "password_hash": generate_password_hash("admin1"), "role": "admin", "name": "运营管理员", "age_range": "25-30", "gender": "female"}
            ]
        }
        
        # 确保数据目录存在
        os.makedirs(os.path.dirname(users_file), exist_ok=True)
        with open(users_file, 'w', encoding='utf-8') as f:
            json.dump(default_users, f, ensure_ascii=False, indent=2)
        
        return default_users


def save_users_data(data):
    """Atomically persist user data so password migration cannot leave partial JSON."""
    users_file = os.path.join(backend_dir, "data", "test_users.json")
    directory = os.path.dirname(users_file)
    fd, temporary_path = tempfile.mkstemp(dir=directory, prefix="test_users.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, users_file)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def verify_and_migrate_password(user, submitted_password):
    password_hash = user.get("password_hash")
    if password_hash:
        return check_password_hash(password_hash, submitted_password)

    legacy_password = user.get("password")
    if not isinstance(legacy_password, str) or not hmac.compare_digest(legacy_password, submitted_password):
        return False

    user["password_hash"] = generate_password_hash(submitted_password)
    user.pop("password", None)
    save_users_data(users_data)
    return True


def api_error(code, message, status_code, retryable=False, unavailable=False):
    return jsonify({
        "status": "unavailable" if unavailable else "error",
        "code": code,
        "message": message,
        "request_id": str(uuid.uuid4()),
        "retryable": retryable,
    }), status_code

# 加载用户数据
users_data = load_users_data()

# 认证函数定义
def authenticate_user():
    """验证用户身份"""
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.replace('Bearer ', '')
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        print("❌ Token已过期")
        return None
    except jwt.InvalidTokenError:
        print("❌ 无效的Token")
        return None
    except Exception as e:
        print(f"❌ Token验证错误: {e}")
        return None

# 导入服务（放在认证函数之后）
try:
    from backend.services.aigc_service import AIGCServiceError, generate_content
    print("✅ 成功导入AIGC服务")
except ImportError as e:
    raise RuntimeError("AIGC service could not be imported") from e
    print(f"⚠️ AIGC服务导入失败: {e}")
    
    # 降级方案
    class MockAIGCService:
        def generate_content(self, prompt, style):
            print(f"🎨 模拟生成: {prompt} - {style}")
            time.sleep(2)
            
            title = f"{prompt}的{style}之旅"[:10]
            content = f"在{style}的风格下，{prompt}展现出独特的魅力。这是一段精心创作的描述，希望能够激发您的想象力。"
            content = content[:100] + "..." if len(content) > 100 else content
            
            image_url = f"https://picsum.photos/512/512?random={int(time.time())}"
            return image_url, title, content
    
    aigc_service = MockAIGCService()
    
    def generate_content(prompt, style):
        return aigc_service.generate_content(prompt, style)

try:
    from backend.services.mysql_service import mysql_service
    print("✅ 成功导入MySQL服务")
except ImportError as e:
    print(f"⚠️ MySQL服务导入失败: {e}")
    mysql_service = None


# 导入Hive服务
try:
    from backend.services.hive_service import hive_service
    print("✅ 成功导入Hive服务")
except ImportError as e:
    print(f"⚠️ Hive服务导入失败: {e}")
    hive_service = None

# 导入日志服务
try:
    from backend.utils.logger import log_event
    print("✅ 成功导入日志服务")
except ImportError:
    print("⚠️ 使用简化日志服务")
    def log_event(event_type, data):
        timestamp = datetime.now().isoformat()
        print(f"📝 [{timestamp}] {event_type}: {data}")

# 路由定义
@app.route('/')
def home():
    """直接显示登录页面"""
    try:
        return send_from_directory(frontend_dir, 'login.html')
    except:
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>智能文创平台</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; }
                a { display: inline-block; margin: 10px; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; }
            </style>
        </head>
        <body>
            <h1>🎨 智能文创平台</h1>
            <p>请选择登录方式：</p>
            <a href="/login.html">用户/运营登录</a>
            <a href="/index.html">直接进入用户端</a>
            <a href="/dashboard.html">直接进入运营端</a>
        </body>
        </html>
        '''

@app.route('/<path:filename>')
def serve_static(filename):
    """服务前端静态文件"""
    try:
        # 处理根路径
        if filename == '' or filename == 'index.html':
            filename = 'index.html'
        
        # 处理可能的前缀
        if filename.startswith('frontend/'):
            filename = filename.replace('frontend/', '')
        
        file_path = os.path.join(frontend_dir, filename)
        
        print(f"📄 尝试访问文件: {filename}")
        print(f"📁 完整路径: {file_path}")
        
        if os.path.exists(file_path):
            return send_from_directory(frontend_dir, filename)
        else:
            print(f"❌ 文件不存在: {file_path}")
            return f'文件未找到: {filename}', 404
            
    except Exception as e:
        print(f"❌ 服务器错误: {e}")
        return f"服务器错误: {e}", 500

# 登录接口
@app.route('/api/login', methods=['POST'])
def login():
    """用户登录接口"""
    try:
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        role = data.get('role', 'user')
        
        
        if not username or not password:
            return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400
        
        # 查找用户（简化查找逻辑）
        user = None
        all_users = users_data.get('users', []) + users_data.get('admins', [])
        
        for u in all_users:
            if u['username'] == username and verify_and_migrate_password(u, password):
                user = u
                # 检查角色匹配
                if (role == 'admin' and u['role'] != 'admin') or (role == 'user' and u['role'] != 'user'):
                    return jsonify({'status': 'error', 'message': '角色选择错误'}), 401
                break
        
        if not user:
            print(f"❌ 用户验证失败: {username}")
            return jsonify({'status': 'error', 'message': '用户名或密码错误'}), 401
        
        # 更新最后登录时间
        user['last_login'] = datetime.now().isoformat()
        
        # 生成JWT token
        if not JWT_SECRET:
            return api_error("JWT_NOT_CONFIGURED", "Authentication service is not configured.", 503, unavailable=True)
        token_payload = {
            'user_id': user['user_id'],
            'username': user['username'],
            'role': user['role'],
            'exp': datetime.now(timezone.utc) + timedelta(days=1)
        }
        token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        # 返回用户信息（排除密码）
        user_info = user.copy()
        user_info.pop('password', None)
        user_info.pop('password_hash', None)
        
        print(f"✅ 登录成功: {username} ({user['name']}) 角色: {user['role']}")
        
        return jsonify({
            'status': 'success',
            'message': '登录成功',
            'token': token,
            'user': user_info
        })
        
    except Exception as e:
        return api_error("AUTH_PROCESSING_FAILED", "Login could not be completed.", 500)

@app.route('/api/register', methods=['POST'])
def register():
    """用户注册接口（支持普通用户和运营注册）"""
    try:
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        role = data.get('role', 'user').strip()  # 接收前端传递的角色
        name = data.get('name', username).strip()
        age_range = data.get('age_range', '25-30')  # 新增字段，默认值
        gender = data.get('gender', 'unknown')      # 新增字段，默认值

        # 基础校验
        if not username or len(username) < 3 or len(username) > 12:
            return jsonify({'status': 'error', 'message': '用户名需3-12位'}), 400
        if not password or len(password) < 6 or len(password) > 16:
            return jsonify({'status': 'error', 'message': '密码需6-16位'}), 400
        
        if role != 'user':
            return api_error("ADMIN_REGISTRATION_FORBIDDEN", "Public registration can only create user accounts.", 403)

        # 检查用户名是否已存在
        all_users = users_data.get('users', []) + users_data.get('admins', [])
        if any(u['username'] == username for u in all_users):
            return jsonify({'status': 'error', 'message': '用户名已存在'}), 409

        user_id = f"U{int(time.time()) % 1000000:06d}"

        # 创建新用户数据
        new_user = {
            'user_id': user_id,
            'username': username,
            'password_hash': generate_password_hash(password),
            'role': 'user',
            'name': name,
            'age_range': age_range,  # 新增
            'gender': gender,        # 新增
            'last_login': None,
            'created_at': datetime.now().isoformat()  # 新增创建时间
        }

        users_data['users'].append(new_user)

        save_users_data(users_data)

        return jsonify({'status': 'success', 'message': '注册成功'})

    except Exception as e:
        return api_error("REGISTRATION_FAILED", "Registration could not be completed.", 500)


# 内容生成接口（需要登录）
# 内容生成接口（需要登录）
@app.route('/api/generate', methods=['POST'])
def generate_content_api():
    """内容生成API - 需要登录"""
    # 验证用户身份
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    start_time = time.time()
    
    try:
        data = request.json
        prompt = data.get('prompt', '')
        style = data.get('style', 'general')
        
        print(f"🎯 用户 {user_info['username']} 生成请求: {prompt} - {style}")
        
        if not prompt:
            return jsonify({'status': 'error', 'message': '主题描述不能为空'}), 400
        
        # 调用AIGC服务生成图文
        try:
            image_url, title, content = generate_content(prompt, style)
        except AIGCServiceError as error:
            log_event('error', {'code': error.code, 'user_id': user_info.get('user_id')})
            return api_error(error.code, error.message, 502, error.retryable)
        generation_time = round(time.time() - start_time, 2)

        # ==================== 插入图片保存代码开始 ====================
        local_image_url = image_url  # 默认使用原始URL
        
        try:
            # 下载图片
            import requests
            response = requests.get(image_url, timeout=30)
            if response.status_code == 200:
                # 生成唯一文件名
                import hashlib
                filename_hash = hashlib.md5(f"{user_info['user_id']}_{prompt}_{int(time.time())}".encode()).hexdigest()[:10]
                local_filename = f"image_{filename_hash}.png"
                local_path = os.path.join(project_root, "static", "images", local_filename)
                
                # 确保目录存在
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                # 保存图片
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                
                # 使用本地路径
                local_image_url = f"/static/images/{local_filename}"
                print(f"✅ 图片已保存到本地: {local_path}")
                
            else:
                print(f"⚠️ 图片下载失败: {response.status_code}")
        except Exception as e:
            print(f"⚠️ 图片保存失败: {e}")
        # ==================== 插入图片保存代码结束 ====================

        # 获取用户完整信息（包含年龄性别）
        user_id = user_info['user_id']
        all_users = users_data['users'] + users_data['admins']
        user_data = next((u for u in all_users if u['user_id'] == user_id), None)

        # 记录日志 - 使用 local_image_url
        log_data = {
            'event_type': 'generate',
            'user_id': user_info['user_id'],
            'username': user_info['username'],
            'age_range': user_data.get('age_range', 'unknown') if user_data else 'unknown',
            'gender': user_data.get('gender', 'unknown') if user_data else 'unknown',
            'prompt': prompt,
            'style': style,
            'image_url': local_image_url,  # 使用本地路径
            'title': title,
            'content': content,
            'generation_time': generation_time,
            'content_length': len(content),
            'timestamp': datetime.now().isoformat(),
            'login_time': user_data.get('last_login') if user_data else None,
            'user_rating': None,
            'download_count': 0
        }
        log_event('generate', log_data)

        # 只在生成时插入MySQL记录，其他事件只更新
        if mysql_service is None or not mysql_service.connect():
            log_event('error', {'code': 'MYSQL_UNAVAILABLE', 'user_id': user_info.get('user_id')})
            return api_error("MYSQL_UNAVAILABLE", "Data service is temporarily unavailable.", 503, True, True)

        mysql_record_id = None
        if mysql_service and mysql_service.connect():
            try:
                # 检查是否已存在相同记录
                check_query = """
                SELECT id FROM generation_logs 
                WHERE user_id = %s AND prompt = %s AND style = %s 
                AND timestamp >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
                ORDER BY timestamp DESC LIMIT 1
                """
                existing_record = mysql_service.execute_query(check_query, (user_id, prompt, style))
                
                if not existing_record:
                    # 插入新记录 - 使用 local_image_url
                    insert_query = """
                    INSERT INTO generation_logs 
                    (user_id, event_type, timestamp, prompt, style, image_url, title, content, 
                     generation_time, content_length, user_rating, download_count, user_age, user_gender, login_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    insert_params = (
                        user_id,
                        'generate',
                        datetime.now().isoformat(),
                        prompt,
                        style,
                        local_image_url,  # 使用本地路径
                        title,
                        content,
                        generation_time,
                        len(content),
                        None,
                        0,
                        int(user_data.get('age_range', '25-30').split('-')[0]) if user_data and user_data.get('age_range') else 25,
                        1 if user_data and user_data.get('gender') == 'male' else 0 if user_data and user_data.get('gender') == 'female' else 2,
                        user_data.get('last_login') if user_data else None
                    )
                    
                    result = mysql_service.execute_query(insert_query, insert_params)
                    if result is not None:
                        print(f"✅ 成功保存生成记录到MySQL: {user_id}")
                    else:
                        print(f"⚠️ 保存到MySQL失败，但继续流程")
                else:
                    print(f"ℹ️ 已存在相似记录，跳过重复插入: {user_id}")
                    
            except Exception as e:
                print(f"⚠️ 保存到MySQL失败: {e}")
        
        # 返回给前端的也使用本地路径
        return jsonify({
            'image_url': local_image_url,  # 使用本地路径
            'title': title,
            'content': content,
            'generation_time': generation_time,
            'log_id': f"log_{int(time.time())}_{user_id}",
            'status': 'success'
        })
    
    except Exception as e:
        error_msg = f"API处理错误: {e}"
        print(f"❌ {error_msg}")
        log_event('error', {'error': error_msg, 'user_id': user_info.get('user_id')})
        return jsonify({'status': 'error', 'message': error_msg}), 500

# 运营数据接口（需要管理员权限）
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """运营数据统计API - 需要管理员权限"""
    # 验证用户身份和权限
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    if user_info.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': '无权限访问运营数据'}), 403
    
    try:
        # 获取日期范围参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        print(f"📊 请求统计日期范围: {start_date} 到 {end_date}")

        # 优先使用MySQL服务
        if mysql_service is not None:
            print("📊 从MySQL获取运营数据...")
            stats = mysql_service.get_dashboard_stats(start_date, end_date)
            
            if stats is not None:
                print("✅ 成功从MySQL获取运营数据")
                return jsonify({
                    'status': 'success',
                    'data': {
                        'stats': stats,
                        'dataSource': 'MySQL'
                    }
                })
        
        # MySQL不可用时使用Hive服务
        if hive_service is not None:
            print("📊 从Hive获取运营数据...")
            stats = hive_service.get_dashboard_stats()
            
            if stats is not None:
                print("✅ 成功从Hive获取运营数据")
                return jsonify({
                    'status': 'success',
                    'data': {
                        'stats': stats,
                        'dataSource': 'Hive'
                    }
                })

        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)
         
        # 若MySQL和Hive服务均不可用或未获取到有效数据，返回服务不可用错误
        print("⚠️ MySQL和Hive服务均不可用或未获取到有效数据")
        return jsonify({
            'status': 'error', 
            'message': '数据服务暂时不可用，请稍后重试'
        }), 503
        
    except Exception as e:
        print(f"❌ 获取运营数据失败: {e}")
        return jsonify({
            'status': 'error', 
            'message': f'数据查询失败: {str(e)}'
        }), 500

# 用户信息接口
@app.route('/api/user/profile', methods=['GET'])
def get_user_profile():
    """获取当前用户信息"""
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    # 从用户数据中获取完整信息
    user_id = user_info['user_id']
    all_users = users_data['users'] + users_data['admins']
    user_data = next((u for u in all_users if u['user_id'] == user_id), None)
    
    if user_data:
        # 移除密码
        user_data = user_data.copy()
        user_data.pop('password', None)
        user_data.pop('password_hash', None)
        return jsonify({'status': 'success', 'user': user_data})
    else:
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404

@app.route('/api/user/history', methods=['GET'])
def get_user_history():
    """获取用户历史记录"""
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    try:
        user_id = user_info['user_id']
        
        # 优先使用MySQL服务
        if mysql_service is not None:
            print(f"📜 从MySQL获取用户历史记录: {user_id}")
            history_data = mysql_service.get_user_history(user_id)
            if history_data is not None:
                return jsonify({
                    'status': 'success',
                    'data': history_data,
                    'dataSource': 'MySQL'
                })
            else:
                print(f"⚠️ MySQL查询返回None，用户: {user_id}")
        # MySQL不可用时使用Hive服务
        if hive_service is not None:
            print(f"📜 从Hive获取用户历史记录: {user_id}")
            history_data = hive_service.get_user_history(user_id)
            if history_data is not None:
                return jsonify({
                    'status': 'success',
                    'data': history_data,
                    'dataSource': 'Hive'
                })

        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)
         
        # 两个服务都不可用时返回空数据
        return jsonify({
            'status': 'success',
            'data': [],
            'message': '暂无历史记录'
        })
        
    except Exception as e:
        print(f"❌ 获取用户历史记录失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取历史记录失败: {str(e)}'
        }), 500


@app.route('/api/rating', methods=['POST'])
def submit_rating():
    """提交用户评分"""
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    try:
        data = request.json
        rating = data.get('rating')
        prompt = data.get('prompt')
        style = data.get('style')
        
        if not rating or rating < 1 or rating > 5:
            return jsonify({'status': 'error', 'message': '评分必须在1-5之间'}), 400
        
        # 获取用户完整信息（包含年龄性别）
        user_id = user_info['user_id']
        all_users = users_data['users'] + users_data['admins']
        user_data = next((u for u in all_users if u['user_id'] == user_id), None)
        
        if not user_data:
            return jsonify({'status': 'error', 'message': '用户不存在'}), 404
        
        # 记录评分日志 - 包含完整的用户信息
        log_data = {
            'event_type': 'rating',
            'user_id': user_id,
            'username': user_info['username'],
            'age_range': user_data.get('age_range', 'unknown'),
            'gender': user_data.get('gender', 'unknown'),
            'rating': rating,
            'prompt': prompt,
            'style': style,
            'timestamp': datetime.now().isoformat(),
            'login_time': user_data.get('last_login')
        }
        log_event('rating', log_data)
        
        # 更新MySQL中的评分（如果MySQL服务可用）
        if mysql_service and mysql_service.connect():
            try:
                update_rating_query = """
                UPDATE generation_logs 
                SET user_rating = %s 
                WHERE user_id = %s AND prompt = %s AND style = %s
                ORDER BY timestamp DESC LIMIT 1
                """
                result = mysql_service.execute_query(update_rating_query, (rating, user_id, prompt, style))
                if result is not None:
                    print(f"✅ 成功更新评分到MySQL: {user_id} - 评分: {rating}")
                else:
                    print(f"⚠️ 更新评分到MySQL失败")
            except Exception as e:
                print(f"⚠️ 更新评分到MySQL失败: {e}")
        
        return jsonify({
            'status': 'success',
            'message': '评分提交成功',
            'rating': rating
        })
        
    except Exception as e:
        print(f"❌ 评分提交失败: {e}")
        return jsonify({'status': 'error', 'message': f'评分失败: {str(e)}'}), 500


@app.route('/api/download', methods=['POST'])
def record_download():
    """记录图片下载"""
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    try:
        data = request.json
        image_url = data.get('image_url')
        prompt = data.get('prompt')
        style = data.get('style')
        
        # 获取用户完整信息
        user_id = user_info['user_id']
        all_users = users_data['users'] + users_data['admins']
        user_data = next((u for u in all_users if u['user_id'] == user_id), None)
        
        # 记录下载日志 - 包含完整的用户信息
        log_data = {
            'event_type': 'download',  # 明确的事件类型
            'user_id': user_id,
            'username': user_info['username'],
            'age_range': user_data.get('age_range', 'unknown') if user_data else 'unknown',
            'gender': user_data.get('gender', 'unknown') if user_data else 'unknown',
            'image_url': image_url,
            'prompt': prompt,
            'style': style,
            'timestamp': datetime.now().isoformat(),
            'login_time': user_data.get('last_login') if user_data else None,
            'download_count': 1  # 下载次数
        }
        log_event('download', log_data)
        # 更新MySQL中的下载次数（如果MySQL服务可用）
        if mysql_service and mysql_service.connect():
            try:
                update_download_query = """
                UPDATE generation_logs 
                SET download_count = download_count + 1 
                WHERE user_id = %s AND prompt = %s AND style = %s
                ORDER BY timestamp DESC LIMIT 1
                """
                result = mysql_service.execute_query(update_download_query, (user_id, prompt, style))
                if result is not None:
                    print(f"✅ 成功更新下载次数到MySQL: {user_id}")
                else:
                    print(f"⚠️ 更新下载次数到MySQL失败")
            except Exception as e:
                print(f"⚠️ 更新下载次数到MySQL失败: {e}")
        return jsonify({
            'status': 'success',
            'message': '下载记录成功'
        })
        
    except Exception as e:
        print(f"❌ 下载记录失败: {e}")
        return jsonify({'status': 'error', 'message': f'记录失败: {str(e)}'}), 500

@app.route('/static/images/<filename>')
def serve_static_images(filename):
    """服务本地静态图片"""
    static_dir = os.path.join(project_root, "static", "images")
    return send_from_directory(static_dir, filename)


# ==============================================
# 新增推荐和趋势分析接口
# ==============================================

# ==============================================
# 新增接口
# ==============================================

@app.route('/api/dashboard/user-profile')
def get_user_profile_dashboard():
    """获取用户画像仪表盘数据"""
    # 验证用户身份和权限
    user_info = authenticate_user()
    if not user_info:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401
    
    if user_info.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': '无权限访问运营数据'}), 403
    
    try:
        # 获取日期范围参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        print(f"📅 请求日期范围: {start_date} 到 {end_date}")

        # 优先使用MySQL服务
        if mysql_service is not None:
            print("👥 从MySQL获取用户画像数据...")
            user_profile_data = mysql_service.get_user_profile_dashboard(start_date, end_date)
            
            if user_profile_data is not None:
                print("✅ 成功从MySQL获取用户画像数据")
                return jsonify({
                    'status': 'success',
                    'data': user_profile_data,
                    'dataSource': 'MySQL'
                })
        
        # MySQL不可用时使用Hive服务
        if hive_service is not None:
            print("👥 从Hive获取用户画像数据...")
            user_profile_data = hive_service.get_user_profile_dashboard()
            
            if user_profile_data is not None:
                print("✅ 成功从Hive获取用户画像数据")
                return jsonify({
                    'status': 'success',
                    'data': user_profile_data,
                    'dataSource': 'Hive'
                })

        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)
         
        # 若MySQL和Hive服务均不可用，返回降级数据
        print("⚠️ MySQL和Hive服务均不可用，使用模拟用户画像数据")
        return jsonify({
            'status': 'success',
            'data': get_fallback_user_profile_data(),
            'dataSource': '模拟数据'
        })
        
    except Exception as e:
        print(f"❌ 获取用户画像数据失败: {e}")
        return jsonify({
            'status': 'success',
            'data': get_fallback_user_profile_data(),
            'message': '使用模拟数据：' + str(e),
            'dataSource': '模拟数据'
        }), 500  

def get_fallback_user_profile_data():
    """降级用户画像数据"""
    return {
        'stats': {
            'totalUsers': 3449,
            'totalGenerations': 12567,
            'activeUsers': 2890,
            'avgRating': 4.2
        },
        'age_distribution': [
            {'age_range': '1', 'count': 120, 'percentage': 3.5},
            {'age_range': '2', 'count': 850, 'percentage': 24.6},
            {'age_range': '3', 'count': 980, 'percentage': 28.4},
            {'age_range': '4', 'count': 720, 'percentage': 20.9},
            {'age_range': '5', 'count': 450, 'percentage': 13.0},
            {'age_range': '6', 'count': 200, 'percentage': 5.8},
            {'age_range': '7', 'count': 89, 'percentage': 2.6},
            {'age_range': '0', 'count': 40, 'percentage': 1.2}
        ],
        'gender_distribution': [
            {'gender': 'female', 'count': 1850, 'percentage': 53.6},
            {'gender': 'male', 'count': 1420, 'percentage': 41.2},
            {'gender': 'unknown', 'count': 179, 'percentage': 5.2}
        ],
        'active_period_distribution': [
            {'period': '深夜党', 'count': 450, 'percentage': 13.0},
            {'period': '上午党', 'count': 980, 'percentage': 28.4},
            {'period': '下午党', 'count': 1250, 'percentage': 36.2},
            {'period': '晚间党', 'count': 769, 'percentage': 22.3}
        ],
        'user_behavior_7days': {
            'labels': ['10-01', '10-02', '10-03', '10-04', '10-05', '10-06', '10-07'],
            'generation_data': [1560, 1420, 1680, 1750, 1890, 1620, 1780],
            'download_data': [890, 820, 950, 1020, 1100, 920, 980]
        },
        'style_popularity': [
            {'style': '赛博朋克', 'usage_count': 2560},
            {'style': '水彩画风', 'usage_count': 2340},
            {'style': '极简主义', 'usage_count': 1980},
            {'style': '复古风格', 'usage_count': 1760},
            {'style': '未来科技', 'usage_count': 1650},
            {'style': '自然风光', 'usage_count': 1520},
            {'style': '抽象艺术', 'usage_count': 1380},
            {'style': '卡通动漫', 'usage_count': 1250},
            {'style': '写实风格', 'usage_count': 1120},
            {'style': '梦幻唯美', 'usage_count': 980}
        ],
        'rating_distribution': [
            {'rating': 1, 'count': 120},
            {'rating': 2, 'count': 280},
            {'rating': 3, 'count': 1560},
            {'rating': 4, 'count': 3240},
            {'rating': 5, 'count': 2367}
        ],
        'style_trend_30days': {
            'labels': ['09-08', '09-09', '09-10', '09-11', '09-12', '09-13', '09-14', '09-15', '09-16', '09-17', 
                      '09-18', '09-19', '09-20', '09-21', '09-22', '09-23', '09-24', '09-25', '09-26', '09-27',
                      '09-28', '09-29', '09-30', '10-01', '10-02', '10-03', '10-04', '10-05', '10-06', '10-07'],
            'datasets': [
                {
                    'label': '赛博朋克',
                    'data': [65, 70, 68, 72, 75, 78, 80, 82, 85, 88, 90, 92, 95, 98, 100, 105, 108, 110, 112, 115, 118, 120, 122, 125, 128, 130, 132, 135, 138, 140]
                },
                {
                    'label': '水彩画风',
                    'data': [55, 58, 60, 62, 65, 68, 70, 72, 75, 78, 80, 82, 85, 88, 90, 92, 95, 98, 100, 102, 105, 108, 110, 112, 115, 118, 120, 122, 125, 128]
                },
                {
                    'label': '极简主义',
                    'data': [45, 48, 50, 52, 55, 58, 60, 62, 65, 68, 70, 72, 75, 78, 80, 82, 85, 88, 90, 92, 95, 98, 100, 102, 105, 108, 110, 112, 115, 118]
                }
            ]
        },
        'generation_efficiency': [
            {'time_range': '0-5秒', 'count': 1560},
            {'time_range': '5-10秒', 'count': 2340},
            {'time_range': '10-30秒', 'count': 1890},
            {'time_range': '30-60秒', 'count': 980},
            {'time_range': '60秒以上', 'count': 450}
        ],
        'hot_keywords': [
            {'keyword': '夏日', 'frequency': 256, 'trend': [45, 48, 52, 55, 58, 62, 65]},
            {'keyword': '星空', 'frequency': 234, 'trend': [42, 45, 48, 50, 52, 55, 58]},
            {'keyword': '未来', 'frequency': 198, 'trend': [38, 40, 42, 45, 48, 50, 52]},
            {'keyword': '城市', 'frequency': 176, 'trend': [35, 38, 40, 42, 45, 48, 50]},
            {'keyword': '自然', 'frequency': 165, 'trend': [32, 35, 38, 40, 42, 45, 48]},
            {'keyword': '科技', 'frequency': 152, 'trend': [30, 32, 35, 38, 40, 42, 45]},
            {'keyword': '艺术', 'frequency': 138, 'trend': [28, 30, 32, 35, 38, 40, 42]},
            {'keyword': '梦想', 'frequency': 125, 'trend': [25, 28, 30, 32, 35, 38, 40]},
            {'keyword': '海洋', 'frequency': 112, 'trend': [22, 25, 28, 30, 32, 35, 38]},
            {'keyword': '森林', 'frequency': 98, 'trend': [20, 22, 25, 28, 30, 32, 35]}
        ]
    }














# ==============================================
# 新增接口结束
# ==============================================


@app.route('/api/recommendations/personalized')
def get_personalized_recommendations():
    """获取个性化推荐（用户端）"""
    try:
        # 获取当前登录用户
        user_info = authenticate_user()
        if not user_info:
            return jsonify({'status': 'error', 'message': '请先登录'}), 401
            
        user_id = user_info.get('user_id')
        limit = request.args.get('limit', 8, type=int)
        
        if not user_id:
            return jsonify({'status': 'error', 'message': '用户ID不存在'}), 400
        
        print(f"🎯 为用户 {user_id} 获取个性化推荐")
        
        # 优先使用MySQL服务
        if mysql_service is not None:
            trending_data = mysql_service.get_personalized_recommendations(user_id, limit)
            if trending_data:
                return jsonify({
                    'status': 'success',
                    'data': trending_data,
                    'dataSource': 'MySQL'
                })
        
        # MySQL不可用时使用Hive服务
        if hive_service is not None:
            trending_data = hive_service.get_personalized_recommendations(user_id, limit)
            if trending_data:
                return jsonify({
                    'status': 'success',
                    'data': trending_data,
                    'dataSource': 'Hive'
                })

        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)
         
        # 两个服务都不可用时使用模拟数据
        return jsonify({
            'status': 'success',
            'data': {
                'style_recommendations': [
                    {'style': '赛博朋克', 'score': 0.95, 'reason': '同类型用户偏好'},
                    {'style': '水彩画风', 'score': 0.88, 'reason': '同类型用户偏好'}
                ],
                'hot_keywords': [
                    {'keyword': '夏日', 'frequency': 256, 'hot_score': 92, 'type': '全网热门'},
                    {'keyword': '星空', 'frequency': 234, 'hot_score': 87, 'type': '全网热门'}
                ]
            },
            'dataSource': '模拟数据'
        })
        
    except Exception as e:
        print(f"❌ 获取热门推荐失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取热门推荐失败: {str(e)}'
        }), 500

# ==============================================
# 新增接口结束
# ==============================================


# 健康检查接口
@app.route('/api/health')
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': '智能文创平台后端'
    })

if __name__ == '__main__':
    print("🚀 启动智能文创平台后端服务...")
    print("📍 访问地址:")
    print("   - 首页: http://localhost:5000/")
    print("   - 登录页: http://localhost:5000/login.html")
    print("   - 用户端: http://localhost:5000/index.html")
    print("   - 运营端: http://localhost:5000/dashboard.html")
    print("   - API健康检查: http://localhost:5000/api/health")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
