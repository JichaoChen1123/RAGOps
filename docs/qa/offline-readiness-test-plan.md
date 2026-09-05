# 离线接入契约测试计划

适用契约：`docs/architecture/model-execution-contract.md` 2.0 冻结稿。测试准备基线为 `6518416c500fefd4330197d514e982146e1d4fb0`，任务为 WOR-65。

本计划交付阶段 2 的自动化和人工样本，不代表阶段 3 集成验收已经完成。测试只使用人工构造数据、后端 `mock` 适配器和进程内 `httpx.MockTransport`；禁止真实模型请求、登录、凭据探测、真实数据下载和 LangGraph。

## 测试范围

- 提供方无关请求/响应字段和 OpenAI 兼容映射。
- 标签、历史输出、metadata、内部 ID 与模型输入隔离。
- 每次运行回答、评测输入、运行快照、报告和 SQLite 持久化。
- 鉴权、限流、超时、5xx、传输和响应格式错误的重试边界与脱敏。
- 未配置、外部调用禁用、不可用执行方式和不探测状态查询。
- 任务生命周期、执行结果、质量状态、分数和真实连接状态的独立语义。
- `provided`、`retrieved`、`legacy_unknown` 上下文与引用支持判断边界。
- 1.0/2.0 导入、原子校验、重复 ID 和旧 SQLite 幂等升级。
- 为阶段 3 准备本地 API、重启、浏览器 API 模式和 Docker 闭环。

不在本阶段执行：真实提供方连接、真实问答质量、真实数据质量、生产负载、账号权限或额度验证。

## 测试资产

| 资产 | 内容 |
| --- | --- |
| `tests/backend/test_offline_contract_acceptance.py` | A01–A08 FastAPI/SQLite/内存 HTTP 行为测试 |
| `examples/offline-readiness/valid-v2.jsonl` | 3 条 2.0 合法人工样本，含唯一泄漏哨兵 |
| `examples/offline-readiness/legacy-v1.jsonl` | 1 条 1.0 兼容样本 |
| `examples/offline-readiness/invalid-v2.json` | 9 个单行异常、批内重复和库内重复 oracle |
| `examples/offline-readiness/provider-responses.json` | 成功、可空字段、401/403、429、5xx 和非法响应 |
| `examples/offline-readiness/legacy-v1.sql` | 含样本、任务、报告和 confirmed 复核的旧库脚本 |
| `tests/acceptance/offline-readiness/validate-assets.ps1` | 跨平台样本结构与覆盖面自检 |
| `tests/acceptance/offline-readiness/invoke-api-loop.ps1` | 对已启动后端执行完整 API 闭环 |
| `tests/acceptance/offline-readiness/run-local-restart.ps1` | 独立 SQLite、本地后端两次启动和持久化复查 |
| `tests/acceptance/offline-readiness/run-docker-loop.ps1` | 隔离 Compose 项目、重启和完整 API 复查 |
| `tests/acceptance/offline-readiness/browser-api-loop.html` | 真实浏览器 fetch/CORS 辅助闭环 |
| `tests/acceptance/offline-readiness/browser-checklist.md` | 产品前端桌面、移动、刷新、断连和重启检查 |

## 测试矩阵

| ID | 输入 | 操作 | 期望 | 自动化/阶段 |
| --- | --- | --- | --- | --- |
| A01 | 两段乱序给定上下文；完整生成参数；一次完整和一次缺可选字段的成功响应 | 创建 `openai_compatible` 任务，由内存 MockTransport 捕获 `/chat/completions` | 消息顺序和模型/温度/top-p/max tokens/stop/seed 正确；实际模型、finish reason、耗时、Token 和请求 ID 映射；缺失值为 null；模拟传输 `is_mock=true` | Pytest，阶段 2 |
| A02 | reference、gold doc/evidence、诊断、context 标签、历史回答/引用、metadata、内部 ID 均放唯一 `SENTINEL_` 值 | 导入样本并运行 OpenAI 兼容任务，检查捕获的原始请求字节 | 只出现问题、按位置排序的上下文文本、Prompt 和生成参数；所有哨兵及禁用字段名均不出现 | Pytest，阶段 2 |
| A03 | 同一已发布数据集；脚本回答 Alpha/Beta；exact-match 指标 | 连续创建两个任务，再关闭和重开 SQLite | run ID 和回答独立；Alpha 指标 true、Beta false，证明评测读取本次回答；顶层兼容 answer 等于 run.answer；标签、历史值、hash 不变；重开后报告可读 | Pytest，阶段 2 |
| A04 | 401、403、429（立即与超长 Retry-After）、ReadTimeout、500、ConnectError、非法 JSON、空正文、缺 answer、answer 类型错；错误正文含秘密哨兵 | 每种错误创建独立任务；重试基数和最大延时设 0，单次 100 ms、总计 600 ms | 鉴权/格式错误 1 次；可重试错误最多 3 次；999 秒 Retry-After 截断 5000 ms 且因总截止时间只调用 1 次；终态失败也有 200 报告；总耗时不超过 700 ms；API/报告不含正文、Key 或 URL | Pytest，阶段 2 |
| A05 | 无配置；完整假配置但外部开关关闭；`context_policy=retrieval` | 启动、调用 live/ready/status、创建真实适配器任务、请求未实现方式 | 无配置仍启动；status/health transport=0；禁用返回 403 且 attempts=0；retrieval 返回 409；均不创建任务、不回退 mock | Pytest，阶段 2 |
| A06 | `frontend=api` 的阶段 3环境；后端 mock；真实提供方配置完整但未验证；无质量门 | 运行 mock 任务并读取任务、样本和报告 | 三层状态可并存；执行成功率 1.0 仅属 execution；质量 `not_evaluated/unknown/null`；模拟结果不产生 `verified` | Pytest + 前端检查，阶段 2/3 |
| A07 | provided 样本带可解析引用但无 supports_claim；1.0 legacy 样本；Recall@1、resolution/support 指标 | 运行 mock 任务并检查逐样本指标 | provided Recall 为 `not_evaluated/null`；legacy Recall 为 `unknown/null`；resolution 可为 1.0；support 为 `not_evaluated/null`；未实现语义指标无分数 | Pytest，阶段 2 |
| A08 | 2.0/1.0 合法样本；null/空白/未知版本/混用字段/上下文关系/重复 rank；批内和库内重复；旧 SQLite | 创建与导入，检查错误路径和样本数；旧库启动两次并查询 | 兼容归一化语义正确；错误含 row/sample_id/点路径并原子回滚；批内 422、库内 409；两次升级第二次空操作，旧样本、hash、任务、报告和复核保留 | Pytest + 资产自检，阶段 2 |
| A09 | 集成后的本地后端、前端 API 模式、独立 SQLite、3 条人工样本 | API 脚本创建/导入/发布/运行/报告/导出；桌面和移动浏览器执行检查表；刷新并重启后复查 | API 和 UI 使用同一持久化结果；状态语义诚实；无空白/遮挡；断连明确报错；截图不能代替 API 断言 | 脚本 + 人工浏览器，阶段 3 |
| A10 | 完整阶段集成 SHA 和默认禁网 Compose | 隔离 Compose 项目 build/up；运行 API 闭环；restart backend；复查；执行既有后端/评测/前端门禁 | 不调用真实模型；重启后数据可读；既有有效回归不降低；Docker 不可用则记录实际错误和 PowerShell 复现命令，不能写通过 | 脚本 + CI，阶段 3 |

## 关键验收标准

1. 资产自检退出码为 0；JSON/JSONL/SQL 均可解析且覆盖数固定。
2. Pytest 文件能够收集并执行，不使用 skip/xfail，不通过读取生产源码字符串替代行为断言。
3. A01/A02 的 provider 地址固定为 RFC 保留域 `provider.invalid`，`httpx.MockTransport` 只截获该主机；DNS 守卫阻止测试逃逸到真实网络。
4. A03 必须同时证明不同 run、不同回答、依赖回答的不同指标结果、DB 重开可读和原样本未修改。
5. A04 逐场景断言 transport 次数、持久化 attempt 数、总时间上限、终态报告和秘密不存在；只断言安全固定错误，不保存响应正文。
6. A05 的禁用/配置错误发生在 transport 前，transport 计数严格为 0；status 和 readiness 同样不得探测。
7. A06 不允许从 `succeeded`、配置齐全或模拟 HTTP 成功推出质量通过或真实连接已验证。
8. A07 的未知和未评估必须以 `value=null` 表达，不能用 0 代替。
9. A08 任一导入错误接受 0 行；旧库不得删除、重建或覆盖；迁移重复执行结果一致。
10. A09/A10 必须有 API 创建到导出的机器断言；浏览器状态和截图仅为补充证据。

## 执行命令

阶段 2，任何操作系统：

```powershell
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py
pwsh -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
uv run --project backend pytest -c backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py -q
uv run --project backend python scripts/validate_repository.py
```

阶段 3，无 Docker：

```powershell
pwsh -File tests/acceptance/offline-readiness/run-local-restart.ps1 -RepoRoot .
```

阶段 3，Docker 可用时：

```powershell
pwsh -File tests/acceptance/offline-readiness/run-docker-loop.ps1 -RepoRoot .
```

阶段 3，产品前端：

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
$env:VITE_API_MODE = 'api'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
uv run --project backend uvicorn app.main:app --app-dir backend
npm --prefix frontend run dev
```

随后执行 `tests/acceptance/offline-readiness/browser-checklist.md`；不要把服务留作阶段 2 交付结果。

## CI 门禁建议

- PR 必跑资产自检和 `test_offline_contract_acceptance.py`；阶段 2 后端集成完成前保留红灯，不删除断言或 skip。
- 后端全量维持 Ruff、Pytest、分支覆盖率 85% 和仓库验证；新增测试计入现有 `tests/backend` 收集范围。
- 前端维持 typecheck、Vitest 和 build；阶段 3 增加 API 模式浏览器 E2E 后才把浏览器闭环列为自动门禁。
- Compose 继续执行 config 和 build；有稳定运行器后增加 `run-docker-loop.ps1`，不要在普通单测内启动 Docker。
- 所有网络测试默认拒绝非 `provider.invalid` 主机；任何真实提供方测试必须另建显式授权、非默认门禁。

## 当前执行记录

当前记录对应契约基线、尚未集成阶段 2 后端/前端生产实现的测试准备分支。

| 命令 | 结果 | 解释 |
| --- | --- | --- |
| `powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .` | 通过，退出码 0 | 3 条 v2、1 条 v1、9 个异常 case、provider 响应和旧库 SQL 通过 |
| `uv run --project backend ruff check --config backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py` | 通过，退出码 0 | `All checks passed!` |
| `uv run --project backend pytest -c backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py -q --tb=no` | 32 failed，退出码 1 | 预期红灯：冻结基线仍只接受数据集 1.0，且缺少 2.0 status/schema/run/report/migration；无 skip/xfail，不记功能通过 |
| `uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation --ignore=tests/backend/test_offline_contract_acceptance.py -q --tb=no` | 50 passed，退出码 0 | 既有后端与评测回归未被测试资产破坏；另有 1 条 TestClient 弃用警告 |
| `uv run --project backend python scripts/validate_repository.py` | 通过，退出码 0 | 26 Markdown、8 JSON、5 JSONL、2 YAML；既有 fixture oracle 6/9/8 |
| PowerShell AST 解析与 `git diff --check` | 通过，退出码 0 | 4 个 PowerShell 脚本语法有效；无空白错误 |
| 本地重启/浏览器/Docker | 未执行 | 留待阶段 3 同一集成 SHA；阶段 2 不冒充验收 |
| 真实连接/真实问答 | 未执行，按范围禁止 | 无真实凭据和数据，不做探测 |

## 风险清单

| 风险 | 影响 | 门禁/缓解 |
| --- | --- | --- |
| 后端并行实现尚未进入测试分支 | Pytest 当前失败，无法声明离线功能通过 | 失败如实保留；负责人集成后由 WOR-66 在准确 SHA 重跑 |
| 测试 transport 被绕过 | 可能产生网络访问 | provider.invalid 专用拦截 + DNS 守卫 + transport 次数断言 |
| 重试测试依赖真实时间 | 测试变慢或抖动 | 退避固定为 0、总超时 600 ms，并断言实际次数和耗时 |
| 哨兵值被 Prompt 重写隐藏 | 简单字段检查漏检 | 检查最终 HTTP 原始字节，同时检查唯一值和禁用字段名 |
| 旧库 fixture 与 0001 基线漂移 | 迁移出现假失败或漏列 | SQL 固定为契约冻结的 main 表结构；结构不匹配必须停止，不自动重建 |
| 异步任务未在 TestClient 请求结束前终态 | 单测取到 queued | 后端测试保持确定性内联背景任务；阶段 3 脚本有 30 秒有界轮询 |
| 浏览器截图被当作 API 证据 | 静态页面掩盖后端失败 | PowerShell API 闭环为必要证据，截图仅补充布局 |
| Docker 环境不可用 | A10 无法实跑 | 记录实际命令/错误，保留 Windows PowerShell 复现步骤，不将未测写为通过 |
| 模拟成功被误认为真实连接 | 状态和产品说明失真 | 断言 `configured_unverified`、`last_verified_at=null`，真实验证本阶段禁止 |

## 阶段 3 结果模板

```text
集成 SHA：
代码已实现：是/否（差异或 PR）
离线测试通过：是/否（命令、通过/失败数）
本地 API + SQLite 重启：通过/失败/未执行
产品前端桌面/移动 API 模式：通过/失败/未执行
Docker：通过/失败/未执行（实际错误与复现命令）
真实连接已验证：未执行，按范围禁止
真实问答效果：未评测
遗留风险：
```
