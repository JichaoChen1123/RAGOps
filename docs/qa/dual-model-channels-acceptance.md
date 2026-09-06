# WOR-73 双通道离线安全与端到端验收

验收日期：2026-09-06。受测产品实现 SHA：`89819e248aa5dfb1869aee3eed553207241eee84`；整合 QA 测试后的复验 SHA：`eb9f5f8e5864c9edaab8059c0538689ebaceda80`；来源分支：`feature/dual-model-channels`；目标分支：`agent/ragops/bd1953fd5894`。

结论：**离线验收通过，提交用户评审**。公共契约、后端适配器、Windows 主机桥接、前端状态/报告、Docker Compose 与 mock 闭环均有独立离线证据。真实账号、真实 Key、真实模型和真实费用验证未执行，不能由本报告推断为可用。

独立 QA 最初基于旧产品提交 `6f830887cad460207adc4e3463328aa337a08f85` 复验，145 项断言全部通过，但总分支覆盖率仅 `83.51%`，低于仓库既有 `85%` 门槛。负责人随后在最新产品提交补入真实子进程级 fake Codex App Server 测试；QA 又补充了外部总闸、参数拒绝、无跨通道回退、未知遥测、协议错误闭集、线程隔离响应和桥接 CLI 安全测试。两组测试整合后，最终 167 项通过，覆盖率 `87.79%`，没有为通过门禁而降低阈值。

## 范围与环境

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | Windows / PowerShell 5.1 |
| Python / uv | Python 3.11.15 / uv 0.12.1 |
| Node.js / npm | Node.js v24.18.0 / npm 11.16.0 |
| Docker | Engine 29.7.2 / Compose v5.4.0 |
| 后端模式 | `mock` |
| 外部调用 | `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` |
| 前端模式 | Docker 构建使用 `VITE_API_MODE=api` |
| 测试数据 | 1 条合成支持政策样本；TestClient/内存传输错误矩阵；不含真实业务数据 |
| 明确排除 | Codex 登录、OpenAI-compatible 真实 Key、真实生成、真实额度/费用和模型质量 |

## 验收矩阵

| ID | 输入与操作 | 期望结果 | 独立结果与证据 | 判定 |
| --- | --- | --- | --- | --- |
| D01 | 分别向 OpenAI-compatible 与 Codex 模拟传输发送固定请求 | 两通道只映射允许字段；响应字段保留原语义 | `test_openai_compatible_maps_whitelisted_request_and_response`、`test_codex_adapter_maps_only_allowed_fields_and_optional_response_values` 通过 | 通过 |
| D02 | 未登录、错误登录方式、登录失效、额度不足、限流、超时、取消、连接错误及非法响应 | 返回稳定安全错误码；不泄漏原始错误；认证错误不重试 | Codex 11 类错误参数化、OpenAI 401/403/429/5xx/超时/取消/非法响应及新增协议闭集测试通过 | 通过 |
| D03 | 外部调用关闭，对两个 provider 发起显式验证并注入“调用即失败”的工厂 | 在工厂/网络前返回 403，调用计数为 0 | `test_external_gate_blocks_provider_checks_before_factory` 两通道通过；Docker 状态接口也返回 `external_calls_enabled=false` | 通过 |
| D04 | 在参考答案、gold 标签、历史输出、metadata 中放唯一哨兵 | 模型请求只含 Prompt、问题和本题上下文 | OpenAI executor 哨兵测试、Codex 固定桥接 payload 与 App Server turn 序列化断言通过 | 通过 |
| D05 | 连续两次 Codex 模拟生成 | 每条样本创建独立 ephemeral 线程和临时空目录；结束后目录删除 | 线程 ID、请求 ID、cwd 均不同；`approvalPolicy=never`、只读、无网络/工具/MCP/指令源断言通过 | 通过 |
| D06 | provider 返回 `actual_model/usage/request_id/finish_reason=null` | 报告保持 `null/未知`，成本不得推断 | `test_unknown_provider_telemetry_stays_unknown_in_report` 与前端报告测试通过；成本仍为 `null` | 通过 |
| D07 | OpenAI-compatible 返回认证失败；记录工厂创建的 adapter ID | 只失败当前通道，不切换 Codex 或 mock，不以参考答案补位 | 工厂记录仅两次 `openai_compatible`（创建校验与执行），传输 1 次，回答为 `null`，错误安全持久化 | 通过 |
| D08 | Codex 分别提交非默认 temperature、top_p、max tokens、stop、seed | 请求持久化前明确 422 拒绝 | 5 个参数场景均返回 `VALIDATION_ERROR`，消息指出不支持字段，任务数保持 0 | 通过 |
| D09 | 两通道成功/失败/未知遥测与 mock 全流程 | 执行、质量和真实验证状态独立；失败报告仍可查询 | 后端任务/报告、前端三轴和样本运行信息测试通过；成功执行不产生质量 100 分 | 通过 |
| D10 | 报告含可评、不可评和失败样本 | `evaluated_count/excluded_count` 与实际样本数一致，不补零 | 聚合测试验证 2/0、0/2 和 0/6；前端显示 `1 已评 / 2 排除` | 通过 |
| D11 | Windows 桥接缺 token、非 loopback 未授权、旧 Codex 版本、任意 `cwd/command` 字段 | 启动或请求应在安全边界失败；健康检查不触发 Codex | CLI 与桥接 API 定向测试通过；API 无 OpenAPI/docs，模型端点需要至少 32 字符 Bearer token | 通过 |
| D12 | Docker 构建并以隔离项目名启动 backend/frontend；API 创建、发布、执行 1 条 mock 样本 | 双服务健康、外部关闭、mock 成功、未知 usage/成本不伪造 | 两服务 healthy；任务 `01a074ee-72d2-70bd-8773-1112662e139a` 为 `completed/succeeded`，1 成功/0 失败，`is_mock=true`，usage/cost 为 `null` | 通过 |
| D13 | `docker compose restart` 后读取同一任务；随后 `down`（不带 `--volumes`） | 数据持久化；QA 容器清理；命名卷不删除 | 重启后同一任务仍为 `completed/succeeded`；容器数 0；卷 `ragops-wor73-qa_ragops-data` 保留 | 通过 |

## Docker 与主机桥接安全复核

- Compose 默认执行器为 `mock`、外部调用为 `false`；真实通道只有同时显式配置并开启总闸才可运行。
- 前端容器无挂载；后端只挂载命名卷到 `/data`，以非 root 用户 `ragops` 运行。未把 `.env`、仓库目录、Codex 登录目录或 Windows 用户目录挂入容器。
- 主机桥接默认只监听 `127.0.0.1`；Docker 模式必须显式 `-Docker/--allow-non-loopback`，所有状态/生成端点仍要求 Bearer token。接口契约拒绝 `cwd`、命令、工具定义等额外字段。
- Codex 子进程移除 `RAGOPS_*` 和已知模型服务 Key，关闭网络、shell、MCP、插件、浏览器、计算机控制、多智能体与记忆等能力；每样本使用新的空临时目录。
- `docker compose down` 未使用 `--volumes`。本轮生成的 QA 数据卷按验收要求保留；需要清理时应由用户明确决定。

## 实际门禁记录

```powershell
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term --cov-fail-under=85
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
docker compose config --quiet
```

最终结果：Ruff 通过；最新整合分支后端/评测 `167 passed`，分支覆盖率 `87.79%`；前端 7 个文件、`56 passed`；typecheck 和 production build 通过；Compose 配置通过。Docker 镜像构建、双服务健康、1 条 mock API 闭环与容器重启持久化通过。

本轮仅有 3 条非阻断弃用告警：Starlette `TestClient` 的 httpx 兼容层 1 条，以及 `HTTP_422_UNPROCESSABLE_ENTITY` 常量 2 条。它们不改变当前行为，但升级 FastAPI/Starlette/httpx 前应消除。

## CI 门禁建议

- 保持当前 85% branch coverage 硬门槛；本次新增测试已纳入现有 backend job，无需单独命令。
- 当前 Docker CI 仅校验配置和构建镜像。建议后续增加 Linux runner 的 `mock + external=false` 健康检查和 1 条 API 冒烟；不得注入真实账号或 provider Key。
- 将真实连接验证放入手工、显式授权且有预算上限的独立工作流，禁止成为普通 PR 的随机网络门禁。
- 固定断言“不支持参数在持久化前拒绝”“外部关闭时 provider 工厂零调用”“任一 provider 失败不跨通道回退”，防止后续重构削弱安全边界。

## 样例数据建议

真实连接阶段仍应按 1 条到 10 条逐级放量：先用 1 条脱敏、答案短且证据唯一的样本验证认证和字段映射，再加入 9 条覆盖无答案、多证据、上下文不足、未知 usage、限流/超时恢复的样本。参考答案、gold 标签和历史输出只能用于调用后的评测，必须继续用哨兵测试证明它们不进入生成请求。

## 状态分列

| 代码已实现 | 离线测试通过 | 真实连接已验证 |
| --- | --- | --- |
| 三执行通道契约、OpenAI-compatible/Codex 适配器、主机桥接、错误模型、前端三轴与报告、Docker 配置 | **是**：167 项后端/评测、56 项前端、覆盖率/构建、Docker mock 闭环与重启持久化均通过 | **未执行**：无账号登录、无真实 Key、无真实模型调用、无额度/费用和真实质量结论 |

## 剩余风险

| 风险 | 当前影响 | 建议 |
| --- | --- | --- |
| 未做真实 Codex/App Server 协议握手 | 不能证明安装版本、账号类型、可用模型与额度在用户机器上真实可用 | 用户授权后先只做状态检查，再明确确认一次最小生成 |
| 未做真实 OpenAI-compatible 方言验证 | 不保证所有兼容服务的字段、错误体和 usage 形态一致 | 为选定服务商保存脱敏契约 fixture，再做 1/10 条受控验证 |
| Windows Docker 桥接需监听 `0.0.0.0` | 同机局域面暴露面大于 loopback | 保持随机 token、Windows Firewall、禁止路由器映射；更高隔离要求使用专用用户/VM |
| 协议实现分支覆盖仍明显低于核心业务模块 | 未见路径可能在 Codex 升级后失效 | 后续优先补 JSON-RPC EOF/超时/服务端反向请求和并发锁测试，而非降低全局阈值 |
| FastAPI/Starlette 弃用告警 | 依赖升级后可能转为失败 | 独立维护任务更新常量并迁移 TestClient/httpx2 |

本验收未发现需要修改生产代码的阻断缺陷；发现并修复的是阶段 1 未满足既有 CI 覆盖率门槛的问题。离线通过不等于真实连接或真实回答质量通过。
