#!/bin/bash
# ==============================================
# 脚本解释器声明（第一行强制要求）
# ==============================================

# ==============================================
# 1. 环境变量配置（Hadoop路径+项目路径）
# ==============================================
# Hadoop路径（和 which hdfs 输出匹配，正确）
export HADOOP_HOME=/usr/local/hadoop
export PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH

# 项目路径（简化后续路径写法）
PROJECT_ROOT="/home/mywork/smart-cultural-platform"

# ==============================================
# 2. 日志路径配置（保持你的原路径，无需改）
# ==============================================
LOCAL_LOG_DIR="$PROJECT_ROOT/data/logs"
LOCAL_LOG_FILE="$LOCAL_LOG_DIR/app.log"
HDFS_LOG_DIR="/user/logs/aigc_platform"
HDFS_BACKUP_DIR="$HDFS_LOG_DIR/backup"

# ==============================================
# 3. 核心执行逻辑
# ==============================================
echo "=== 开始上传日志到HDFS ==="

# 检查HDFS服务是否真的可用（测试根目录，比/test/user更基础）
if ! hdfs dfs -test -d /; then
    echo "❌ HDFS服务未启动或不可访问"
    exit 1
fi
echo "✅ HDFS服务连接正常"

# 自动创建HDFS目录（-p确保父目录也创建）
if ! hdfs dfs -test -d $HDFS_LOG_DIR; then
    echo "⚠️ HDFS目标目录不存在，自动创建：$HDFS_LOG_DIR"
    hdfs dfs -mkdir -p $HDFS_LOG_DIR
fi
if ! hdfs dfs -test -d $HDFS_BACKUP_DIR; then
    echo "⚠️ HDFS备份目录不存在，自动创建：$HDFS_BACKUP_DIR"
    hdfs dfs -mkdir -p $HDFS_BACKUP_DIR
fi

# 检查本地日志文件是否存在+非空
if [ ! -f "$LOCAL_LOG_FILE" ]; then
    echo "⚠️ 本地日志文件不存在：$LOCAL_LOG_FILE"
    exit 0
fi
FILE_SIZE=$(stat -c%s "$LOCAL_LOG_FILE")  # 仅Ubuntu可用的文件大小命令
if [ $FILE_SIZE -eq 0 ]; then
    echo "⚠️ 本地日志文件为空，跳过上传"
    exit 0
fi
echo "✅ 本地日志文件正常（大小：$FILE_SIZE 字节）"

# 上传日志（带时间戳，避免覆盖）
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HDFS_LOG_FILE="$HDFS_LOG_DIR/app_$TIMESTAMP.log"

echo "📤 开始上传：$LOCAL_LOG_FILE -> $HDFS_LOG_FILE"
hdfs dfs -put -f "$LOCAL_LOG_FILE" "$HDFS_LOG_FILE"  # -f覆盖已存在文件

# 验证上传结果
if hdfs dfs -test -f "$HDFS_LOG_FILE"; then
    echo "✅ 日志上传成功！HDFS路径：$HDFS_LOG_FILE"
    
    # 本地日志备份+清空（可选，按你的需求保留）
    BACKUP_FILE="$LOCAL_LOG_DIR/app_$TIMESTAMP.log.backup"
    cp "$LOCAL_LOG_FILE" "$BACKUP_FILE"
    > "$LOCAL_LOG_FILE"  # 清空原日志
    echo "📦 本地日志已备份到：$BACKUP_FILE，并清空原文件"
else
    echo "❌ 日志上传失败，请检查HDFS权限"
    exit 1
fi

# ==============================================
# 4. ERNIE数据集导入（可选功能）
# ==============================================
ERNIE_DATASET_DIR="/home/mywork/smart-cultural-platform/data/ernie_dataset"
ERNIE_PROCESSED_FILE="$ERNIE_DATASET_DIR/processed/ernie_platform_logs.json"

# 检查是否需要导入ERNIE数据集
if [ "$1" = "--import-ernie" ] && [ -f "$ERNIE_PROCESSED_FILE" ]; then
    echo "=== 开始导入ERNIE数据集 ==="
    
    # 创建ERNIE数据专用目录
    hdfs dfs -mkdir -p $HDFS_LOG_DIR/ernie_data
    
    # 上传ERNIE数据集
    echo "📤 上传ERNIE数据集到HDFS..."
    hdfs dfs -put -f "$ERNIE_PROCESSED_FILE" "$HDFS_LOG_DIR/ernie_data/"
    
    if hdfs dfs -test -f "$HDFS_LOG_DIR/ernie_data/ernie_platform_logs.json"; then
        echo "✅ ERNIE数据集上传成功"
        echo "📊 数据集大小: $(hdfs dfs -du -h $HDFS_LOG_DIR/ernie_data/ernie_platform_logs.json)"
    else
        echo "❌ ERNIE数据集上传失败"
    fi
fi


# 在ERNIE数据集导入部分后面添加：

# ==============================================
# 5. Flickr30K数据集导入（可选功能）
# ==============================================
FLICKR_DATASET_DIR="/home/mywork/smart-cultural-platform/data/flickr30k_dataset"
FLICKR_PROCESSED_FILE="$FLICKR_DATASET_DIR/processed/flickr_platform_logs.json"

# 检查是否需要导入Flickr30K数据集
if [ "$1" = "--import-flickr" ] && [ -f "$FLICKR_PROCESSED_FILE" ]; then
    echo "=== 开始导入Flickr30K数据集 ==="
    
    # 创建Flickr30K数据专用目录
    hdfs dfs -mkdir -p $HDFS_LOG_DIR/flickr_data
    
    # 上传Flickr30K数据集
    echo "📤 上传Flickr30K数据集到HDFS..."
    hdfs dfs -put -f "$FLICKR_PROCESSED_FILE" "$HDFS_LOG_DIR/flickr_data/"
    
    if hdfs dfs -test -f "$HDFS_LOG_DIR/flickr_data/flickr_platform_logs.json"; then
        echo "✅ Flickr30K数据集上传成功"
        echo "📊 数据集大小: $(hdfs dfs -du -h $HDFS_LOG_DIR/flickr_data/flickr_platform_logs.json)"
    else
        echo "❌ Flickr30K数据集上传失败"
    fi
fi


echo "=== HDFS上传任务完成 ==="