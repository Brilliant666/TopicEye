# TopicEye — 创作者选题雷达

AI 驱动的内容发现与选题分析平台，帮助内容创作者从 RSS/Reddit/知乎等信源发现热门话题。

## 项目结构

```
TopicEye/
├── backend/          # FastAPI 后端 (Python)
│   ├── app/
│   │   ├── main.py          # 入口
│   │   ├── api/v1/          # API 路由
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # Pydantic Schema
│   │   ├── services/        # 业务逻辑 (爬虫/评分/分析)
│   │   └── database.py      # 数据库配置
│   ├── venv/                # Python 虚拟环境 (已创建)
│   └── topiceye.db          # SQLite 数据库
├── frontend/         # Next.js 前端 (TypeScript)
│   ├── src/
│   │   ├── app/             # 页面路由
│   │   ├── components/      # 组件
│   │   └── lib/             # API/工具
│   └── package.json
└── docs/
```

## 环境要求

- Python 3.12+
- Node.js 24+ (fnm 管理)
- curl (系统自带)
- SQLite3 (系统自带)

## 启动步骤

### 1. 启动后端 (本地开发建议端口 8100)

```bash
cd TopicEye/backend

# 激活虚拟环境
source venv/bin/activate

# 启动服务
uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
```

启动成功后会看到：
```
INFO:     Uvicorn running on http://127.0.0.1:8100
INFO:     Application startup complete — scheduler running
```

验证：浏览器打开 http://127.0.0.1:8100/docs 可看到 API 文档

### 2. 启动前端 (端口 3000)

**新开一个终端窗口**：

```bash
cd TopicEye/frontend

# 安装依赖 (首次或 package.json 变更后)
npm install

# 启动开发服务器。默认会代理到 http://127.0.0.1:8100
npm run dev
```

启动成功后会看到：
```
✓ Ready in xxxms
- Local:   http://localhost:3000
```

### 3. 访问应用

浏览器打开 http://localhost:3000

## 注意事项

### 代理问题

如果你的系统开着 HTTP 代理 (ClashX/Surge 等，端口 7890)，或者 `8000` 端口被 Docker/OrbStack 等本机服务占用：

1. 本地开发优先使用后端 `127.0.0.1:8100`
2. 确保「绕过代理」列表包含 `localhost` 和 `127.0.0.1`
3. ClashX: 设置 → Bypass Domain → 添加 `localhost`
4. Surge: 设置 → 跳过代理 → 添加 `localhost, 127.0.0.1`

也可以显式指定前端代理目标：

```bash
cd TopicEye/frontend
BACKEND_API_URL=http://127.0.0.1:8100 npm run dev
```

Docker Compose 内部仍使用 `backend:8000`，不受本地开发端口影响。

### DuckDB 分析层

- `backend/requirements.txt` 已包含 `duckdb`
- 后端启动时会初始化 DuckDB，并以 READ_ONLY 方式 ATTACH 当前 SQLite/PostgreSQL 数据库
- 健康检查：`curl http://127.0.0.1:8100/health`
- 如果 `database.duckdb.available=false`，说明当前 Python 环境没有安装 DuckDB 包或缺少所需扩展，分析接口会暂时退回 SQLAlchemy

### 数据库

- 后端首次启动会自动创建 `topiceye.db` 并初始化表结构
- 如需重置：停止后端，删除 `backend/topiceye.db`，重启后端

### 手动触发数据抓取

```bash
# 抓取所有启用的信源
curl -X POST http://127.0.0.1:8100/api/v1/sources/sync-all

# 抓取单个信源 (把 1 替换为信源 ID)
curl -X POST http://127.0.0.1:8100/api/v1/sources/1/sync
```

## 功能模块

| 模块 | 说明 |
|------|------|
| 信源管理 | RSS / RSSHub / Reddit / 知乎热榜 / 自定义网站 |
| 内容精选 | 6 维 LLM 评分 + 百分位截断 (P70) + 用户反馈校准 |
| 用户反馈 | 👍👎 反馈按钮，反馈数据用于校准精选算法 |
| 信源权重 | 1-5 级权重，影响精选评分 |
| AI 日报 | 每日自动生成选题分析报告 |
| 趋势追踪 | 关键词热度变化追踪 |
| 收藏夹 | 手动收藏感兴趣的选题 |
