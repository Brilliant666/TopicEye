# Agent Guidelines

## Commit Discipline

Follow the existing project history. Recent commits use concise Conventional
Commit-style messages with Chinese summaries:

```text
fix(auth): 降低登录链路 SQLite 写锁等待
fix(cache): 重试统计工作台启动预热
fix(trending): 合并重复信源筛选项
```

Use this shape for new commits:

```text
<type>(<scope>): <中文说明>
```

Preferred types:

- `fix`: bug fixes, permission changes, UI behavior corrections, config safety fixes
- `feat`: user-visible new capability
- `chore`: tooling, scripts, repository hygiene, non-product maintenance
- `test`: tests only
- `docs`: documentation only

Preferred scopes:

- `auth`, `cache`, `trending`, `backend`, `frontend`, `config`, `db`, `docs`, `test`

## Commit Boundaries

- Keep each commit focused on one user-visible behavior, risk boundary, or maintenance concern.
- Do not mix backend, frontend, docs, and config changes unless they are required for the same fix.
- Put tests in the same commit as the behavior they verify.
- Keep local-only files out of commits, especially `backend/.env`, databases, venvs, caches, screenshots, and generated browser artifacts.
- Stage explicit paths. Avoid `git add -A` when the worktree contains unrelated or user-owned changes.

## Before Committing

Inspect the staged diff:

```bash
git diff --cached --stat
git diff --cached --summary
```

Run the smallest relevant verification:

- Backend Python syntax: `python -m py_compile <changed-python-files>`
- Backend tests: `python -m pytest <relevant-tests> -q`
- Shell scripts: `bash -n <script>`
- Frontend type check: `cd frontend && npx tsc --noEmit`

Note: `frontend` currently has an `npm run lint` script that invokes `next lint`,
which may fail under the installed Next.js version by treating `lint` as a
project directory. Prefer `npx tsc --noEmit` unless the lint script is fixed.

## Rewriting Local Commits

If asked to adjust recent commits:

- First confirm the worktree is clean.
- Create a backup branch before rewriting, for example:

```bash
git branch backup/recent-before-rewrite HEAD
```

- Preserve the final file tree unless the user explicitly asks for content changes.
- After rewriting, compare with the backup branch:

```bash
git diff backup/recent-before-rewrite..HEAD
```

An empty diff means the rewrite only changed commit history, not project content.

## Commit Examples

Good:

```text
fix(auth): 登录页隐藏应用导航
fix(auth): 移出默认管理员种子凭据
fix(backend): 整理后端根目录诊断脚本
docs: 补充 agent 提交规范
```

Avoid:

```text
Update stuff
Fix bugs
Move admin seed credentials to env
Deduplicate trending source filters
```
