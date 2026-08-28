# WOR-55 UI 与 README 二轮验收记录

## 验收结论

- 基线：`6896152e35d4c9baded9a58626b131fd5a8f75c4`（`main`）。
- 环境：Windows、Node.js `v24.18.0`、npm `11.16.0`、Python `3.11.15`，默认 `VITE_API_MODE=mock`，未使用 Docker。
- 结论：**有条件通过**。前端 typecheck、36 个 Vitest 用例、production build、仓库链接/结构化文件校验、WOR-49 交互契约和无 Docker dev server smoke 均通过；README 的定位、技术栈、完成度、验收命令、简历技术点和已知边界完整。
- 未满足项：本次运行没有可用的应用内浏览器实例，未执行真实浏览器截图、hover 视觉比对和端到端点击。因此不能把“视觉一致性/真实浏览器 E2E”写成已通过；合并前至少应由人工浏览器复核本页清单，或接受现有 Testing Library 证据作为本轮替代证据。

Mock 通过只证明仓库 fixture、前端状态与交互契约可复现，不代表真实 LLM、RAG provider、向量检索或生产持久化已经接入。

## 测试范围与矩阵

| ID | 输入与操作步骤 | 期望结果 | 实际结果 |
| --- | --- | --- | --- |
| W55-UI-001 | 在 mock 正常场景加载 `/projects/demo/overview`；检查工作台标题、当前运行上下文和技术链路。 | 页面体现 RAG 评测平台而非通用网站；展示 Dataset、Evaluation Job、Metrics、Failure Diagnosis、Report、Review。 | 自动化通过：`workspace-capabilities.test.tsx` 校验完整链路；源码包含版本、指标、诊断和门禁上下文。真实视觉未执行。 |
| W55-UI-002 | 检查侧边栏当前路由、可用入口、版本对比、只读模型/Prompt 和项目设置。 | active、available、coming soon、readonly、disabled 语义可区分；disabled 不可点击且说明原因。 | 自动化通过 active/NEXT/disabled/只读弹窗；CSS 静态契约覆盖 hover、active、coming-soon、disabled。hover 视觉未执行。 |
| W55-UI-003 | 直达概览、数据集、评测任务、报告、诊断和未知路由；切换正常、加载、空、失败、部分数据。 | 核心路由不崩溃；空态/错误/部分数据有明确提示，API 失败不静默回退 mock。 | `route-smoke` 与 `app-routes` 通过；错误重试、空态和未确定门禁有断言。 |
| W55-UI-004 | 以 fixture 执行导入/创建/搜索/筛选/归档、创建评测、查看报告、导出、引用联动和复核。 | 每个操作产生路由、状态、文件或可访问反馈；Mock 写入明确标识且不伪装持久化。 | `interactions.test.tsx` 全部通过；mock client 隔离写入通过。 |
| W55-TECH-001 | 检查概览技术上下文和模型/Prompt 只读快照。 | 展示模型 `qwen3-32b@2026-08`、Prompt `support-rag@v12`、Dataset v3.4、指标、诊断规则、mock/API 与工程门禁。 | 自动化通过，WOR-55 静态契约新增覆盖。 |
| W55-README-001 | 阅读项目定位、技术栈与功能完成度表。 | 已完成/下一阶段边界明确，不能把确定性执行器写成生产 RAG。 | 通过；真实 provider、向量数据库与生产级能力均明确标为下一阶段。 |
| W55-README-002 | 按 README 执行 `npm --prefix frontend ci`、mock dev 启动、typecheck、test、build；检查本地 Markdown 链接。 | 不依赖 Docker 即可返回前端页面；命令可执行；本地链接无断链。 | 通过：dev server 对概览 URL 返回 HTTP 200 且含 React root；其他命令见下节；20 个 Markdown 文件链接校验通过。 |
| W55-README-003 | 检查 README 简历技术点和风险表述。 | 技术点与实现一致；明确真实 LLM/RAG provider、向量库、真实浏览器 E2E 未完成。 | 通过；未发现把未实现能力写成已完成的表述。 |
| W55-CI-001 | 检查 `.github/workflows/ci.yml` 并执行仓库契约。 | 前端 typecheck/test/build、后端测试与覆盖率、文档/fixture、Docker build 形成分层门禁。 | 配置通过静态校验；本轮只执行 issue 范围内的前端与仓库契约，未执行 Docker/真实 provider。 |

## 执行结果

| 命令 | 结果 |
| --- | --- |
| `npm --prefix frontend ci --cache frontend/.npm-cache --prefer-offline --no-audit --no-fund` | 通过，安装 121 个锁定依赖。 |
| `npm --prefix frontend run typecheck` | 通过。 |
| `npm --prefix frontend test -- --reporter=verbose` | 通过，5 个测试文件、36 个用例。 |
| `npm --prefix frontend run build` | 通过，1831 个模块；JS 323.76 kB（gzip 100.01 kB），CSS 43.71 kB（gzip 9.75 kB）。 |
| `python scripts/validate_repository.py` | 通过，20 Markdown、6 JSON、3 JSONL、2 YAML；fixture 计数 6/9/8。 |
| `./tests/fixtures/validate-fixtures.ps1` | 通过，6 个有效样本、9 个无效用例、8 个指标用例。 |
| `./tests/acceptance/validate-wor-49.ps1 -RepoRoot .` | 通过，15 个交互同时覆盖 mock/API 期望与写操作。 |
| `./tests/acceptance/validate-wor-55.ps1 -RepoRoot .` | 通过，README、技术链路、导航状态、前端脚本和 CI 接线均存在。 |
| 短暂启动 `npm --prefix frontend run dev -- --host 127.0.0.1 --port 4173` 后请求概览 URL | 通过，HTTP 200 且返回 React root；检查后已停止服务。 |

受限 Windows 进程沙箱内首次运行 Vitest/Vite 时出现 `spawn EPERM`；在允许 Vite 创建子进程的同一环境中重跑即通过。这是运行器权限差异，不是测试断言或构建错误。

## 验收标准

- 自动化合并门禁：typecheck、Vitest、build 和仓库契约必须全部成功；任何失败均阻断合并。
- 产品表达门禁：概览必须保留 Dataset → Evaluation → Metrics → Diagnosis → Report → Review 链路，以及模型/Prompt/数据集版本、指标、诊断规则、运行模式和质量门禁。
- 状态门禁：active、hover、coming soon、readonly、disabled 必须有不同的交互/视觉反馈；disabled 需提供原因，coming soon 不得伪装为已实现。
- README 门禁：项目定位、技术栈、完成/未完成、无 Docker 验收、质量命令、简历技术点和真实能力边界不得缺失；本地链接必须存在。
- 视觉门禁：在真实 Chromium 中以 1440×900 和 390×844 至少复核概览、数据集、任务、报告和诊断；核对侧边栏遮挡、横向溢出、hover/disabled、弹窗和长文本。该门禁本轮未执行。

## 样例数据建议

- 主链路继续固定使用 `examples/eval-samples/valid-samples.jsonl` 的 6 条脱敏样本，覆盖正确回答、检索缺失、上下文污染、引用缺失、重排边界和不可回答。
- 参数/导入异常使用 `invalid-samples.jsonl` 的 9 条 oracle；必须断言字段、错误类型、稳定错误码与原子回滚，不能只断言 HTTP 422。
- 指标计算使用 `metric-cases.json` 的 8 组确定性 oracle；保留分子、分母、rank 与 excluded count 证据。
- 浏览器报告/诊断固定使用 `eval-20260826` 与 `sample-042`，覆盖待复核筛选、引用 `[2]`、证据定位和 confirmed/dismissed 状态。
- 接入真实 provider 后另建不参与 Prompt 调参的冻结金标集，记录 provider/model/Prompt/index/judge 版本和重复测量方差。

## CI 门禁建议

1. 保持现有前端 typecheck → Vitest → build，以及后端 Ruff/Pytest/branch coverage ≥ 85%、仓库契约和 Docker build 的依赖顺序。
2. 在 repository-contracts job 中执行 `tests/acceptance/validate-wor-55.ps1`，防止 README 边界、RAGOps 技术链路和导航状态标记被回退。
3. 新增 Playwright Chromium 的 mock E2E，覆盖五个核心页面、五种数据场景、侧边栏状态与 1440×900/390×844 截图差异；失败上传脱敏截图和 trace。
4. API E2E 单独启动真实后端，覆盖写入 → 状态刷新 → 报告 → 复核 → 导出 → 刷新持久化，并明确验证 API 失败不回退 mock。
5. 真实 provider 质量不进入普通 PR 的确定性阻断门禁；应在固定版本、固定金标集的定时任务中统计漂移、429/超时、成本和 judge 方差。

## 剩余风险

| 风险 | 当前影响 | 建议门禁/缓解 |
| --- | --- | --- |
| 真实 LLM/RAG provider 未接入 | 无法证明模型质量、限流、超时、成本、索引漂移和 judge 稳定性。 | PR 使用确定性 fake；定时任务固定版本与金标集做漂移/故障测试。 |
| 真实向量库、Embedding、Rerank 未接入 | 当前检索指标只证明 fixture/oracle 计算，不证明生产召回与索引生命周期。 | 接入后增加索引构建、版本冻结、召回基线、删除/重建和权限隔离测试。 |
| 真实浏览器视觉/E2E 未执行 | CSS 布局、hover、窄屏、弹窗遮挡、下载和浏览器兼容问题仍可能漏检。 | 合并前人工复核或补跑 Playwright；未执行前不得宣称视觉验收通过。 |
| API 模式缺少浏览器闭环 | CORS、代理、错误映射和刷新持久化可能只在集成环境暴露。 | 增加同源代理或 CORS 配置，并执行 API 模式 E2E。 |
| Mock 写入只在组件内存 | 跨路由或刷新后状态重置，不能作为持久化证据。 | 保留 MOCK 标识和重置说明；持久化验收只看 API 模式。 |

## 本地复现

```powershell
npm --prefix frontend ci
$env:VITE_API_MODE = 'mock'
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
./tests/acceptance/validate-wor-49.ps1 -RepoRoot .
./tests/acceptance/validate-wor-55.ps1 -RepoRoot .
python scripts/validate_repository.py
npm --prefix frontend run dev
```

打开 README 列出的五个页面，按“测试范围与矩阵”的 W55-UI-001 至 W55-UI-004 做真实浏览器补验；只有观察到期望结果后，才能将视觉门禁改为通过。
