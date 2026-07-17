#!/usr/bin/env python3
import os
import sys
from pyhive import hive

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

def init_hive_tables():
    """初始化Hive表结构"""
    try:
        # 连接Hive
        connection = hive.connect(host='localhost', port=10000, username='hadoop')
        cursor = connection.cursor()
        
        print("✅ 连接Hive成功")
        
        # 读取SQL文件
        sql_file_path = os.path.join(current_dir, 'hive_setup.sql')
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割并执行SQL语句
        statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        for stmt in statements:
            if stmt:
                print(f"执行: {stmt[:50]}...")
                cursor.execute(stmt)
        
        print("🎉 Hive表初始化完成")
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ Hive表初始化失败: {e}")
        return False

if __name__ == "__main__":
    init_hive_tables()