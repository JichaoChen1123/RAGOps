# MVP 骨架验收与质量门禁

本文定义 RAGOps MVP 在 `数据集 → 评测任务 → 样本结果 → 报告` 最小闭环上的可重复验收。执行结果必须记录真实输入、命令和通过/失败/未执行项；mock 页面通过不能替代真实前后端契约通过。

## 测试范围

- 后端：FastAPI 路由、Pydantic 参数校验、SQLite 持久化、任务状态流转、确定性评测器和报告聚合。
- 算法：`valid-samples.jsonl` 的可实现诊断标签与 `metric-cases.json` 的确定性指标 oracle。
- 前端：项目概览、数据集、评测任务、报告、样本诊断和 404 的直达路由 smoke；当前使用脱敏 mock 数据。
- 工程：Python lint、后端/评测测试、覆盖率、前端类型检查/测试/构建、Markdown/fixture/YAML 校验和 Docker Compose 构建。

不在当前通过范围内：真实 provider、LLM judge、浏览器级 E2E、前端真实 API 模式的端到端闭环、性能与故障恢复。

## 测试矩阵与验收标准

| ID | 输入与操作 | 期望结果 | 自动化位置 |
| --- | --- | --- | --- |
| MVP-API-001 | 请求 `/health/live`、`/health/ready` 和 OpenAPI | 健康检查为 200；关键数据集、任务和报告路径存在 | `tests/backend/test_mvp_acceptance.py` |
| MVP-API-002 | 将 6 条 `valid-samples.jsonl` 通过导入 API 写入草稿并发布 | 接受 6、拒绝 0；版本为 published；内容 SHA-256 可追溯 | `tests/backend/test_mvp_acceptance.py` |
| MVP-API-003 | 将 `invalid-samples.jsonl` 的 9 条 oracle 输入逐类提交 | 全部返回 422；字段/类型/消息与 oracle 对应；批次原子回滚 | `tests/backend/test_mvp_acceptance.py` |
| MVP-API-004 | 对已发布数据集创建评测并读取任务 | 创建响应为 queued；随后为 succeeded；进度 1.0；6 条样本全部成功；起止时间存在 | `tests/backend/test_mvp_acceptance.py` |
| MVP-API-005 | 读取样本结果和报告 | 报告总数守恒；成功率 1.0；Recall@3 宏平均 0.6，5 条计入、1 条不适用 | `tests/backend/test_mvp_acceptance.py` |
| MVP-ALG-001 | 读取 `metric-cases.json` 调用指标模块 | Recall/MRR/NDCG、上下文、引用和空分母行为与 oracle 一致 | `tests/evaluation/` |
| MVP-ALG-002 | 读取有效 fixture 的期望诊断 | 已实现标签必须产生 confirmed/suspected 规则；未实现标签显式列为风险 | `tests/backend/test_mvp_acceptance.py` |
| MVP-FE-001 | 直接打开五个 MVP 路由和未知路由 | 每个页面出现稳定主标题；未知路由显示 404；无路由级异常 | `tests/frontend/route-smoke.test.tsx` |
| MVP-CI-001 | 执行 PR CI | 后端、评测、覆盖率、前端和仓库契约全部通过后才允许 Docker 构建 | `.github/workflows/ci.yml` |

## 可重复执行命令

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run --project backend python scripts/validate_repository.py

npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build

docker compose config --quiet
docker compose build
```

Windows 受限运行器若不允许 pytest 写系统临时目录，可将 `--basetemp` 指向仓库内专用临时目录；该目录只是运行产物，不得提交。CI 的 Ubuntu runner 不需要此覆盖。

## 样例数据与 oracle

- `valid-samples.jsonl`：6 条合成、脱敏、UTF-8 样本，覆盖正常、检索缺失、重排边界、上下文污染、缺引用和不可回答。
- `invalid-samples.jsonl`：9 条参数/引用/批次边界输入。API 对外统一返回 `VALIDATION_ERROR`，测试继续核对字段、Pydantic 类型或稳定消息，避免只断言 HTTP 422。
- `metric-cases.json`：8 组无需模型即可复算的指标 oracle。评测单元测试直接读取该文件。

后续扩充数据时，应保持合成/授权来源、稳定 `sample_id`、明确 gold evidence 和版本化 oracle；不能把测试集用于 Prompt 调参。

## CI 质量门禁

- `ruff` 覆盖 `backend/app`、全部 `tests` 和 `scripts`。
- pytest 同时执行后端 API、评测指标/诊断和 fixture 验收，应用总覆盖率不得低于 85%，并启用 branch coverage。
- 前端必须通过 TypeScript、Vitest 路由/API client 测试和 Vite 生产构建。
- 仓库契约校验必须通过 Markdown、本地链接、JSON/JSONL、fixture oracle 和 YAML 解析。
- Docker Compose 配置与镜像构建依赖前三组门禁成功；本机无 Docker 时只能记录为未执行，不能写成通过。

## 风险清单

| ID | 风险 | 当前证据 | 建议 |
| --- | --- | --- | --- |
| R-MVP-01 | 前端真实 API client 与后端资源路由/响应结构不一致 | 前端请求 `/projects/{id}/...`，后端提供 `/datasets`、`/evaluation-jobs`；Compose 默认 mock | 新建契约适配任务，完成后把 Compose 默认切到 api 并增加浏览器 E2E |
| R-MVP-02 | 两个 fixture 诊断标签尚无确定性闭环 | `model_hallucination` 未实现；`rerank_ineffective` 缺少 `rank_before` 证据且规则名不同 | 冻结标签映射，补充可判定输入和对应规则，再移除已知未支持集合 |
| R-MVP-03 | 当前前端测试是 jsdom 组件/路由 smoke，不是浏览器 E2E | 未启动浏览器、Nginx 或真实后端 | 增加 Playwright fake-provider P0 流程与失败截图/trace |
| R-MVP-04 | 本地环境不一定具备 Docker | 无 Docker 时无法验证 Compose build | 以 GitHub CI Docker job 作为合并门禁，并在交付评论如实记录本地未执行 |
| R-MVP-05 | TestClient 依赖出现迁移预警 | Starlette 提示当前 `httpx` TestClient 用法后续迁移到 `httpx2` | 锁定兼容版本并单独安排依赖升级回归 |
