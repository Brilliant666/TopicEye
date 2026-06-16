#!/usr/bin/env bash
# =============================================================================
# TopicEye 数据库备份脚本
#
# 用法：
#   ./scripts/backup_db.sh [backup_dir]
#
# 自动检测 DATABASE_URL（从 .env 或环境变量），按 backend 类型备份：
#   - SQLite: 直接 cp 数据库文件（停服时安全；运行时用 sqlite3 .backup）
#   - PostgreSQL: pg_dump 自定义格式压缩
#
# 保留策略：默认保留最近 7 份，更早的自动删除。
# 适合配 cron：每天凌晨跑一次。
#   0 4 * * * cd /app && ./scripts/backup_db.sh /app/data/backups >> /app/data/backup.log 2>&1
# =============================================================================
set -euo pipefail

BACKUP_DIR="${1:-./data/backups}"
KEEP_COUNT="${BACKUP_KEEP_COUNT:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# 读取 DATABASE_URL（优先环境变量，其次 .env）
DATABASE_URL="${DATABASE_URL:-}"
if [[ -z "$DATABASE_URL" && -f .env ]]; then
    DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
fi

if [[ -z "$DATABASE_URL" ]]; then
    echo "ERROR: DATABASE_URL not set (env or .env)" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
echo "[$(date)] Backup started → $BACKUP_DIR (DATABASE_URL prefix: ${DATABASE_URL%%://*})"

if [[ "$DATABASE_URL" == sqlite* ]]; then
    # ── SQLite backup ──
    # 提取 db 文件路径（去掉 sqlite+aiosqlite:/// 前缀）
    DB_PATH="${DATABASE_URL#*:///}"
    DB_PATH="${DB_PATH#*://}"  # 兼容 sqlite:///path
    if [[ ! -f "$DB_PATH" ]]; then
        echo "ERROR: SQLite file not found: $DB_PATH" >&2
        exit 1
    fi
    BACKUP_FILE="$BACKUP_DIR/topiceye_${TIMESTAMP}.db"

    # 用 sqlite3 .backup（在线热备，不阻塞写入；比 cp 更安全）
    if command -v sqlite3 &>/dev/null; then
        sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
        echo "[$(date)] SQLite online backup → $BACKUP_FILE"
    else
        cp "$DB_PATH" "$BACKUP_FILE"
        echo "[$(date)] SQLite cold copy → $BACKUP_FILE (sqlite3 not available)"
    fi

elif [[ "$DATABASE_URL" == postgresql* ]]; then
    # ── PostgreSQL backup ──
    BACKUP_FILE="$BACKUP_DIR/topiceye_${TIMESTAMP}.dump"

    # 从 URL 解析连接参数
    PG_URL="${DATABASE_URL#postgresql+asyncpg://}"
    PG_URL="${PG_URL#postgresql://}"
    PG_USER="$(echo "$PG_URL" | cut -d: -f1)"
    PG_PASS="$(echo "$PG_URL" | cut -d: -f2 | cut -d@ -f1)"
    PG_HOST="$(echo "$PG_URL" | cut -d@ -f2 | cut -d: -f1)"
    PG_PORT="$(echo "$PG_URL" | cut -d@ -f2 | cut -d: -f2 | cut -d/ -f1)"
    PG_DB="$(echo "$PG_URL" | cut -d/ -f2)"
    PG_PORT="${PG_PORT:-5432}"

    export PGPASSWORD="$PG_PASS"
    pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -Fc -f "$BACKUP_FILE" "$PG_DB"
    unset PGPASSWORD
    echo "[$(date)] PostgreSQL backup → $BACKUP_FILE"

else
    echo "ERROR: Unsupported DATABASE_URL: ${DATABASE_URL%%+*}" >&2
    exit 1
fi

# ── 保留策略：只留最近 KEEP_COUNT 份 ──
if [[ "$KEEP_COUNT" -gt 0 ]]; then
    # 按修改时间倒序，删除超出的
    cd "$BACKUP_DIR" || exit 1
    ls -t topiceye_* 2>/dev/null | tail -n +"$((KEEP_COUNT + 1))" | while read -r old_file; do
        rm -f "$old_file"
        echo "[$(date)] Pruned old backup: $old_file"
    done
    cd - >/dev/null || true
fi

BACKUP_SIZE="$(du -h "$BACKUP_FILE" 2>/dev/null | cut -f1 || echo "?")"
echo "[$(date)] Backup done: $BACKUP_FILE ($BACKUP_SIZE), keeping last $KEEP_COUNT"
