# TopicEye

**AI-powered content discovery and topic radar for creators.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/Brilliant666/TopicEye/actions/workflows/ci.yml/badge.svg)](https://github.com/Brilliant666/TopicEye/actions/workflows/ci.yml)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Frontend: Next.js](https://img.shields.io/badge/Frontend-Next.js_16-black.svg)](https://nextjs.org/)

[English](README.md) | [简体中文](README.zh-CN.md)

---

TopicEye continuously crawls 25+ sources (RSS, Reddit, YouTube, podcasts, newsletters, trending boards), scores every item through a transparent 6-dimension engine, and surfaces the topics worth writing about today. It is built for content creators who are overwhelmed by noise and need curation with taste — not another feed reader.

![Today's Picks](docs/screenshots/screenshot-today.png)

## Why TopicEye

- **Transparent scoring engine, not a black box.** Every selected item ships with a full breakdown: base score (information density / actionability / creator value / viral potential / source authority / freshness), quality gates, time decay, diversity penalty, and feedback signal. See the [`algorithm` page](docs/screenshots/screenshot-algorithm.png) in the app.
- **Feedback closes the loop.** Your 👍 / 👎 doesn't just get saved — it is weighted at 15% and feeds back into ranking. The engine gets sharper the more you use it.
- **Multi-source intelligence.** 25+ crawl sources (RSS / Reddit / YouTube / podcasts / newsletters / trending boards) + WeRead reading stats + webnovel radar (Fanqie / Qimao / Zhihu Yanxuan). One platform, full-spectrum signal.
- **Self-host friendly.** Full Docker setup, PostgreSQL, OAuth login (Google / GitHub). Your data stays yours.
- **Agent-native (planned).** The scoring engine is being exposed as a stable API so other agents and tools can call it as their ranking layer.

## Screenshots

### Core Discovery

| Today's Picks | Daily Report | Trending Radar |
|---|---|---|
| ![today](docs/screenshots/screenshot-today.png) | ![daily](docs/screenshots/screenshot-daily.png) | ![trending](docs/screenshots/screenshot-trending.png) |

| Trend Tracking | Low-Follower Viral | Algorithm Flow |
|---|---|---|
| ![trends](docs/screenshots/screenshot-trends.png) | ![lfv](docs/screenshots/screenshot-low-follower-viral.png) | ![algorithm](docs/screenshots/screenshot-algorithm.png) |

### Stats & Reports

| Stats Dashboard | Job Stats | Changelog |
|---|---|---|
| ![stats](docs/screenshots/screenshot-stats.png) | ![stats-jobs](docs/screenshots/screenshot-stats-jobs.png) | ![changelog](docs/screenshots/screenshot-changelog.png) |

| Weekly Report | Monthly Report | |
|---|---|---|
| ![weekly](docs/screenshots/screenshot-weekly.png) | ![monthly](docs/screenshots/screenshot-monthly.png) | |

### New Features — WeRead & Webnovel

| WeRead Stats | Webnovel Radar |
|---|---|
| ![weread](docs/screenshots/screenshot-weread.png) | ![novel](docs/screenshots/screenshot-novel.png) |

### User Workspace

| Favorites | My Topics | Topic Config |
|---|---|---|
| ![favorites](docs/screenshots/screenshot-favorites.png) | ![my-topics](docs/screenshots/screenshot-my-topics.png) | ![my-topics-config](docs/screenshots/screenshot-my-topics-config.png) |

| Login | Profile | |
|---|---|---|
| ![login](docs/screenshots/screenshot-login.png) | ![profile](docs/screenshots/screenshot-profile.png) | |

### Admin Console

| Admin Overview | Source Management | Content Management |
|---|---|---|
| ![admin](docs/screenshots/screenshot-admin.png) | ![admin-sources](docs/screenshots/screenshot-admin-sources.png) | ![admin-contents](docs/screenshots/screenshot-admin-contents.png) |

| User Management | AI Engine (Model Eval) | Mother Topics |
|---|---|---|
| ![admin-users](docs/screenshots/screenshot-admin-users.png) | ![admin-model-eval](docs/screenshots/screenshot-admin-model-eval.png) | ![admin-mother-topics](docs/screenshots/screenshot-admin-mother-topics.png) |

| Release Notes | Feedback Workbench | System Settings |
|---|---|---|
| ![admin-updates](docs/screenshots/screenshot-admin-updates.png) | ![admin-feedback](docs/screenshots/screenshot-admin-feedback.png) | ![admin-settings](docs/screenshots/screenshot-admin-settings.png) |

## Features

| Module | Description |
|---|---|
| **Source management** | RSS / RSSHub / Reddit / YouTube / Podcasts / Newsletters / custom sites. Public sources + private sources per user. |
| **Curation scoring** | 6-dimension weighted engine + P70 percentile cutoff + risk control + user feedback calibration. |
| **AI analysis** | Per-item summary, key points, topic suggestions (differentiated prompts for CN/EN content). |
| **Daily / weekly / monthly reports** | Auto-generated from the content pool, with timeline view and scrollable history. |
| **Trend radar** | Topic trending + low-follower viral detection (find breakout posts before they peak). |
| **WeRead integration** | Sync reading stats and bookshelf from WeRead API; daily auto-refresh cache, reading-time analytics, and bookshelf comparison. |
| **Webnovel radar** | Fanqie / Qimao / Zhihu Yanxuan trending charts, gated behind a runtime feature flag. |
| **Mother topics** | Multi-tenant topic templates — admins maintain the system library, users fork their own and customize keywords, weights, and target readers. Fork edits take effect immediately in the scoring queue. |
| **AI model evaluation** | Admin UI to compare LLM models side-by-side on the same prompts, track quality and cost, and pick the right routing group per task. |
| **Email verification** | Transactional email via Brevo API or any SMTP provider (QQ Enterprise / Gmail / etc.), configured from the admin settings page. |
| **Article reader** | In-app reader for source URLs — fetches public HTML only, no auth/cookies/captcha bypass, with SSRF guard and snapshot caching. |
| **Favorites** | Save items across sessions (per-user). |
| **My topics** | Personalized topic configuration with mother-topic fork, keyword filters, and scoring overrides. |
| **Admin console** | Full management UI: sources, content, users, AI model evaluation, mother-topic templates, release notes, feedback, and system settings. |
| **OAuth login** | Google / GitHub (email + password also supported). |
| **Rate limiting** | Per-endpoint budgets for login, registration, and LLM calls. |

## Architecture

### Backend layering

Strict one-way dependency (see [AGENTS.md](AGENTS.md) for the full rules):

```text
api/v1/ ──► services/ ──► repositories/ ──► models/ ──► sqlalchemy
```

| Layer | Owns | Must not |
|---|---|---|
| `api/v1/` | Route declarations, request validation, response shaping | `import sqlalchemy` (except `AsyncSession` type hint), direct ORM queries |
| `services/` | Business orchestration, transaction boundaries, cross-repo composition | — |
| `repositories/` | Single entry point for ORM, CRUD + complex query encapsulation | Importing each other, business logic |
| `models/` | Pure ORM declarations, field definitions, `__table_args__` | Business methods, side effects, IO |
| `schemas/` | Pydantic request/response models, serialization | ORM imports, DB access |

Cross-cutting: `core/` (config, DB, logging, retry), `middleware/` (rate limit, request metrics), `services/email/` (Brevo + SMTP), `services/llm/` (failover, circuit breaker, response cache), `services/scrapers/` + `services/trending_scrapers/` (per-source fetchers).

### Scoring engine

The 6-dimension base score (weights sum to 1.0):

| Dimension | Weight | What it measures |
|---|---|---|
| Information density | 0.25 | Signal-to-noise ratio of the content |
| Actionability | 0.20 | Can the reader do something with this today? |
| Creator value | 0.18 | Usefulness for someone writing about this topic |
| Viral potential | 0.15 | Likelihood of breaking out |
| Source authority | 0.12 | Trust weight of the originating source |
| Freshness | 0.10 | Recency decay (`exp(-0.02 × hours)`, floor 0.3) |

Post-processing:

- **Quality gates** — items below 45 are too thin; above 70 are fully trusted.
- **Risk control** — hard-exclude above 82, soft-degrade starting at 45.
- **Diversity penalty** — 0.85× per same-source duplicate, 0.92× per same-category duplicate (with grace slots).
- **Percentile cutoff** — top ~30% (P70 and above) selected.
- **Feedback signal** — 👍 / 👎 weighted at 15%, clamped at ±20 per item to prevent domination.
- **Curation floor** — minimum base score 58; the engine refuses to surface weak items just because the batch is weak.

Full config in [backend/app/services/scoring_engine.py](backend/app/services/scoring_engine.py).

### Source matrix

| Category | Sources |
|---|---|
| RSS / RSSHub | Any RSS feed, RSSHub routes (custom sites, blogrolls) |
| Aggregators | Reddit, Hacker News, GitHub Trending, V2EX, Juejin, Sspai, ITHome, 36Kr |
| Social / short video | Weibo, Douyin (hot + trending), Bilibili, Tieba, Zhihu trending |
| Finance | Xueqiu, Eastmoney, Netease Finance, Sohu Finance |
| Discovery | Douban, Hupu, Heiyan, Ishugui, Xyzrank, Toutiao, Baidu |
| Long-form | YouTube, Podcasts, Newsletters |
| Reading | WeRead (reading stats + bookshelf via official gateway) |
| Webnovel | Fanqie, Qimao, Zhihu Yanxuan (runtime feature flag, off by default) |

### Database choices

- **PostgreSQL 16** — the only supported OLTP database (startup validator rejects anything else). Local dev uses the compose `postgres` service; tests run against a throwaway PG container (`make test-backend`).
- **DuckDB** — read-only analytics layer over the OLTP database. Powers stats dashboards without burdening the write path. Memory and thread budgets configurable via `DUCKDB_THREADS` / `DUCKDB_MEMORY_LIMIT`.

## Tech stack

- **Backend:** FastAPI (async) · SQLAlchemy 2.0 · Alembic · DuckDB (analytics) · httpx
- **Frontend:** Next.js 16 · React 19 · TypeScript · Tailwind CSS v4
- **Database:** PostgreSQL 16 · DuckDB as a read-only analytics layer over OLTP
- **Auth:** Opaque bearer tokens (DB-hashed) + OAuth via Authlib
- **Email:** Brevo API or SMTP (user-configurable per deployment)
- **Infra:** Docker / docker-compose (dev + prod) · APScheduler

## Quick start

### Rardar local product MVP (Windows)

Rardar reuses the existing TopicEye PostgreSQL cluster and the enabled
`routing_group=rardar` model; it never creates a replacement database or
rewrites model credentials. Real Rardar intelligence is the default. Sync one
fully audited published generation into the repository-external local mirror,
build its immutable read-optimized Serving Projection, then start the product:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 sync-data
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 start
```

The Rardar navigation also exposes `/news`, a saved multi-source technology
timeline spanning official updates, technology reporting and community
discussion. Refresh sources explicitly without running a repository scan,
Discover evaluation, or model call:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 refresh-news
```

For daily use, sign in as an administrator and use the operation panel on
`/news`: **更新资讯** fetches only configured public sources with no model call;
**补充中文速读** shows the current page scope and server request cap before an
explicit confirmation. The server freezes that page, manages a new durable
budget internally, and exposes status/results after navigation or reload.
Ordinary GET requests never start work. Anonymous and non-admin POST requests
are rejected; cookie POST requests must also pass the configured-origin check.

Use **信源管理 → 暂停 / 恢复** to control News collection. Web refresh and
`refresh-news` honor the same existing Source setting; initialization does not
re-enable paused sources. Pausing preserves collected articles, Chinese reading
results and HTTP cache validators. An in-flight fetch may finish without
overwriting the pause; resume takes effect on the next normal refresh. Paused
sources are not network failures, and an all-paused refresh reports no collection.

The local-only runner reuses the same business functions as the CLI and an OS
writer lock serializes refresh/enhancement across both entries. Repeated clicks
during a run return the active operation; retries with the same request key do
not allocate another budget. Interrupted runs are shown as interrupted, not
automatically resumed. Completed content stays saved. The server-only
`RARDAR_NEWS_REQUEST_LIMIT` defaults to 12 requests per explicit enhancement;
the browser cannot change it. A single operation is bounded to 30 minutes and
one page (18 items). State and budget journals live outside the checkout under
`%LOCALAPPDATA%/TopicEye/news-operations/<database-hash>/` on Windows, or
`~/.local/state/TopicEye/news-operations/<database-hash>/` elsewhere. Historical
research and quick-read ledgers are never reused. No scheduler is added.

The existing CLI remains available for operators. Chinese quick-read is a
separate, explicitly budgeted local step. Initialize a
durable run budget once, then reuse the same path and run ID for retries or
cache verification:

```powershell
$budget = "$env:LOCALAPPDATA\RardarNewsQuickRead\20260908\provider-budget.json"
pwsh -NoProfile -File .\scripts\rardar-local.ps1 enhance-news `
  -NewsBudgetPath $budget -NewsRunId quickread-20260908 -NewsBudgetLimit 16 `
  -NewsItemLimit 18 -InitializeNewsBudget

# Repeat without -InitializeNewsBudget; unchanged items reuse their saved result.
pwsh -NoProfile -File .\scripts\rardar-local.ps1 enhance-news `
  -NewsBudgetPath $budget -NewsRunId quickread-20260908 -NewsBudgetLimit 16 -NewsItemLimit 18
```

The source-refresh command reuses TopicEye's SSRF-guarded clients, conditional HTTP cache
(`ETag` / `Last-Modified`) and existing PostgreSQL content tables. A failed
source keeps previously saved items; normal page requests only read that cache.
Source and topic filters, ordering and pagination run over the complete saved
result set. `publishedAt`, `updatedAt`, community discussion time and local
`fetchedAt` remain distinct, and a missing publication time is shown as unknown
rather than replaced with fetch time. Quick-read uses the existing Rardar model
route, strict JSON validation and single-concurrency provider ledger. It stores
Chinese text as a derived cache bound to the original title/summary and, when
used, the safely extracted article body. A title-only item can receive a
faithful title translation but never an invented summary. Normal refresh keeps
valid derived results; normal page requests never fetch publishers or call a
model.

`sync-data` reads the configured `rardar-prod` host without changing it and
independently synchronizes Today and Discover below
`%LOCALAPPDATA%\TopicEye\rardar-intelligence`. Each path verifies a stable
pointer, ready manifest, every required artifact hash and source copy, stages
an immutable generation, builds its own static Serving projection, and switches
only its own pointers. Today can remain healthy if Discover is unavailable;
Discover can advance without rewriting Today. A failed or interrupted
activation restores the affected pointers, so a page cannot mix generations.
The command never reads D1 or credentials and never writes Production.

For daily **Today-only** checks, log in as an administrator and use
**检查并同步榜单** on `/`. The page retains the last result, check time and
successful sync time separately from the factual observation window. A check
uses the existing read-only SSH identity, validates a published complete board,
and either installs its fact-first Serving or reports **已是最新** / no newer
complete board. It never triggers upstream collection, Discover or a model.
An in-progress check is shared by repeat clicks; failures preserve the old board.
The CLI uses the same flow:
`python -m scripts.sync_rardar_intelligence --target <local-data-dir> --check-published`
(run from `backend`). `RARDAR_TODAY_SOURCE_HOST` and
`RARDAR_TODAY_SOURCE_ROOT` are server-only configuration, defaulting to the
existing `rardar-prod` and `/var/lib/rardar/data`; the browser cannot supply
hosts, paths or generation options. No additional SSH or sudo permission is
granted by this entry. It is available only in the local Rardar admin mode.

Rardar daily operations reuse the backend APScheduler and its existing job
records. The normal local launcher enables only the Rardar daily job, not
TopicEye's unrelated collectors or analysis jobs. The schedule checks at 08:30
Asia/Shanghai and hourly afterwards for bounded same-day recovery; startup
checks missed work, but sleeping/offline computers do not execute jobs.
Administrators use **后台 → 系统设置 → Rardar 每日自动更新** to pause/resume,
run immediately, inspect recent results and configure the shared daily model
request limit. Triggered, processed and published are separate outcomes.
Missing model expense configuration leaves zero-model sync available. Daily
progress and budget records survive process restarts; historical experiment
ledgers are not reset or reused. A continuously online host still requires a
separately authorized deployment through the existing deployment procedure.

The daily cycle checks Today facts first (never requiring AI), refreshes enabled
public News sources, checks registered public project material, then continues
Discover assessments, News quick reads and Today profiles using compatible
caches. All managed candidates/content are inventoried; transport chunks are
not a daily coverage quota. Counts distinguish checks, completed work, pending
work and actual pointer activation. Each 08:30 cycle has at most three attempts;
a midnight manual catch-up does not consume the coming morning's cycle. Model
usage instead follows the Shanghai calendar day and includes manual calls.
Historical Find questions/results are not rerun; old memory-only project lists
cannot be reconstructed and are not reported as a completed historical scan.

Serving contains a small `today.json`, one project profile and one static
evidence record per Top 20 repository. Serving v4 separates a concise Chinese
project identity, an evidence-backed core value, at most two key
differentiators, the complete capability list, and semantic quality state.
Images, badges, bare URLs, redirect notices, install-only text and placeholders
are rejected before a profile can be marked ready. A machine-readable content
audit checks all Top 20 profiles after a rebuild.

Normal Today and project-detail requests verify only the Serving pointer,
manifest, selected file hash and strict Schema; they do not repeat the full raw
Artifact audit, call GitHub or invoke an LLM. The loader caches the verified DTO
by pointer identity, emits an ETag, and invalidates safely when the pointer
changes. Rebuild and audit the projection from the already verified local
generation without contacting Production:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 rebuild-serving
Push-Location .\backend
python -m scripts.audit_rardar_serving_content --target "$env:LOCALAPPDATA\TopicEye\rardar-intelligence"
Pop-Location
```

`/discover` is a local Shadow selection of projects worth understanding,
learning from or reusing outside Today Top 20. It starts from a locally
mirrored, hash-verified bundle of Rardar Observation captures and the
authoritative Today artifact, keeps exact rank 21+ eligible, and uses six
deterministic recall channels with an explicit stable batch identity. The
momentum-blind, evidence-bound Value Gate alone determines eligibility;
Timeliness is optional context and cannot veto, admit or reorder a project.
Star and short-window growth remain auxiliary facts and cannot make weak value
strong.

The page is one unranked stream with category and primary-reason filters in the
URL. Project cards and details reuse a cached canonical profile, or use bounded
deterministic profile evidence on a cache miss; the Selection build never hides
extra profile-model calls outside the attached shared execution budget. They add a versioned
Selection context without duplicating identity, positioning or capability
authority. Normal Discover and detail requests read only the immutable
`discover-worth-seeing` Serving projection: zero GitHub calls, zero LLM calls,
zero raw source reads and zero PostgreSQL fact writes. Build, inspect, repeat
the idempotence check, or roll back a retained local generation with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 build-selection
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 selection-status
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 rebuild-selection
powershell -ExecutionPolicy Bypass -File .\scripts\rardar-local.ps1 selection-rollback `
  -SelectionGeneration <generation-id>
```

This runtime is deliberately local/shadow-only. It does not activate
Production Discover or modify Today. See
[Rardar Discover Adapter](docs/platform/RARDAR_DISCOVER_ADAPTER.md).

Local administrators can instead open `/discover`, choose **生成下一批精选**,
review the fixed candidates, Today/source revision and request cap, then
explicitly confirm. Preparation and status reads never call a model. The
server owns the batch and durable budget; duplicate confirmation returns the
same operation rather than buying another allowance. Source facts are prepared
from the verified local Today mirror, excluding only its published Top 20.
Up to six available candidates are processed without padding or replacement.
The versioned small-batch policy keeps incomplete projects unfinished while
publishing independently valid results. Failure preserves the previous
Selection, and retained artifacts keep their original validation policy.

Today links each repository to
`/project/github/<githubRepositoryId>?generation=<generationId>`. The numeric
GitHub repository ID is authoritative and the generation query binds the
official profile, static evidence and 24-hour facts to the same immutable
snapshot. Today prioritizes project identity and core value before two concise
adoption signals. The detail page presents identity, core value, capabilities
and the Rardar adoption decision before start-here links and 24-hour facts;
official excerpts and generation provenance remain closed until requested. AI
deep insight is an explicit action on that detail page and uses the saved
evidence; the single Find Project action safely pre-fills the canonical public
GitHub URL.

### Find Project：按需求核对公开项目

`/find` 接受自然语言需求和可选公开 GitHub 仓库 URL。一次有界查询规划
区分用途、必须条件、偏好和排除项；最多三条 GitHub Search 按相关性召回，
轮流取候选而不按 Star 截断。最多六个项目读取现有安全 GitHub 证据入口的
有界 README 和静态资料，再针对同一需求给出零至三个重点方案。

每个必须条件及排除约束区分“资料支持 / 资料明确不满足 / 未确认”，并提供
资料链接；README 声明不等于实际运行验证。提供的仓库不是默认最佳方案；
未深评候选也不是被证明不合适。没有候选时不补演示仓库，模型不可用时仍
保留真实召回资料，不用未验证的流畅文本替代结构验证。

相同需求和证据复用现有模型路由缓存（进程内、有 TTL）；Star 等互动变化
不进入比较输入。浏览、回退和查看本标签页近期结果不发起检索或模型调用。
页面仅在当前标签页保存最近三组结果，最长 24 小时，可主动清除；它们不
成为长期用户偏好。验证运行可使用既有持久 Provider 账本，Find 的规划、
比较和底层重试共用 `find_project` 阶段额度，不借用历史 Shadow / News 账本。

Find 的证据比较单次截止时间由 `RARDAR_FIND_COMPLETION_TIMEOUT_SECONDS`
控制（默认及上限 120 秒），查询规划仍使用原通用截止时间（默认 45 秒）。
模型配置的更短 timeout 仍有效；Find 超时不自动重复或切换模型消耗额度，
日志区分本地截止取消与 SDK 超时，不将其一律归为远端 HTTP 故障。
外层 Rardar 代理为 300 秒；用户取消不会重新提交模型请求。
比较输入从已采集 README 中选取有界需求相关上下文，明确标注省略边界；
未在摘录中找到能力不是“不支持”的证据。页面保留完整已采集材料（每仓库
最多 12000 字符，并非完整仓库扫描），摘录仍需匹配原始证据；Markdown
行内链接可按可见文字匹配，但不能改写事实或删除否定词。

`start` starts the existing PostgreSQL cluster when needed, then the backend
in Rardar product mode and the frontend at `http://127.0.0.1:3000/`. The
frontend health probe uses `/api/health`, which does not load Rardar data. If no
verified Serving Projection exists, the real API fails closed instead of
silently substituting sample projects. Demo data is available only when a
developer explicitly sets `RARDAR_DATA_MODE=demo`; it remains development-only
and visibly labelled. Use the same command with `status` or `stop` to inspect or
stop the app processes. Existing PostgreSQL data, model configuration and the
mirrored generations are preserved on stop.

### Prerequisites

- Python 3.12+ · Node.js 20+ · Git
- **or** Docker + Docker Compose (easiest path)

### Option A — Docker Compose (production-style, recommended for running the service)

Uses [docker-compose.prod.yml](docker-compose.prod.yml): code baked into the image, no hot reload, healthchecks, resource limits, Postgres by default.

```bash
git clone https://github.com/Brilliant666/TopicEye.git
cd TopicEye
docker compose -f docker-compose.prod.yml up -d --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

> The default [docker-compose.yml](docker-compose.yml) is a hot-reload development setup (bind mounts, `--reload`, `npm run dev`). Use it for local development only — not for deploying the service.

### Option B — Docker Compose (development with hot reload)

```bash
git clone https://github.com/Brilliant666/TopicEye.git
cd TopicEye
docker compose up -d
```

Same ports as above. Source changes reload automatically. PostgreSQL is part of
the default Compose stack and the backend waits for its health check. To start
only the database:

```bash
docker compose up -d postgres
```

### Option C — Local development (no Docker)

**1. Backend** (port 8102)

```bash
cd TopicEye/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt   # includes pytest + pytest-asyncio
cp .env.example .env                  # edit as needed
uvicorn app.main:app --host 127.0.0.1 --port 8102 --reload
```

**2. Frontend** (port 3000, in a new terminal)

```bash
cd TopicEye/frontend
npm install
npm run dev
```

Open http://localhost:3000 and point the frontend at the backend with `BACKEND_API_URL=http://127.0.0.1:8102` if the proxy bypass is not set.

> **Proxy note:** if you run a local HTTP proxy (ClashX / Surge on :7890), make sure `localhost` and `127.0.0.1` bypass it, or set `BACKEND_API_URL=http://127.0.0.1:8102` before `npm run dev`.
>
> **OAuth callback URL:** when running the backend locally on :8102, the OAuth redirect URIs in Google/GitHub consoles should point to `http://localhost:8102/api/v1/auth/oauth/{google,github}/callback`. In Docker mode use `:8000`.

## Configuration

All configuration is environment-driven. See [`backend/.env.example`](backend/.env.example) for the full list with comments. Highlights:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string, e.g. `postgresql+asyncpg://user:pass@host:5432/topiceye`. SQLite support has been removed. |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed frontend origins. |
| `OAUTH_GOOGLE_CLIENT_ID` / `_SECRET` | empty | Enable Google login. [Guide](backend/.env.example). |
| `OAUTH_GITHUB_CLIENT_ID` / `_SECRET` | empty | Enable GitHub login. |
| `OAUTH_FRONTEND_REDIRECT_URL` | `http://localhost:3000/oauth/callback` | Frontend OAuth callback page (token travels via URL fragment). |
| `ADMIN_SEED_ENABLED` | `false` | Set to `true` plus `ADMIN_EMAIL` / `ADMIN_PASSWORD` to seed/promote an admin on startup. |
| `AUTH_LOGIN_ATTEMPTS_PER_MINUTE` | `20` | Login rate limit per IP. |
| `LLM_REQUESTS_PER_MINUTE` | `30` | LLM call rate limit per user. |
| `RSS_SCRAPER_TIMEOUT_SECONDS` | `15` | Per-fetch timeout; slow sources can override via per-source `settings`. |
| `SOURCE_SYNC_TIMEOUT_SECONDS` | `120` | Overall sync timeout per source. |
| `ARTICLE_READER_ENABLED` | `true` | In-app reader for public HTML (SSRF-guarded, no auth bypass). |

> **Webnovel-CN module** (Fanqie / Qimao / Zhihu Yanxuan) is gated behind a runtime feature flag — disabled by default. Admins can enable it from **Source management → Feature flags** in the UI, or via `PUT /api/v1/settings/feature-flags`. No restart needed.
>
> **Email verification** is configured from the admin settings page. Two providers are supported:
> - **Brevo API** — free tier 300 emails/day, no credit card required but account approval needed.
> - **SMTP** — bring your own provider (QQ Enterprises / Gmail / etc.), no approval needed.

## Development

```bash
# Backend tests (uses an isolated test database)
cd backend && python -m pytest tests/ -q

# Frontend type check
cd frontend && npx tsc --noEmit

# Run a single scraper manually
curl -X POST http://127.0.0.1:8102/api/v1/sources/1/sync
```

The project uses Conventional Commits (`feat(auth): ...`, `fix(cache): ...`). See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow, and [AGENTS.md](AGENTS.md) for the commit discipline and layering rules enforced in this repo.

CI runs these gates on every PR:

- **Frontend type check** (`tsc --noEmit`).
- **Frontend unit tests + coverage gate** on `src/lib` pure logic modules.
- **Lint** (`ruff`) on changed Python files (incremental, not a full-history sweep).
- **Layering check** (AST-enforced `api → service → repo` discipline) and **dependency security scan**.
- **Rardar adapter contracts** and the **complete backend + Rardar control
  regression** against a PostgreSQL service.

For local reproduction or a high-risk backend change, `make test-backend` runs
the backend suite against a throwaway `postgres:16-alpine` container on port
5433 and removes it afterwards. Follow the proportional verification paths in
[AGENTS.md](AGENTS.md); an unchanged full suite is not a default requirement
for every task.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and workflow. Feel free to open an issue with the `good first issue` label to find a starter task.

## Special Thanks

[![LINUX DO](docs/images/linuxdo.png)](https://linux.do)

For all things AI, head to [LINUX DO](https://linux.do)! Wishing the community ever greater success~

## License

Licensed under the [Apache License, Version 2.0](LICENSE). Copyright © 2026 fxbin.
