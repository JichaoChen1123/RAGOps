# WOR-52 功能完善回归验收记录

## 1. 验收结论

- 验收基线：`main` `89012f8`，已包含后端 PR #14 和前端 PR #15。
- 自动化与 API 结论：通过。前端 4 个测试文件、33 个用例通过；后端与评测 50 个用例通过，分支覆盖率 92.97%；类型检查、Ruff、生产构建、fixture、WOR-49 交互契约和仓库文档/结构化文件校验均通过。
- 真实浏览器结论：环境阻断。本轮内置浏览器发现列表为空，没有可用 `iab` 实例；未改用其他浏览器后端，因此不能把下表的“浏览器手工验收”写成通过。
- 发布判定：产品自动化和后端 API 没有剩余 P0 失败；最终可见交互验收仍需在可用浏览器中执行第 3 节清单，或由项目负责人明确接受以 Testing Library 用户事件测试替代本轮真实浏览器门禁。

本文只记录本轮真实执行结果。mock 页面通过不代表真实服务、真实 LLM 或生产 RAG provider 已接入。

## 2. 测试范围与证据

| 层级 | 输入与操作 | 期望 | 本轮结果 / 证据 |
| --- | --- | --- | --- |
| 前端路由 smoke | 直达概览、数据集、任务、报告、诊断和未知路由 | 页面主标题稳定；未知路由显示 404；无路由级异常 | 通过，`tests/frontend/route-smoke.test.tsx` |
| 前端按钮 smoke | 在五个核心页面查找刷新、创建、筛选、导出、诊断和复核入口 | 控件可见；按钮不是无理由禁用态 | 通过，新增 5 组页面级动作矩阵 |
| 前端交互 | 用用户事件执行搜索、筛选、创建、导入、详情、复制、刷新/重试、导出、引用联动、复核和工作台操作 | 每次点击产生路由、弹窗、状态或可访问反馈；失败保留旧数据并可重试 | 通过，`tests/frontend/interactions.test.tsx` |
| 后端写入 API | 创建含样本数据集、发布、创建任务、读取状态、复核、导出 | 201/202；任务 queued 后完成；复核与导出持久化一致 | 通过，`tests/backend/test_write_contracts.py` |
| 后端异常 | 空 owner/version、非法 review 状态、未知样本、意外 500 | 422/404/500 使用稳定且可读的错误信封，不泄漏内部异常 | 通过 |
| 算法与样例 | 6 条有效样例、9 条无效样例、8 个指标 oracle | 导入原子性、状态计数、指标和诊断规则结果可复算 | 通过，`tests/backend`、`tests/evaluation` |
| 文档与工程 | Markdown、本地链接、JSON/JSONL、YAML、Ruff、typecheck、build | 全部结构有效；本地命令可重复 | 通过 |
| 真实浏览器 | 本地工作台逐项点击 | 可见结果与自动化断言一致 | 阻断：本轮没有可用内置浏览器实例 |

## 3. 浏览器手工验收清单

下列步骤在 mock 模式执行；API 模式需另按第 5 节校验网络和持久化。每项只有观察到期望结果才可勾选。

| ID | 页面 / 输入 | 操作步骤 | 期望结果 | 本轮浏览器 |
| --- | --- | --- | --- | --- |
| W52-UI-001 | 概览正常数据 | 点击“刷新数据”、“查看趋势看板”、“新建评测” | 显示刷新反馈；打开趋势弹窗；进入任务页并可打开新建弹窗 | 阻断 |
| W52-UI-002 | 数据集正常数据 | 搜索“账单”，按状态筛选，打开“更多操作” | 结果集合正确；详情、复制 ID、归档均有可见或可访问反馈 | 阻断 |
| W52-UI-003 | 数据集空态 | 点击“导入首个数据集”，确认导入；再新建空数据集 | 列表新增明确标记的 Mock 数据，toast 说明仅页面会话保存 | 阻断 |
| W52-UI-004 | 数据集刷新失败 stub | 点击刷新，等待错误，再点重试 | pending 时按钮禁用且旧列表/筛选保留；错误可读；重试成功更新 | 阻断 |
| W52-UI-005 | 评测任务正常/空态 | 搜索任务，筛选状态，新建 completed Mock 任务，点击已有任务“查看报告” | 搜索/筛选正确；新任务标记 Mock；真实 fixture 报告可打开 | 阻断 |
| W52-UI-006 | 任务刷新失败 stub | 点击“刷新任务状态”，注入失败后重试 | 旧表格保留；错误和重试入口可感知；running 可刷新为 completed | 阻断 |
| W52-UI-007 | 报告页 | 切换全部/待复核/已确认，打开版本对比，分别导出 JSON/Markdown | 集合和计数一致；对比弹窗有基线；导出非空且有成功反馈 | 阻断 |
| W52-UI-008 | 报告失败样本 | 点击 `sample-042` 的“诊断” | 进入正确深链，问题与诊断标签匹配 | 阻断 |
| W52-UI-009 | 样本诊断 | 复制回答，点击引用 `[2]`，打开源文档 | 剪贴板与原文一致；引用定位“订单退款通用规则”；内部 `kb://` 只展示元数据 | 阻断 |
| W52-UI-010 | 样本诊断 pending | 分别重载页面后点击“确认故障归因”和“排除诊断” | 对应按钮进入 pressed/disabled；状态文案与 toast 一致 | 阻断 |
| W52-UI-011 | 工作台 | 搜索“数据集”，打开帮助，折叠侧栏，打开项目菜单 | 搜索导航、帮助弹窗和折叠状态有效；当前项目有反馈，其他项目明确禁用原因 | 阻断 |

## 4. 后端 API 验收矩阵

| ID | 输入与步骤 | 期望结果 | 自动化 |
| --- | --- | --- | --- |
| W52-API-001 | `POST /datasets`，携带名称、owner、version 和 1 条样本 | 201；`sample_count=1`、`imported_samples=1`；数据可读 | 通过 |
| W52-API-002 | owner/version 为空白 | 422；错误字段恰为 owner/version；不写脏数据 | 通过 |
| W52-API-003 | 发布数据集后 `POST /evaluation-jobs` | 202 queued；随后 GET 为 completed/succeeded；配置版本可追踪 | 通过 |
| W52-API-004 | 将同一样本从 pending 改为 dismissed，再重置 pending | dismissed 写入 `reviewed_at`；pending 清空时间；列表与导出状态始终一致 | 通过，WOR-52 新增回归 |
| W52-API-005 | 非法 review 枚举、未知 sample | 分别为 422 `VALIDATION_ERROR`、404 `RESOURCE_NOT_FOUND` | 通过 |
| W52-API-006 | `GET /report/export` | schema 为 `1.0`；report 状态和 sample 复核状态与持久层一致 | 通过 |
| W52-API-007 | 读取 OpenAPI | 数据集 POST、任务 POST、复核 PATCH、报告导出路径均存在；枚举固定为 pending/confirmed/dismissed | 通过 |
| W52-API-008 | 注入未处理异常 | 500 `INTERNAL_ERROR`；带 request ID；响应不包含敏感实现细节 | 通过 |

## 5. Mock 与 API 模式边界

| 能力 | Mock 模式 | API 模式 |
| --- | --- | --- |
| 数据来源 | 内置脱敏 fixture 和浏览器内存状态 | `/api/v1` 下的真实 HTTP 资源接口 |
| 数据集/任务写入 | 使用 `mock-*` ID，只在当前页面会话存在，刷新后重置 | 调用 `POST /datasets`、`POST /evaluation-jobs`，服务端响应为事实来源 |
| 报告/诊断 | 固定演示报告和诊断，可验证 UI 链路 | 调用报告、样本、复核和导出 API；错误时不得静默回退 mock |
| 概览趋势 | fixture 数据 | 后端暂无项目聚合/趋势接口，只能展示明确的 MVP 边界 |
| 归档/项目切换 | 可做 Mock 行为或给出明确提示 | 没有契约的操作必须禁用或提示，不得伪造成功 |
| 模型执行 | 不调用真实模型 | 当前仍是本地确定性执行器，不是外部 LLM/RAG provider |

API 模式的最终浏览器闭环仍需在真实后端运行时补测：创建数据集并发布、创建任务、刷新到完成、查看报告、复核样本、导出并刷新页面确认状态持久化。

## 6. 样例数据建议

- 主流程继续使用 `examples/eval-samples/valid-samples.jsonl` 的 6 条合成 UTF-8 样本；它们覆盖正确回答、检索缺失、上下文污染、引用缺失、重排边界和不可回答。
- 参数校验使用 `invalid-samples.jsonl` 的 9 条 oracle；每次失败都要断言字段/类型/稳定错误码和原子回滚，不能只断言 HTTP 422。
- 指标回归使用 `metric-cases.json` 的 8 组确定性 oracle；浮点断言保留分子、分母、排位或 excluded count 证据。
- UI 浏览器补测固定使用 `sample-042`，因为它同时覆盖引用联动、源文档、confirmed/dismissed 和报告筛选计数。
- 后续真实 provider 金标集应与 Prompt 调参集隔离，固定 provider/model/Prompt/索引版本并记录重复测量方差；不得把一次非确定性分数作为 PR 阻断真值。

## 7. CI 质量门禁建议

当前 PR 阻断门禁应保持：

1. Ruff 和后端/算法全量 pytest，启用 branch coverage，应用总覆盖率不低于 85%。
2. 前端 typecheck、Vitest 和 production build 全部通过；`route-smoke.test.tsx` 的关键动作矩阵属于 P0。
3. 仓库校验覆盖 Markdown 链接、JSON/JSONL、YAML 和 fixture oracle；WOR-49 交互契约继续校验 mock/API 双模式和写操作映射。
4. Docker Compose 构建只在前三组门禁通过后运行。

下一步应增加浏览器 E2E：mock 模式覆盖第 3 节全部点击；API 模式覆盖“写入 → 状态刷新 → 报告 → 复核 → 导出 → 刷新持久化”。失败时上传脱敏截图、trace、Git SHA、模式和 base URL；不得通过自动重跑隐藏 flaky。

## 8. 本地复现命令

```powershell
$env:UV_CACHE_DIR = '.uv-cache'
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run --project backend python scripts/validate_repository.py

npm --prefix frontend ci --cache frontend/.npm-cache --prefer-offline --no-audit --no-fund
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build

.\tests\fixtures\validate-fixtures.ps1
.\tests\acceptance\validate-wor-49.ps1
```

受限 Windows 运行器可能阻止 Vite/Vitest 创建子进程；这类 `spawn EPERM` 必须在允许子进程的本地终端或 CI 重跑，并在结果中标注环境差异。

## 9. 剩余风险

| 风险 | 当前影响 | 门禁 / 缓解 |
| --- | --- | --- |
| 本轮没有可用内置浏览器 | 无法形成真实点击和视觉布局证据 | 在可用浏览器补跑第 3 节；未执行前不得宣称手工验收通过 |
| 不做真实 LLM/RAG provider | 无法证明外部模型质量、限流、超时、成本、索引漂移和 judge 稳定性 | PR 使用确定性执行器；夜间固定金标集和版本做漂移/故障测试 |
| API 模式未完成真实浏览器 E2E | 前后端映射或 CORS/代理问题可能只在部署态暴露 | 增加 API 模式浏览器闭环和 Docker Compose E2E |
| 后端没有项目级资源隔离 | 前端 `projectId` 只是工作台上下文，不能代表多租户隔离 | 冻结项目作用域契约后增加越权与跨项目测试 |
| Mock 状态为组件内内存 | 跨路由或刷新后写入结果丢失 | 页面明确标记 Mock；演示前说明重置规则；不要当成持久化证据 |
| 内部源文档为 `kb://` | 当前只能展示元数据，不能验证真实文档权限和失效链接 | 引入安全的 http(s) allowlist、权限校验和无 URL 禁用态 |
| TestClient 依赖迁移预警 | 后续 FastAPI/Starlette/httpx 升级可能破坏测试运行 | 锁定兼容版本并建立依赖升级 PR 的单独回归 |
