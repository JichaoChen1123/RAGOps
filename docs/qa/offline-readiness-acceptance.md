# 离线基础集成验收记录

## 验收结论

- 验收基线：`10ef6b33c4373ee98f6e82e9a053212e5105252f`，阶段分支 `work/wor-61-offline-readiness`，2026-09-05 独立验收。
- 总结论：**离线验收不通过，需完成 1 项有界前端修复后复测**。后端/评测回归、本地 API 闭环、SQLite 重启持久化、桌面与移动端主流程、断连不回退 mock 均通过；诊断页没有识别后端 `rule_id`，3 条有效诊断均被渲染为 `unclassified`。
- 环境限制：Docker CLI 与 Compose 可用，`docker compose config --quiet` 通过，但本机 Docker Engine 命名管道不存在，因此未执行镜像构建、容器启动和容器重启持久化。此限制没有替代或掩盖本地关键链路验收。
- 范围边界：全程使用人工构造数据、SQLite 与 `mock` 执行器；未读取真实凭据，未调用真实模型、账号、订阅、API 或真实数据，未引入 LangGraph。真实问答效果保持“未评测”。

## 环境与证据

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | Windows，PowerShell |
| Python / uv | Python 3.11.15 / uv 0.12.1 |
| Node.js / npm | v24.18.0 / 11.16.0 |
| 浏览器 | Microsoft Edge 152.0.4191.62，由 `playwright-core` 驱动本机浏览器 |
| 浏览器视口 | 桌面 1440×900；移动 390×844 |
| 后端模式 | `RAGOPS_MODEL_EXECUTION_ADAPTER=mock` |
| 外部调用 | `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` |
| 前端模式 | `VITE_API_MODE=api`，经 Vite 同源代理连接本地 FastAPI |
| 数据 | 页面导入的 12 条人工 2.0 样本；API 重启脚本使用 3 条人工样本 |
| 浏览器持久化任务 | `01a070fb-98f6-72df-906a-63ee29a3a19d` |
| 浏览器持久化样本 | `01a070fb-98fa-7e0c-a24b-0b182707bbd6` |

机器可读浏览器证据保存在 [`screenshots/offline-readiness/browser-api-evidence.json`](screenshots/offline-readiness/browser-api-evidence.json)。截图：

- [API 数据集桌面页](screenshots/offline-readiness/api-dataset-desktop.png)
- [API 报告桌面页](screenshots/offline-readiness/api-report-desktop.png)
- [API 诊断移动页](screenshots/offline-readiness/api-diagnosis-mobile.png)
- [后端重启后的诊断页](screenshots/offline-readiness/api-diagnosis-after-restart.png)
- [后端断开后的显式错误页](screenshots/offline-readiness/api-disconnected-desktop.png)

## 离线验收矩阵

| ID | 输入与操作 | 期望结果 | 实际结果 | 判定 |
| --- | --- | --- | --- | --- |
| A01 | OpenAI 兼容适配器 + 内存 `MockTransport` | 请求只含问题、Prompt、生成参数和允许的上下文；响应映射完整 | 请求/响应、用量、finish reason、request ID 映射断言通过 | 通过 |
| A02 | 在参考答案、gold、历史回答与 metadata 放唯一哨兵 | 哨兵不进入模型 payload | 目标测试通过；真实外部请求为 0 | 通过 |
| A03 | 两次模拟输出、SQLite 重启后复查 | 本次回答独立保存；原始样本/历史回答不被覆盖 | 本地 HTTP 脚本及浏览器刷新/进程重启复查通过 | 通过 |
| A04 | 401/403、429、超时、5xx、网络错误、非法/空响应 | 错误分类稳定；鉴权/格式错误不重试；总尝试和总时长有界；消息脱敏 | 离线契约测试通过 | 通过 |
| A05 | 无凭据启动；假凭据但外部调用关闭 | 应用可启动；真实 transport 在 DNS/socket 前拒绝；不回退 mock | 状态接口、禁用门与 transport spy 断言通过 | 通过 |
| A06 | 前端 API + 后端 mock + provider 未配置 | 三轴同时显示；执行成功不推断质量通过或 100 分 | 页面显示“API 数据 / mock / 未配置”“执行成功 / 未评估 / 未知” | 通过 |
| A07 | 给定上下文、无语义 judge 的引用 | 无假召回率；可解析引用不推断语义支持；未知值不补零 | 报告与目标测试均保持 `not_evaluated`/`not_applicable`/`null` | 通过 |
| A08 | 3 条 2.0、1 条 1.0、9 条非法样本；旧库连续迁移两次 | 字段级错误准确；旧数据保留；迁移幂等；新旧报告可读 | fixture/oracle 与迁移测试通过 | 通过 |
| A09 | 桌面/移动浏览器连接本地 API，导入、发布、运行、报告、诊断、刷新、重启、断连 | 主流程非空且语义正确；重启后数据保留；断连不回退 mock | 主流程、布局、持久化和断连通过，但诊断规则语义错误 | **失败** |
| A10 | 全量回归、Compose 配置、容器闭环 | 现有测试不回退；Docker 可执行则验证容器闭环，否则如实记录 | 回归与 Compose 配置通过；Engine 不可用，容器闭环未执行 | 部分通过 |

## 浏览器 API 模式结果

| ID | 操作 | 观察结果 | 判定 |
| --- | --- | --- | --- |
| B01 | 桌面打开 API 模式工作台 | 三轴为“前端 API 数据 / 执行器 mock / 提供方未配置”；无“真实已验证” | 通过 |
| B02 | 数据集页导入示例 JSONL | 后端创建、导入并发布 12 条 2.0 人工样本，页面显示可用 | 通过 |
| B03 | 创建 mock 任务并进入报告 | 生命周期完成、执行成功、质量未评估、分数未知，任务和报告均有 `SIMULATED` 标识 | 通过 |
| B04 | 打开首条样本 | 参考答案、历史/本次回答、`provided` 上下文、引用空态、未知 Token 均分层展示 | 通过 |
| B05 | 刷新报告与样本页 | ID、回答、运行快照和报告保持一致 | 通过 |
| B06 | 停止并重启后端进程 | 同一任务、样本、回答和参考答案仍可读取 | 通过 |
| B07 | 停止后端并刷新报告 | 显示 HTTP 502、数据载入失败和重试按钮；没有 fixture 报告或成功状态 | 通过 |
| B08 | 390×844 诊断页 | 页面非空，`scrollWidth=390`、`clientWidth=390`，无横向溢出；诊断标签错误见缺陷 D01 | 布局通过，语义失败 |

浏览器请求守卫只允许 `localhost`/`127.0.0.1`；证据中 `external_requests=[]`。最终断连阶段记录的 502 控制台消息是主动停止后端后的预期错误，不是外部调用。

## 实际执行记录

以下命令均在精确基线的独立副本中执行；退出码未特别标注时为 0。受控环境生成的长临时根在记录中归一化为 `$env:TEMP`，其余参数与执行实录一致。

```powershell
uv sync --cache-dir .uv-cache --project backend --extra dev --frozen
uv run --cache-dir .uv-cache --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --cache-dir .uv-cache --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --tb=short --cov=app --cov-branch --cov-report=term --cov-fail-under=85 --basetemp "$env:TEMP\ragops-wor66-pytest-escalated"
```

结果：Ruff 通过；Pytest `109 passed`，分支覆盖率 `90.69%`，仅有 1 条 Starlette `PendingDeprecationWarning`。

```powershell
uv run --cache-dir .uv-cache --project backend pytest -c backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py -q --tb=short --basetemp "$env:TEMP\ragops-wor66-contract"
uv run --cache-dir .uv-cache --project backend python scripts/validate_repository.py
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/validate-wor-49.ps1 -RepoRoot .
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/validate-wor-55.ps1 -RepoRoot .
```

结果：离线契约定向测试 `32 passed`；Markdown/JSON/JSONL/YAML 与 fixture/oracle 检查、既有 WOR-49/WOR-55 门禁均通过。最终仓库校验统计为 40 个 Markdown、14 个 JSON、5 个 JSONL、2 个 YAML；人工资产为 3 条 2.0、1 条 1.0、9 条非法样本以及 provider 脚本和 legacy SQL。

```powershell
npm.cmd --prefix frontend ci --cache .npm-cache --no-audit --no-fund
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
node --check frontend/scripts/offline-readiness-browser.mjs
```

结果：TypeScript 通过；Vitest 5 个文件、41 个测试通过；production build 通过，共转换 1831 个模块；浏览器脚本语法检查通过。

```powershell
$env:UV_CACHE_DIR = (Resolve-Path .uv-cache).Path
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/run-local-restart.ps1 -RepoRoot . -Port 18015
```

结果：3 条人工样本的创建、导入、发布、mock 执行、状态、样本、报告、导出与同一 SQLite 的后端进程重启复查均通过。任务最终为 `completed/succeeded`，质量为 `not_evaluated`；脚本结束后只停止自身启动的服务。

对 production build、浏览器证据及本轮前后端日志扫描 `SENTINEL_FAKE_API_KEY_never_log_this`、`SENTINEL_RAW_PROVIDER_BODY`、`SENTINEL_METADATA_SECRET_7f0b3f`，匹配数为 0。结束检查 `18015/18016/15173` 监听数为 0。

产品浏览器脚本需先按 [浏览器检查表](../../tests/acceptance/offline-readiness/browser-checklist.md) 启动本地前后端，再分三阶段运行：

```powershell
$env:RAGOPS_FRONTEND_URL = 'http://127.0.0.1:15173'
$env:RAGOPS_BROWSER_OUTPUT_DIR = (Resolve-Path docs/qa/screenshots/offline-readiness).Path
$env:RAGOPS_BROWSER_STATE = Join-Path $env:RAGOPS_BROWSER_OUTPUT_DIR 'browser-api-evidence.json'
npm.cmd --prefix frontend run acceptance:offline-browser -- create
npm.cmd --prefix frontend run acceptance:offline-browser -- restart_recheck
npm.cmd --prefix frontend run acceptance:offline-browser -- disconnected
```

三次都完成了相应操作并保留证据；`create=1`、`restart_recheck=1`、`disconnected=1`，共同原因是 D01 仍在验收失败列表中，创建/重启阶段还观察到重复 React key 告警。非零退出码不得通过重跑或忽略改写成通过。

Docker 检查：

```powershell
docker compose config --quiet
docker info --format '{{json .ServerVersion}}'
```

第一条退出码 0；第二条退出码 1，实际错误为 Docker Desktop Linux Engine 命名管道不存在。未执行 `docker compose build/up`，也未安装、登录或启动 Docker。可在已启动 Docker Desktop 的 Windows 机器复现：

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
docker compose config --quiet
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/run-docker-loop.ps1 -RepoRoot .
```

## 缺陷与有界复测

### D01：API 诊断规则被渲染为 `unclassified`

- 严重度：P1 / 离线阶段验收阻断。
- 输入：上述浏览器任务的后端样本返回 `retrieval.missing_evidence`、`citation.missing`、`rerank.no_gain_or_regression` 三个 `rule_id`。
- 实际：诊断页主/次标签均为 `unclassified`；报告失败分布也会丢弃这类条目。移动端及重启后截图可复现。
- 原因：`frontend/src/api/client.ts:483` 与 `:572` 只读取 `category/label/rule/code`，没有读取冻结契约字段 `rule_id`。`frontend/src/pages/DiagnosisPage.tsx:175` 又用重复的 `item.label` 作为 React key，标签相同会产生重复 key 告警。
- 有界修复：在两个 mapper 中优先兼容 `rule_id`，为次级诊断使用稳定且唯一的 key，并增加 API snake_case fixture 的 Vitest 回归；不需要改后端契约或重写页面架构。
- 复测门禁：41 项前端测试与 build 通过；重新跑浏览器三阶段；证据中的 `diagnosis_labels` 不得包含 `unclassified`，创建/重启阶段不得出现 React duplicate-key 错误；其余 A01–A10 不回退。

## 接口、配置与迁移边界

- 前端 API client 已对齐 `/api/v1/datasets`、`/evaluation-jobs`、报告、样本/复核和 `/model-execution/status` 资源路由；页面 URL 中的 `projectId` 只是工作台上下文。
- `VITE_API_MODE=api` 只代表前端读取项目后端，不代表模型连接。Vite 使用 `VITE_API_PROXY_TARGET` 做本地同源代理；生产 Compose 由 Nginx 代理 `/api/` 到 backend。
- 后端默认 `mock`，外部调用总开关默认 `false`。选择 `openai_compatible` 也只有在显式启用并完整配置后才允许传输；前端不保存任何 provider Key。
- `ragops init-db` 和自动初始化执行 `0001_mvp_baseline -> 0002_model_execution_contract`。无迁移元数据的完整旧库先校验 1.0 必需结构再盖章升级；重复执行是 no-op；部分/未知 schema 直接失败，不能删库重建代替迁移。

## 能力分列

| 代码已实现 | 离线测试通过 | 真实连接已验证 |
| --- | --- | --- |
| provider-neutral 请求/响应/错误契约；mock 与 OpenAI-compatible 适配器；安全配置门；2.0 数据/运行/报告；幂等迁移；前端 API 模式与三轴状态 | 后端与评测自动化、MockTransport 错误矩阵、凭据隔离、本地 HTTP/SQLite 重启、绝大部分浏览器主流程、桌面/移动布局、断连 no-fallback | **未执行，按范围禁止**；没有真实 Key、账号、订阅、模型、RAG 检索或真实数据证据 |

由于 D01，不能将“前端诊断语义正确”列入离线通过，也不能宣称本阶段已经完成。模拟执行成功只证明执行链路可用，不代表回答质量通过；本次质量状态是 `not_evaluated`，分数与结论是未知。

## 后续真实接入所需输入

- 用户明确选择的提供方、模型、OpenAI-compatible Base URL、后端鉴权方式，以及受控 secret 注入方案。
- 单次/总超时、最大尝试、429/5xx 退避、并发、取消、预算和审计要求。
- 经授权且脱敏的数据来源、版本、许可、保留期限、gold/上下文/引用标签质量与污染检查。
- 在隔离环境进行一次明确授权的连接验证，再单独评估真实回答质量、延迟、用量与成本；离线 MockTransport 成功不能替代。

Codex 只保留未来扩展评估项，不在本阶段做账号接入。官方文档将本地 Codex 的 ChatGPT 登录与 API Key 登录列为不同方式；API Key 按标准 API 费率计费，不能把 ChatGPT Plus/订阅直接当作通用 API 额度。后续还需单独验证入口适用性、账号授权、功能/使用限制、结构化输出、取消、超时、并发与 Token 可用性：

- [Codex authentication](https://developers.openai.com/codex/auth)
- [Codex pricing](https://developers.openai.com/codex/pricing)

## 风险清单

| 风险 | 当前影响 | 处理建议 |
| --- | --- | --- |
| D01 诊断字段映射缺失 | 用户无法识别实际故障规则，报告失败分布也可能缺项 | 按有界修复完成并重跑 A09/B04/B06/B08 |
| Docker Engine 未运行 | 镜像构建、容器健康与数据卷重启未在本机验证 | 在已启动 Engine 的 Windows/CI 中跑 `run-docker-loop.ps1`，不复用本地 SQLite 结论 |
| 真实 provider 未验证 | 无法声明真实鉴权、网络、限流、成本或输出质量 | 用户授权配置后单独建受控验收，不修改离线结论 |
| SQLite + 进程内任务 | 进程崩溃恢复、并发与生产耐久性未覆盖 | 上生产前引入队列、外部数据库、备份恢复与并发/故障演练 |
