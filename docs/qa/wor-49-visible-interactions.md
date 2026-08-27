# WOR-49 可见交互验收矩阵与模式边界

## 1. 文档状态

- 对应 issue：`WOR-49`
- 状态：QA 契约基线；不代表前后端实现已经通过
- 测试数据：`tests/acceptance/wor-49-visible-interactions.json`
- 契约自检：`pwsh -File tests/acceptance/validate-wor-49.ps1`

本轮目标是消除“按钮可见但点击无反馈”。任何可聚焦、可点击或视觉上表现为操作入口的控件，都必须满足以下三种结果之一：完成动作并反馈、打开可操作界面，或以禁用态就地说明能力边界。点击后没有 UI 变化、没有可访问状态变化且没有错误提示，一律判定失败。

## 2. 测试范围与统一判定

### 2.1 范围

- 页面：全局导航、数据集、评测任务、评测报告、样本诊断。
- 模式：`mock` 与 `api` 各执行一遍 P0；P1 至少做浏览器交互验证。
- 状态：正常、加载、空数据、部分数据、请求失败、写入冲突。
- 契约：数据集创建/导入、任务创建/读取、复核写入、报告导出。
- 文档：README 必须说明两种模式的能力差异和禁止静默回退规则。

### 2.2 通过规则

1. P0 用例在两种模式下均有确定结果，且没有未解释的占位按钮。
2. mock 写操作可以使用内存状态，但必须标识为演示数据；浏览器刷新导致重置时要提前说明。
3. API 模式必须调用真实 HTTP 契约。服务不可用或未实现时显示错误/边界提示，不得回落到 mock 后显示成功。
4. 异步动作在 100 ms 内给出 loading/disabled/pressed 等反馈；成功和失败均可由可访问文本感知。
5. 写失败时不得伪造成功状态；表单内容、排除原因等用户输入保留，可安全重试。
6. 导出 JSON 文件非空、schema 版本明确且标识当前任务；若前端额外提供 CSV，则单元格以 `= + - @` 开头时必须做公式注入防护。
7. 复核结果在诊断页、报告列表和筛选计数间一致。

## 3. 前后端契约门禁

### 3.1 当前基线观察（2026-08-27，`main` commit `db3271a`）

- 主分支已包含可运行的前后端 MVP 骨架，但本轮列出的多个按钮仍是占位交互。
- 前端当前读取 `/api/v1/projects/{projectId}/datasets`、`/evaluations`、`/report` 和 `/samples/{sampleId}`。
- 后端当前提供 `/api/v1/datasets` 与 `/api/v1/evaluation-jobs`，没有项目路径层级。
- 后端尚无样本复核写入与报告导出；前端 HTTP client 也只有 GET。

因此当前只能判定“契约未对齐/实现待验收”，不能判定 API 模式闭环通过。WOR-49 前后端 PR 合并前必须使用同一份 OpenAPI 或共享类型固定以下逻辑操作；前端调用、后端 OpenAPI 和测试断言必须完全一致。

### 3.2 后端 WOR-49 PR #14 对齐结果（head `84dbc57`）

PR #14 已补数据集写入、任务创建/读取、复核 PATCH 与 JSON 报告导出，并在 `tests/backend/test_write_contracts.py` 覆盖 201/202、422、404、持久化和 OpenAPI 路径。审计时该 PR 与 `main` 冲突，且前端仍未调用这些写接口，故只记为“后端契约已提出”，不记为端到端通过。

| 逻辑操作 / 前端方法 | PR #14 路径 | 最小成功结果 | 关键失败 |
| --- | --- | --- | --- |
| `createDataset` | `POST /api/v1/datasets` | 201 + 服务端 ID + `draft`；可原子携带 samples | 422 字段错误，不持久化 |
| `importDatasetSamples` | `POST /api/v1/datasets/{dataset_id}/samples:import` | 201 + `accepted=6,rejected=0` | 行/字段可定位；原子模式无半批数据 |
| `listDatasets` | `GET /api/v1/datasets` | 稳定列表与计数 | 非法分页 422 |
| `createEvaluation` | `POST /api/v1/evaluation-jobs` | 202 + job ID + queued 快照 | 幂等冲突 409；无脏任务 |
| `listEvaluations` / `getEvaluation` | `GET /api/v1/evaluation-jobs[/{job_id}]` | 状态和单调进度 | 未知任务 404 |
| `listEvaluationSamples` | `GET /api/v1/evaluation-jobs/{job_id}/samples` | `review_status` 与计数一致 | 未知任务 404 |
| `updateSampleReview` | `PATCH /api/v1/evaluation-jobs/{job_id}/samples/{sample_id}/review` | confirmed/dismissed 持久化并返回样本 | 非法枚举 422；未知样本 404；未完成 409 |
| `exportReport` | `GET /api/v1/evaluation-jobs/{job_id}/report/export` | schema `1.0` 的 JSON bundle，含 report/samples | 未完成报告 409；未知任务 404 |

仍需前后端共同决策项目作用域：前端现有 `/projects/{projectId}/...` 与 PR #14 的无项目层级路径不能同时作为最终事实来源。若 MVP 暂不实现项目隔离，前端 client 应显式适配上述路径并在文档声明；不得在两套路由间猜测或失败后回退 mock。

统一错误至少包含稳定 `code`、可读 `message` 和 `request_id`。前端只依赖状态码和 `code` 分支，不解析 message 文案。

## 4. 可见交互验收矩阵

以下 15 个核心交互的详细输入、步骤和两种模式期望由 JSON fixture 固定；表内结果栏在实现 PR 可运行后填写，未执行不得写“通过”。

| ID | 级别 | 页面 / 控件 | Mock 重点 | API 重点 | 自动化层 | 当前结果 |
| --- | --- | --- | --- | --- | --- | --- |
| W49-UI-001 | P0 | 数据集 / 新建数据集 | 弹窗、内存新增、重置说明 | 201、失败保留输入 | FE + API | 待实现 |
| W49-UI-002 | P0 | 数据集 / 导入样例 | 6 条摘要、不上传外部 | 原子导入、行级错误 | FE + API | 待实现 |
| W49-UI-003 | P0 | 数据集 / 筛选 | 面板、计数、清除 | 参数一致、空态 | FE | 待实现 |
| W49-UI-004 | P0 | 数据集 / 刷新 | fixture 加载反馈 | 保留筛选与旧数据 | FE | 待实现 |
| W49-UI-005 | P0 | 任务 / 新建评测 | 明确确定性演示 | 202、幂等、状态读取 | FE + API | 待实现 |
| W49-UI-006 | P0 | 任务 / 筛选 | completed 集合正确 | query 与结果一致 | FE | 待实现 |
| W49-UI-007 | P0 | 任务 / 刷新状态 | 进度不回退 | 状态机契约 | FE + API | 待实现 |
| W49-UI-008 | P0 | 报告 / 导出 | 非空 JSON、文件名 | schema、任务与复核状态一致 | FE + API | 后端 PR #14 已覆盖；FE 待实现 |
| W49-UI-009 | P1 | 报告 / 对比版本 | 打开入口或明确禁用 | 无 API 时禁止伪回退 | FE | 待实现 |
| W49-UI-010 | P0 | 报告 / 复核筛选 | 集合、计数、空态 | reviewStatus 一致 | FE | 待实现 |
| W49-UI-011 | P0 | 诊断 / 复制回答 | 精确原文、成功/失败提示 | 同 mock | FE | 待实现 |
| W49-UI-012 | P0 | 诊断 / 打开源文档 | 无 URL 明确禁用 | 仅允许 http/https | FE | 待实现 |
| W49-UI-013 | P0 | 诊断 / 确认故障归因 | 状态联动 | confirmed 持久化、409 | FE + API | 待实现 |
| W49-UI-014 | P0 | 诊断 / 排除诊断 | 确认与状态联动 | dismissed 持久化、错误回滚 | FE + API | 后端 PR #14 已覆盖；FE 待实现 |
| W49-UI-015 | P1 | 全局 / 使用帮助 | fixture 与重置边界 | base URL、错误、不回退 | FE | 待实现 |

### 4.1 现有可见控件补充检查

除上表外，浏览器巡检还必须逐一覆盖：侧栏收起、项目切换、全局搜索、数据集“更多操作”、搜索输入、空态 CTA、查看报告、诊断链接、文档选择、引用 chip、返回链接和重试按钮。已具备行为的验证导航/状态变化；暂不交付的入口改为原生禁用或不可聚焦的禁用控件，并提供可见原因。不得只用 `onClick={() => {}}`、空函数或仅 console 日志充当反馈。

## 5. 模式边界专项

| ID | 输入/前置 | 操作 | 期望 |
| --- | --- | --- | --- |
| MODE-001 | `VITE_API_MODE=mock` | 创建数据集、复核样本、导出报告 | 页面标识 MOCK；动作使用本地 fixture/内存；不发业务 HTTP 请求；不宣称持久化或真实模型运行 |
| MODE-002 | `VITE_API_MODE=api`，API 正常 | 执行所有 P0 | 写操作命中真实 API，服务端响应是事实来源；刷新后已写状态仍存在 |
| MODE-003 | `VITE_API_MODE=api`，API 断开 | 创建/复核/导出 | 显示超时或网络错误和重试；不生成成功 toast、不落 mock 状态、不静默切换模式 |
| MODE-004 | API 返回 422/409/500 | 分别提交无效表单、制造复核冲突、注入服务错误 | 422 定位字段，409 提示刷新，500 保留 request ID；安全场景才显示重试 |
| MODE-005 | 配置非法 `VITE_API_MODE` 或空 base URL | 启动页面 | 使用文档化默认值并在开发环境警告，或启动失败并说明配置；不得显示 LIVE API 后实际读取 mock |
| MODE-006 | 对比/源文档等能力无契约或缺数据 | 点击入口 | 明确禁用原因或阶段提示；不打开空弹窗、不猜测外链 |

## 6. 样例数据与操作步骤

1. 使用 `examples/eval-samples/valid-samples.jsonl` 导入，期望 6 条；数据包含中文、引用与检索上下文，可同时覆盖 UTF-8、导入摘要和报告渲染。
2. 新建名为 `WOR-49 可见交互验收集` 的数据集，重复创建用于检查 ID 唯一性，空名称用于 422。
3. 使用 `rag-retrieval-miss-001` 分别做 confirmed 与 dismissed 复核，断言 `reviewed_at` 与报告筛选同步。
4. 复制断言使用完整文本“企业版审计日志默认保留 180 天。”，同时注入 Clipboard API reject 覆盖失败提示。
5. 导出验证 schema `1.0` JSON bundle、task ID、review status 和非空样本；若前端提供 CSV，再增加以 `=HYPERLINK(...)` 开头的恶意问题文本验证公式防护。

## 7. 自动化与 CI 门禁建议

### 7.1 当前可执行

```powershell
pwsh -File tests/fixtures/validate-fixtures.ps1
pwsh -File tests/acceptance/validate-wor-49.ps1
```

第一条验证既有评测 fixture；第二条验证 15 个交互均有 mock/API 期望、写操作映射、README 边界和文档追踪。它们只证明测试资产一致，不证明应用交互通过。

### 7.2 前后端 PR 必须增加

- 前端：React Testing Library 覆盖每个 P0 的 success/error，用户事件必须断言可访问反馈；Playwright 在 mock 和 API stub 两种配置各跑一次主路径。
- 后端：OpenAPI contract test 固定上述 operationId；写 API 覆盖 2xx、422、404/409、持久化和幂等；导出断言 headers、body 与公式注入防护。
- 集成：对同一 task/sample 跑“创建任务 → 状态读取 → 报告 → 复核 → 复核筛选 → 导出”，禁止通过跨 PR mock 伪造 API 成功。
- CI 顺序：fixture/QA contract → backend unit/contract → frontend unit/typecheck/build → mock E2E → API integration E2E。任一 P0 失败阻断合并。

每次 CI 输出必须记录 Git SHA、模式、base URL（不含凭据）、失败用例 ID 和 artifact。真实 provider 不进入本轮门禁。

## 8. PR #13/#14/#15 组合验收执行记录（2026-08-27）

### 8.1 组合与环境

- 基线：`main` `db3271a`。
- 组合 head：PR #13 `37ce728`、PR #14 `9139264`、PR #15 `1aa8f20`。
- 本地顺序：`#13 -> #14 -> #15`，三次 merge 均无冲突。该顺序先落 QA 门禁、再落后端契约、最后落前端调用；当前文件集合不存在 Git 层硬依赖，但建议保持此顺序以便逐步验证。
- 自动化：前端原始套件 `22 passed`；附加审计用例后 `25 passed`。后端 `49 passed`，分支覆盖率 `92.97%`；Ruff、QA contract 和仓库 contract 均通过。
- API 实例：本地 FastAPI + SQLite，前端使用 `VITE_API_MODE=api`、`VITE_API_BASE_URL=/api/v1` 的生产构建，经同源转发访问真实 API。12 条示例原子写入返回 `sample_count=12, imported_samples=12`；任务从 `queued` 到 `completed/succeeded`；报告导出 schema `1.0`；confirmed/dismissed 均持久化并进入后续导出。
- 浏览器环境：本轮内置浏览器发现结果为空，无可用 `iab` 实例。按浏览器控制规范未改用其他浏览器后端，因此下表“真实浏览器”均为环境阻断，不得视为通过。

### 8.2 13 项 P0 结果

| ID | 组合自动化 / API | 真实浏览器 | 证据与判定 |
| --- | --- | --- | --- |
| W49-UI-001 | 通过 | 阻断 | mock 创建测试通过；真实 `POST /datasets` 返回 201 并持久化草稿 |
| W49-UI-002 | 通过 | 阻断 | mock 空态导入测试通过；真实 API 原子导入 12 条，`accepted/imported=12` |
| W49-UI-003 | 通过 | 阻断 | Testing Library 验证 draft 筛选、计数与结果集合 |
| W49-UI-004 | **失败** | 阻断 | `DatasetsPage` 没有“刷新”按钮；附加可访问角色审计确认 `queryByRole(button, /刷新/)` 为空 |
| W49-UI-005 | 通过 | 阻断 | mock 新建任务测试通过；真实 `POST /evaluation-jobs` 返回 queued，随后完成 |
| W49-UI-006 | 通过 | 阻断 | Testing Library 验证 completed 筛选与空态 |
| W49-UI-007 | **失败** | 阻断 | API 状态可从 queued 读到 completed，但 `EvaluationsPage` 没有“刷新/重新读取状态”控件；附加角色审计确认缺失 |
| W49-UI-008 | 通过 | 阻断 | mock JSON 导出测试通过；真实 `/report/export` 返回 schema `1.0`、report 和 samples |
| W49-UI-010 | 通过 | 阻断 | Testing Library 验证复核分段；真实导出在复核后反映 confirmed/dismissed |
| W49-UI-011 | 通过 | 阻断 | Clipboard mock 断言原文写入并出现“已复制模型回答”反馈 |
| W49-UI-012 | 通过 | 阻断 | mock 源文档详情弹窗测试通过；内部 `kb://` 只展示元数据，不尝试外跳 |
| W49-UI-013 | 通过 | 阻断 | mock 确认反馈测试通过；真实 PATCH confirmed 后导出状态仍为 confirmed |
| W49-UI-014 | 通过 | 阻断 | 附加 UI 审计验证 dismissed 反馈及按钮禁用；真实 PATCH dismissed 后导出状态为 dismissed |

### 8.3 结论

- 组合自动化/API：`11/13` 通过，`2/13` 产品失败（W49-UI-004、W49-UI-007）。
- 真实浏览器：`0/13` 完成，原因是本轮无可用内置浏览器实例；不是产品通过证据。
- 父任务暂不可进入 `in_review`。需补数据集刷新和任务状态刷新入口（含 loading、旧数据保留、错误/重试反馈），增加相应前端测试；随后在可用的内置浏览器中重新执行 13 项 P0，至少对 mock 全量点击，并对 API 模式执行创建、状态读取、报告、复核和导出闭环。

## 9. 风险清单

| 风险 | 影响 | 门禁/缓解 |
| --- | --- | --- |
| 前后端资源路径和命名不一致 | API 模式全部失败 | OpenAPI operationId + 生成 client；契约测试 P0 |
| API 失败后静默使用 mock | 演示虚假成功 | MODE-003；断言无业务 fixture 注入、无成功 toast |
| mock 写入仅改局部组件 | 返回列表后状态丢失 | 共享 mock store；跨路由断言复核和计数 |
| 双击/重试产生重复任务 | 污染结果 | 前端 pending 禁用 + 后端 Idempotency-Key |
| 导出空文件或 CSV 公式注入 | 数据错误/安全风险 | 内容与 headers 断言；危险前缀转义 |
| Clipboard/弹窗只靠视觉反馈 | 无障碍用户无法感知 | `aria-live`、focus trap、键盘与 reject 测试 |
| 源文档 URL 缺失或不安全 | 空白页、开放跳转 | URL allowlist；缺失时原生禁用并说明 |
| 未合并 PR 被当作主干能力 | 验收结论失真 | 记录 base/head SHA；只对实际 checkout 的组合报告结果 |
