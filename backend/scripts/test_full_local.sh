#!/usr/bin/env bash
# =============================================================================
# 本地隔离的全量 PG 测试入口
#
# GitHub 的 Rardar 控制作业也会运行完整 backend/tests；本入口用于本地复现
# 或风险需要时的独立验证。一次性容器（127.0.0.1:5433）跑完即删，不占用
# 开发栈的 postgres:5432，也避开测试 TRUNCATE 与运行中 backend 互相锁库。
#
# 用法：
#   bash backend/scripts/test_full_local.sh [pytest 参数...]
#   make test-backend
# 可用环境变量：
#   TEST_PG_PORT   临时 PG 端口（默认 5433，被占用时换一个）
#   PYTHON         Python 解释器（默认 backend/venv/bin/python，缺省回退 python3）
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PORT="${TEST_PG_PORT:-5433}"
# 容器名带端口派生：允许通过不同 TEST_PG_PORT 并行跑多份套件互不干扰
CONTAINER="topiceye-test-pg-${PORT}"
if [ -x "$BACKEND_DIR/venv/bin/python" ]; then
  PYTHON="${PYTHON:-$BACKEND_DIR/venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "==> 启动一次性 PostgreSQL (127.0.0.1:${PORT})..."
docker run --rm -d --name "$CONTAINER" \
  -e POSTGRES_DB=topiceye_test \
  -e POSTGRES_USER=topiceye \
  -e POSTGRES_PASSWORD=topiceye \
  -p "127.0.0.1:${PORT}:5432" \
  postgres:16-alpine >/dev/null

echo "==> 等待 PG 就绪..."
# 用 psql 而不是 pg_isready 探活：initdb 阶段的临时服务器也会让 pg_isready
# 短暂转绿，psql 真实连接成功才是可写状态。
ready=0
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" psql -U topiceye -d topiceye_test -c 'SELECT 1' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "PostgreSQL 30s 内未就绪，退出（容器已清理）" >&2
  exit 1
fi

echo "==> 运行全量测试（${PYTHON}）..."
cd "$BACKEND_DIR"
DATABASE_URL="postgresql+asyncpg://topiceye:topiceye@127.0.0.1:${PORT}/topiceye_test" \
DUCKDB_THREADS=1 \
DUCKDB_MEMORY_LIMIT=128MB \
  "$PYTHON" -m pytest tests/ -q --tb=short "$@"
