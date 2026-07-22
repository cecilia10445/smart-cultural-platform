import time
import os
import json
import jwt
import hmac
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, g, jsonify, request, send_from_directory
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
REAL_BUSINESS_SMOKE_DATABASE = "aigc_platform_demo"

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


def current_request_id():
    if not hasattr(g, "api_request_id"):
        g.api_request_id = str(uuid.uuid4())
    return g.api_request_id


def api_error(code, message, status_code, retryable=False, unavailable=False):
    return jsonify({
        "status": "unavailable" if unavailable else "error",
        "code": code,
        "message": message,
        "request_id": current_request_id(),
        "retryable": retryable,
    }), status_code


def log_generation_failure(user_id, stage, code, error=None):
    """Record only stable, non-content diagnostics for a generation failure."""
    image_stage = stage in {"image_generation", "image_download"}
    payload = {
        "user_id": user_id,
        "request_id": current_request_id(),
        "code": code,
        "stage": stage,
        "model_name": getattr(aigc_service, "image_model" if image_stage else "text_model", None),
        "endpoint_path": "/api/v1/services/aigc/multimodal-generation/generation" if image_stage else "/responses",
    }
    if error is not None:
        payload["timeout_stage"] = error.timeout_stage
        payload["provider_http_status"] = error.http_status
        payload["provider_error_code"] = error.provider_error_code
    log_event("error", payload)


def public_model_error_message(code):
    if code in {"MODEL_CONNECT_TIMEOUT", "MODEL_READ_TIMEOUT", "MODEL_REQUEST_TIMEOUT"}:
        return "Generation service did not respond in time."
    if code == "MODEL_RATE_LIMITED":
        return "Generation service is temporarily busy."
    if code == "MODEL_CONTENT_FILTERED":
        return "Generation request could not be processed under content policy."
    return "Generation service could not complete the request."


def v2_generation_data_origin(user_info):
    """Choose the persisted origin on the server; clients cannot supply it.

    The explicit smoke flag is intentionally narrow: it only marks a request
    as test data when the process targets the dedicated local demo database
    and the authenticated principal is the configured smoke identity.
    """
    username = user_info.get("username")
    is_controlled_smoke = (
        settings.run_real_business_smoke
        and settings.mysql_database == REAL_BUSINESS_SMOKE_DATABASE
        and bool(settings.smoke_test_username)
        and bool(settings.smoke_test_password)
        and isinstance(username, str)
        and hmac.compare_digest(username, settings.smoke_test_username)
    )
    return "test" if is_controlled_smoke else "production"

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
    from backend.services.aigc_service import AIGCServiceError, aigc_service, generate_content
    print("✅ 成功导入AIGC服务")
except ImportError as e:
    raise RuntimeError("AIGC service could not be imported") from e

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

from backend.domain.cultural_product_brief import BriefValidationError, canonical_brief_json, validate_cultural_product_request
from backend.prompts.cultural_product_v1 import PROMPT_TEMPLATE_VERSION, build_image_prompt, factual_background
from backend.services.image_storage import ImagePersistenceError, persist_generated_image, remove_persisted_image
from backend.services.generation_tracking import GenerationTracker, TrackingPersistenceError

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
        
        if not prompt:
            return jsonify({'status': 'error', 'message': '主题描述不能为空'}), 400

        print(f"🎯 用户 {user_info['username']} 提交生成请求，风格: {style}")

        # 在调用可计费模型前检查业务数据库是否可用。
        if mysql_service is None or not mysql_service.connect():
            log_event('error', {'code': 'MYSQL_UNAVAILABLE', 'user_id': user_info.get('user_id')})
            return api_error("MYSQL_UNAVAILABLE", "Data service is temporarily unavailable.", 503, True, True)
        
        # 调用AIGC服务生成图文
        try:
            image_url, title, content = generate_content(prompt, style)
        except AIGCServiceError as error:
            log_event('error', {'code': error.code, 'user_id': user_info.get('user_id')})
            return api_error(error.code, error.message, 502, error.retryable)
        generation_time = round(time.time() - start_time, 2)

        try:
            local_image_url = persist_generated_image(image_url, os.path.join(project_root, "static", "images"))
        except ImagePersistenceError:
            log_event('error', {'code': 'IMAGE_PERSIST_FAILED', 'user_id': user_info.get('user_id')})
            return api_error("IMAGE_PERSIST_FAILED", "Generated image could not be saved.", 502, True)

        # 获取用户完整信息（包含年龄性别）
        user_id = user_info['user_id']
        all_users = users_data['users'] + users_data['admins']
        user_data = next((u for u in all_users if u['user_id'] == user_id), None)

        # 准备本地日志；只有 MySQL 真实落库后才记录生成成功。
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
        age_value = None
        age_range = user_data.get('age_range') if user_data else None
        if isinstance(age_range, str):
            try:
                age_value = int(age_range.split('-', 1)[0])
            except (TypeError, ValueError):
                age_value = None

        gender = user_data.get('gender') if user_data else None
        gender_value = 1 if gender == 'male' else 0 if gender == 'female' else None

        insert_query = """
        INSERT INTO generation_logs
        (user_id, event_type, timestamp, prompt, style, image_url, title, content,
         generation_time, content_length, user_rating, download_count, user_age, user_gender,
         login_time, data_origin)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        insert_params = (
            user_id,
            'generate',
            datetime.now().isoformat(),
            prompt,
            style,
            local_image_url,
            title,
            content,
            generation_time,
            len(content),
            None,
            0,
            age_value,
            gender_value,
            user_data.get('last_login') if user_data else None,
            'production',
        )

        try:
            mysql_record_id = mysql_service.execute_insert(insert_query, insert_params)
        except Exception:
            mysql_record_id = None

        if mysql_record_id is None:
            if not remove_persisted_image(local_image_url, os.path.join(project_root, "static", "images")):
                log_event('error', {'code': 'ORPHAN_IMAGE_CLEANUP_FAILED', 'user_id': user_id})
            log_event('error', {'code': 'GENERATION_PERSIST_FAILED', 'user_id': user_id})
            return api_error(
                "GENERATION_PERSIST_FAILED",
                "Generated content could not be persisted.",
                503,
                True,
                True,
            )

        log_event('generate', log_data)
        print(f"✅ 成功保存生成记录到MySQL: {user_id}")
        
        # 返回给前端的也使用本地路径
        return jsonify({
            'image_url': local_image_url,  # 使用本地路径
            'title': title,
            'content': content,
            'generation_time': generation_time,
            'log_id': mysql_record_id,
            'status': 'success'
        })
    
    except Exception as e:
        error_msg = f"API处理错误: {e}"
        print(f"❌ {error_msg}")
        log_event('error', {'error': error_msg, 'user_id': user_info.get('user_id')})
        return jsonify({'status': 'error', 'message': error_msg}), 500


@app.route('/api/v2/cultural-products/generate', methods=['POST'])
def generate_cultural_product_api():
    """Versioned cultural-product workflow; legacy /api/generate remains unchanged."""
    user_info = authenticate_user()
    if not user_info:
        return api_error("AUTH_REQUIRED", "Please sign in before generating.", 401)
    try:
        brief = validate_cultural_product_request(request.get_json(silent=True))
    except BriefValidationError as error:
        return api_error(error.code, error.message, 400)

    if mysql_service is None or not mysql_service.connect():
        log_generation_failure(user_info.get("user_id"), "persistence", "MYSQL_UNAVAILABLE")
        return api_error("MYSQL_UNAVAILABLE", "Data service is temporarily unavailable.", 503, True, True)

    data_origin = v2_generation_data_origin(user_info)
    try:
        tracker = GenerationTracker(mysql_service, current_request_id(), user_info["user_id"], data_origin, brief, PROMPT_TEMPLATE_VERSION)
        tracker.start()
    except TrackingPersistenceError as error:
        log_generation_failure(user_info.get("user_id"), "persistence", str(error))
        return api_error(str(error), "Generation tracking is temporarily unavailable.", 503, True, True)

    def finish_tracking_failure(stage, code):
        """Best-effort finalization: never replace the original business error."""
        try:
            tracker.fail(stage, code)
        except TrackingPersistenceError:
            log_generation_failure(user_info.get("user_id"), "persistence", "TRACKING_FINALIZE_FAILED")

    started_at = time.time()
    text_started = time.perf_counter()
    try:
        if hasattr(aigc_service, "generate_cultural_product_text_with_metadata"):
            text_result, text_usage = aigc_service.generate_cultural_product_text_with_metadata(brief)
        else:
            text_result, text_usage = aigc_service.generate_cultural_product_text(brief), None
        tracker.record_metric("text_generation", getattr(aigc_service, "text_model", None), "SUCCEEDED", text_started, usage=text_usage)
    except AIGCServiceError as error:
        stage = "text_parse" if error.code in {
            "MODEL_EMPTY_RESPONSE", "MODEL_INVALID_RESPONSE", "MODEL_RESPONSE_INCOMPLETE", "MODEL_RESPONSE_REASONING_ONLY",
        } else "text_generation"
        try:
            tracker.record_metric("text_generation", getattr(aigc_service, "text_model", None), "FAILED", text_started, error=error)
            finish_tracking_failure(stage, error.code)
        except TrackingPersistenceError:
            finish_tracking_failure("persistence", "TRACKING_METRIC_PERSIST_FAILED")
        log_generation_failure(user_info.get("user_id"), stage, error.code, error)
        return api_error(error.code, public_model_error_message(error.code), 502, error.retryable)
    except TrackingPersistenceError as error:
        finish_tracking_failure("persistence", str(error))
        return api_error(str(error), "Generation tracking is temporarily unavailable.", 503, True, True)
    except Exception:
        finish_tracking_failure("text_generation", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        log_generation_failure(user_info.get("user_id"), "text_generation", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        return api_error("CULTURAL_PRODUCT_UNEXPECTED_ERROR", "Cultural product generation could not be completed.", 500)
    image_prompt = build_image_prompt(brief, text_result['product_name'])
    image_started = time.perf_counter()
    try:
        provider_image_url = aigc_service.generate_image_from_prompt(image_prompt)
        tracker.record_metric("image_generation", getattr(aigc_service, "image_model", None), "SUCCEEDED", image_started, image_count=1)
    except AIGCServiceError as error:
        try:
            tracker.record_metric("image_generation", getattr(aigc_service, "image_model", None), "FAILED", image_started, error=error)
            finish_tracking_failure("image_generation", error.code)
        except TrackingPersistenceError:
            finish_tracking_failure("persistence", "TRACKING_METRIC_PERSIST_FAILED")
        log_generation_failure(user_info.get("user_id"), "image_generation", error.code, error)
        return api_error(error.code, public_model_error_message(error.code), 502, error.retryable)
    except TrackingPersistenceError as error:
        finish_tracking_failure("persistence", str(error))
        return api_error(str(error), "Generation tracking is temporarily unavailable.", 503, True, True)
    except Exception:
        finish_tracking_failure("image_generation", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        log_generation_failure(user_info.get("user_id"), "image_generation", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        return api_error("CULTURAL_PRODUCT_UNEXPECTED_ERROR", "Cultural product generation could not be completed.", 500)
    try:
        image_url = persist_generated_image(provider_image_url, os.path.join(project_root, "static", "images"))
    except ImagePersistenceError:
        finish_tracking_failure("image_download", "IMAGE_PERSIST_FAILED")
        log_generation_failure(user_info.get("user_id"), "image_download", "IMAGE_PERSIST_FAILED")
        return api_error("IMAGE_PERSIST_FAILED", "Generated image could not be saved.", 502, True)
    except Exception:
        finish_tracking_failure("persistence", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        log_generation_failure(user_info.get("user_id"), "persistence", "CULTURAL_PRODUCT_UNEXPECTED_ERROR")
        return api_error("CULTURAL_PRODUCT_UNEXPECTED_ERROR", "Cultural product generation could not be completed.", 500)

    factual = factual_background(brief)
    response_data = {
        'status': 'success',
        'generation_kind': 'cultural_product',
        'prompt_template_version': PROMPT_TEMPLATE_VERSION,
        'product_name': text_result['product_name'],
        'factual_background': factual,
        'design_interpretation': text_result['design_interpretation'],
        'product_copy': text_result['product_copy'],
        'image_prompt': image_prompt,
        'image_url': image_url,
        'generation_time': round(time.time() - started_at, 2),
    }
    direction = brief['visual_direction']
    style = '；'.join(value for value in (
        direction['cultural_context'], direction['medium'], direction['palette'], direction['composition'], direction['additional_requirements'],
    ) if value)
    source = brief['cultural_source']
    prompt_summary = f"{brief['product_type']}：{source['name']}"
    user_id = user_info['user_id']
    user_data = next((item for item in users_data['users'] + users_data['admins'] if item['user_id'] == user_id), None)
    age_range = user_data.get('age_range') if user_data else None
    try:
        age_value = int(age_range.split('-', 1)[0]) if isinstance(age_range, str) else None
    except ValueError:
        age_value = None
    gender_value = 1 if user_data and user_data.get('gender') == 'male' else 0 if user_data and user_data.get('gender') == 'female' else None
    insert_query = """
        INSERT INTO generation_logs
        (user_id, event_type, timestamp, prompt, style, image_url, title, content, generation_time,
         content_length, user_rating, download_count, user_age, user_gender, login_time, data_origin,
         generation_kind, prompt_template_version, brief_json, response_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        log_id = mysql_service.execute_insert(insert_query, (
            user_id, 'generate', datetime.now().isoformat(), prompt_summary, style, image_url,
            text_result['product_name'], text_result['product_copy'], response_data['generation_time'],
            len(text_result['product_copy']), None, 0, age_value, gender_value,
            user_data.get('last_login') if user_data else None, data_origin, 'cultural_product',
            PROMPT_TEMPLATE_VERSION, canonical_brief_json(brief), json.dumps(response_data, ensure_ascii=False, separators=(',', ':')),
        ))
    except Exception:
        log_id = None
    if log_id is None:
        if not remove_persisted_image(image_url, os.path.join(project_root, "static", "images")):
            log_generation_failure(user_id, "persistence", "ORPHAN_IMAGE_CLEANUP_FAILED")
        log_generation_failure(user_id, "persistence", "GENERATION_PERSIST_FAILED")
        finish_tracking_failure("persistence", "GENERATION_PERSIST_FAILED")
        return api_error("GENERATION_PERSIST_FAILED", "Generated content could not be persisted.", 503, True, True)
    try:
        tracker.succeed(log_id)
    except TrackingPersistenceError as error:
        log_generation_failure(user_id, "persistence", str(error))
        # The user-visible generation is already durable.  Do not turn it into
        # a retryable failure and accidentally create a duplicate generation.
        # The attempt remains RUNNING and is reported as tracking-incomplete.
    response_data['log_id'] = log_id
    response_data['request_id'] = current_request_id()
    log_event('generate', {'user_id': user_id, 'generation_kind': 'cultural_product', 'log_id': log_id})
    return jsonify(response_data)

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
    except Exception:
        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)














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
    except Exception:
        return api_error("DATA_UNAVAILABLE", "Data services are temporarily unavailable.", 503, True, True)

# ==============================================
# 新增接口结束
# ==============================================


# 存活检查仅表示 Flask 进程可以响应，不访问任何下游依赖。
@app.route('/api/health')
@app.route('/api/health/live')
def health_check():
    """Liveness endpoint and compatibility alias."""
    return jsonify({'status': 'alive'})


@app.route('/api/health/ready')
def readiness_check():
    """Check dependencies required by the synchronous generation API."""
    mysql_ready = False
    if mysql_service is not None:
        try:
            mysql_ready = bool(mysql_service.connect())
        except Exception:
            mysql_ready = False

    # Hive is an optional analytics dependency and does not gate content generation.
    model_configured = bool(load_settings().dashscope_api_key)
    checks = {
        'mysql': 'ready' if mysql_ready else 'unavailable',
        'generation_model': 'configured' if model_configured else 'unavailable',
        'hive': 'optional',
    }
    ready = mysql_ready and model_configured
    return jsonify({
        'status': 'ready' if ready else 'unavailable',
        'checks': checks,
    }), 200 if ready else 503

if __name__ == '__main__':
    print("🚀 启动智能文创平台后端服务...")
    print("📍 访问地址:")
    print("   - 首页: http://localhost:5000/")
    print("   - 登录页: http://localhost:5000/login.html")
    print("   - 用户端: http://localhost:5000/index.html")
    print("   - 运营端: http://localhost:5000/dashboard.html")
    print("   - API健康检查: http://localhost:5000/api/health")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
