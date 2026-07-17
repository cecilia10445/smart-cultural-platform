#!/usr/bin/env python3
import json
import os
import random
import time
from datetime import datetime
from faker import Faker
from werkzeug.security import generate_password_hash

# -------------------------- 配置项 --------------------------
ADMIN_CREATION_KEY = os.getenv("ADMIN_CREATION_KEY", "")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BACKEND_DIR, "data", "test_users.json")

# 预定义的1000个用户ID范围
PREDEFINED_USER_IDS = [f"U{i:04d}" for i in range(1, 1001)]

INITIAL_TEST_USERS = {
    "users": [
        {
            "user_id": "U1001",
            "username": "user1",
            "password_hash": generate_password_hash("user1"),
            "role": "user",
            "name": "创意用户一",
            "email": "user1@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "preferences": {
                "favorite_styles": ["清新", "水彩画风"],
                "content_type": "社交媒体"
            }
        },
        {
            "user_id": "U1002",
            "username": "user2",
            "password_hash": generate_password_hash("user2"),
            "role": "user",
            "name": "创意用户二",
            "email": "user2@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "preferences": {
                "favorite_styles": ["赛博朋克", "电影感"],
                "content_type": "广告文案"
            }
        },
        {
            "user_id": "U1003",
            "username": "user3",
            "password_hash": generate_password_hash("user3"),
            "role": "user",
            "name": "创意用户三",
            "email": "user3@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "preferences": {
                "favorite_styles": ["复古怀旧", "简约"],
                "content_type": "个人博客"
            }
        }
    ],
    "admins": [
        {
            "user_id": "A2001",
            "username": "admin1",
            "password_hash": generate_password_hash("admin1"),
            "role": "admin",
            "name": "运营管理员",
            "email": "admin@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "permissions": ["view_dashboard", "manage_users", "view_analytics"]
        }
    ]
}

# -------------------------- 核心函数 --------------------------
def load_existing_users():
    """加载已有用户数据"""
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    
    if not os.path.exists(USERS_FILE) or os.path.getsize(USERS_FILE) == 0:
        print("⚠️ 未找到用户数据，初始化初始测试用户...")
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(INITIAL_TEST_USERS, f, ensure_ascii=False, indent=2)
        return INITIAL_TEST_USERS
    else:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

def save_users(users_data):
    """保存用户数据"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 用户数据已保存到: {USERS_FILE}")

def is_username_exist(users_data, username):
    """检查用户名是否已存在"""
    all_usernames = [u["username"] for u in users_data["users"]] + [a["username"] for a in users_data["admins"]]
    return username in all_usernames

def get_available_predefined_ids(users_data):
    """获取尚未使用的预定义用户ID"""
    existing_ids = set(u["user_id"] for u in users_data["users"])
    available_ids = [uid for uid in PREDEFINED_USER_IDS if uid not in existing_ids]
    return available_ids

def generate_unique_id(role, users_data):
    """生成唯一用户ID - 修改为使用预定义ID"""
    if role == "user":
        # 优先使用预定义的ID (U0001-U1000)
        available_ids = get_available_predefined_ids(users_data)
        if available_ids:
            return available_ids[0]
        
        # 如果没有预定义ID可用，则使用原有逻辑
        existing_ids = [int(u["user_id"][1:]) for u in users_data["users"] if u["user_id"].startswith("U")]
        max_id = max(existing_ids) if existing_ids else int(time.time()) % 1000000
        return f"U{max_id + 1:06d}"
    else:
        # 管理员ID保持不变
        existing_ids = [int(a["user_id"][1:]) for a in users_data["admins"] if a["user_id"].startswith("A")]
        max_id = max(existing_ids) if existing_ids else 2000
        return f"A{max_id + 1:04d}"

# -------------------------- 批量生成用户 --------------------------
def generate_bulk_users(user_count=1000, admin_count=10):
    """批量生成普通用户和运营，使用预定义的用户ID"""
    fake = Faker('zh_CN')
    users_data = load_existing_users()
    
    # 获取可用的预定义ID
    available_ids = get_available_predefined_ids(users_data)
    
    if len(available_ids) < user_count:
        print(f"⚠️ 警告: 预定义ID不足，需要 {user_count} 个，但只有 {len(available_ids)} 个可用")
        user_count = len(available_ids)
    
    new_users = []
    new_admins = []

    # 批量生成普通用户（使用预定义ID）
    print(f"\n📌 开始批量生成 {user_count} 个普通用户（使用预定义ID U0001-U1000）...")
    for i in range(user_count):
        user_id = available_ids[i]
        username = f"user_{user_id}"  # 用户名基于用户ID
        
        user_data = {
            "user_id": user_id,
            "username": username,
            "password_hash": generate_password_hash(username),
            "role": "user",
            "name": fake.name(),
            "email": f"{username}@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "preferences": {
                "favorite_styles": random.sample([
                    "清新", "赛博朋克", "水彩画风", "电影感", "复古怀旧",
                    "简约", "未来科技", "卡通", "写实", "浪漫"
                ], 2),
                "content_type": random.choice(["社交媒体", "广告文案", "个人博客", "商业报告"])
            }
        }
        new_users.append(user_data)
        users_data["users"].append(user_data)

    # 批量生成运营（使用原有逻辑）
    print(f"\n📌 开始批量生成 {admin_count} 个运营...")
    for i in range(admin_count):
        username = f"admin_{i+1:03d}"
        admin_id = f"A{2000 + i + 1:04d}"
        
        admin_data = {
            "user_id": admin_id,
            "username": username,
            "password_hash": generate_password_hash(username),
            "role": "admin",
            "name": f"批量运营_{i+1}",
            "email": f"{username}@example.com",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "permissions": ["view_dashboard", "manage_users", "view_analytics", "system_config"]
        }
        new_admins.append(admin_data)
        users_data["admins"].append(admin_data)

    # 保存数据
    save_users(users_data)
    print(f"\n✅ 批量生成完成：{len(new_users)} 个普通用户 (ID: {new_users[0]['user_id']}-{new_users[-1]['user_id']}) + {len(new_admins)} 个运营")
    
    # 生成用户映射文件，用于后续的数据分配
    generate_user_mapping(new_users)
    
    return users_data

def generate_user_mapping(users):
    """生成用户ID映射文件，用于数据集分配"""
    mapping = {user['user_id']: user for user in users}
    mapping_file = os.path.join(BACKEND_DIR, "data", "user_id_mapping.json")
    
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 用户ID映射文件已生成: {mapping_file}")
    return mapping

# -------------------------- 手动添加用户 --------------------------
def add_user_manually():
    """手动添加用户（普通用户直接加，运营需密钥）"""
    users_data = load_existing_users()
    fake = Faker('zh_CN')

    # 选择角色
    while True:
        role = input("\n请选择角色 (user/admin): ").strip().lower()
        if role in ["user", "admin"]:
            break
        print("❌ 角色只能是 'user' 或 'admin'，请重新输入")

    # 管理员需密钥验证
    if role == "admin":
        if not ADMIN_CREATION_KEY:
            print("❌ 未配置 ADMIN_CREATION_KEY，无法创建管理员")
            return
        key = input("请输入运营创建密钥: ").strip()
        if key != ADMIN_CREATION_KEY:
            print("❌ 管理员创建密钥错误，无法创建运营")
            return

    # 输入用户信息（确保唯一）
    while True:
        username = input(f"请输入{role}用户名 (3-12位): ").strip()
        if 3 <= len(username) <= 12 and not is_username_exist(users_data, username):
            break
        elif len(username) < 3 or len(username) > 12:
            print("❌ 用户名需3-12位，请重新输入")
        else:
            print("❌ 用户名已存在，请重新输入")

    password = input(f"请输入{role}密码 (6-16位): ").strip()
    while len(password) < 6 or len(password) > 16:
        print("❌ 密码需6-16位，请重新输入")
        password = input(f"请输入{role}密码 (6-16位): ").strip()

    name = input(f"请输入{role}姓名: ").strip() or fake.name()
    email = input(f"请输入{role}邮箱 (可选): ").strip() or f"{username}@example.com"

    # 生成用户数据
    user_id = generate_unique_id(role, users_data)
    user_data = {
        "user_id": user_id,
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "name": name,
        "email": email,
        "created_at": datetime.now().isoformat(),
        "last_login": None
    }

    # 补充角色特定字段
    if role == "user":
        user_data["preferences"] = {
            "favorite_styles": random.sample([
                "清新", "赛博朋克", "水彩画风", "电影感", "复古怀旧"
            ], 2),
            "content_type": random.choice(["社交媒体", "广告文案", "个人博客"])
        }
        users_data["users"].append(user_data)
    else:
        user_data["permissions"] = ["view_dashboard", "manage_users", "view_analytics"]
        users_data["admins"].append(user_data)

    # 保存数据
    save_users(users_data)
    print(f"\n✅ 手动添加成功！{role}信息：ID={user_id}，用户名={username}")

# -------------------------- 主程序 --------------------------
if __name__ == "__main__":
    print("=== 智能文创平台 - 用户数据管理工具 ===")
    print(f"📁 数据文件路径：{USERS_FILE}")
    print("🔑 管理员创建密钥由 ADMIN_CREATION_KEY 环境变量提供")

    # 加载现有数据（确保历史记录不丢失）
    existing_data = load_existing_users()
    print(f"\n📊 现有数据统计：普通用户 {len(existing_data['users'])} 人，运营 {len(existing_data['admins'])} 人")

    # 批量生成选项
    try:
        bulk_choice = input("\n是否批量生成用户？(y/n): ").strip().lower()
        if bulk_choice == "y":
            user_count = int(input("请输入普通用户数量 (默认1000): ").strip() or 1000)
            admin_count = int(input("请输入运营数量 (默认10): ").strip() or 10)
            generate_bulk_users(user_count, admin_count)
    except Exception as e:
        print(f"❌ 批量生成失败：{str(e)}")

    # 手动添加选项
    try:
        manual_choice = input("\n是否手动添加用户？(y/n): ").strip().lower()
        while manual_choice == "y":
            add_user_manually()
            manual_choice = input("\n是否继续手动添加？(y/n): ").strip().lower()
    except Exception as e:
        print(f"❌ 手动添加失败：{str(e)}")

    print("\n=== 操作完成 ===")
