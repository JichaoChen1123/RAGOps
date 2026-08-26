# 本地开发与工程交付

## Docker Compose 一键启动

仓库根目录下的唯一启动命令是：

```bash
docker compose up --build
```

Compose 会构建并启动两个服务：

- `backend`：Python 3.11、FastAPI、SQLite 持久化卷，暴露 `8000`。
- `frontend`：Node 24 构建、Nginx 静态托管，暴露 `5173`。

服务启动顺序由后端 readiness healthcheck 控制；前端只会在后端健康后启动。默认值已写入 `docker-compose.yml`，因此 `.env` 不是启动前置条件。需要覆盖端口、日志级别或数据源模式时：

```bash
cp .env.example .env
docker compose up --build
```

PowerShell 对应命令：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

`.env` 已加入 `.gitignore`。示例文件不含密钥；后续如果引入真实凭证，只能通过本地环境或受控 secret store 注入。

### 当前接口边界

前端真实 client 当前请求 `/api/v1/projects/{project_id}/...`，后端 MVP 当前提供 `/api/v1/datasets` 与 `/api/v1/evaluation-jobs` 等资源路由。两者是 Stage 3 已验收的独立契约，本次集成不擅自改写。

因此 Compose 默认 `VITE_API_MODE=mock`，前端演示链路可用；真实后端可通过 Swagger UI 独立验证。将模式改为 `api` 前，需要先完成项目级聚合路由或前端适配，并新增契约测试。

## 不使用 Docker 的本地开发

后端：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

前端（默认 mock）：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

## 与 CI 一致的检查

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests/backend scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend -q

npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build

uv run --project backend python scripts/validate_repository.py
docker compose config --quiet
docker compose build
```

`scripts/validate_repository.py` 会检查 Markdown 基础格式与本地链接、JSON/JSONL 可解析性、脱敏 fixture 的关键 oracle，以及 YAML（包括 Compose 和 GitHub Actions）语法。

## Windows Git hook 的 `sh.exe` 风险

受限 Windows 运行环境中，Git for Windows 启动 POSIX hook 时可能失败：

```text
sh.exe: fatal error - couldn't create signal pipe, Win32 error 5
error: 'prepare-commit-msg' hook failed
```

这表示 hook shell 没有启动成功，不代表代码或暂存内容失败。按以下顺序处理：

1. 用 `git status` 确认 Git 操作停留在哪一步，并阅读 `.git/hooks/prepare-commit-msg`，确认该 hook 的真实作用。
2. 先手动运行本页全部质量检查；不要把跳过 hook 当作跳过 lint/test 的方式。
3. 仅为当前 Git 命令指定一个空 hooks 目录，不写全局或仓库级 `core.hooksPath`。
4. 如果 hook 本应添加提交 trailer，手动在提交消息中保留同样的 trailer，再用 `git show -s --format=fuller HEAD` 核对结果。

PowerShell 示例：

```powershell
$emptyHooks = Join-Path (Resolve-Path ..) '.git-hooks-disabled'
New-Item -ItemType Directory -Force $emptyHooks | Out-Null
git -c core.hooksPath=$emptyHooks commit -m 'WOR-46: add Docker and CI baseline' -m 'Co-authored-by: multica-agent <github@multica.ai>'
```

对暂停的 cherry-pick，可在确认原提交消息已包含所需 trailer 后执行：

```powershell
git -c core.hooksPath=$emptyHooks cherry-pick --continue
```

不要使用 `git config --global core.hooksPath ...`，也不要删除平台安装的 hook；全局绕过会影响其他仓库并掩盖真正的安全检查。
