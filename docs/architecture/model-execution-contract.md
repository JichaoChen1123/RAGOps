# 模型执行与离线兼容契约

状态：WOR-62 冻结稿。本文冻结阶段 2 后端、前端和 QA 共同依赖的字段与语义；业务实现与离线验收尚未完成。

契约版本：`2.0`。HTTP 路径仍使用 `/api/v1`，资源体通过 `schema_version` 演进。文中的“必须”“不得”和默认值均为规范要求。

## 1. 决策摘要

- 后端执行适配器只有 `mock` 与 `openai_compatible` 两个本阶段实现值。`codex` 是保留扩展点，不得在本阶段注册为可用适配器。
- 默认后端执行器为 `mock`，默认禁止所有模型外部网络调用。配置、启动、就绪检查和状态查询都不得连接提供方。
- 模型请求只允许问题、模型可见上下文、Prompt 和生成参数。参考答案、gold 标签、预存回答、样本 metadata 与内部 ID 不得进入请求或提供方 payload。
- 样本标签、历史预存回答、本次运行输出和评测结果分别存储。本次输出先持久化，再由评测器读取同一个输出；不得回退到参考答案。
- 任务生命周期、样本执行结果和质量评估是三个独立状态。执行成功不代表质量通过，也不产生 `0` 或 `100` 分。
- `provided` 或 `legacy_unknown` 上下文不算本次检索召回。引用能解析不代表语义支持；没有支持性判断时支持指标不出分。
- 新资源使用 `schema_version: "2.0"`。现有 `1.0` 输入与旧数据库保留并兼容投影，但未知来源和未知质量保持未知，不做反推。

## 2. 三层模式与安全边界

三个状态轴彼此独立，UI 必须同时展示，不能用其中一个推导另一个：

| 状态轴 | 枚举 | 默认值 | 含义 |
| --- | --- | --- | --- |
| 前端数据模式 | `mock`、`api` | `mock` | `api` 只表示前端连接 RAGOps 后端，不表示使用真实模型 |
| 后端执行适配器 | `mock`、`openai_compatible` | `mock` | 决定任务使用的模型适配器 |
| 提供方配置状态 | `not_configured`、`configured_unverified`、`verified` | `not_configured` | 只描述真实提供方配置及显式真实验证 |

以下边界无例外：

1. `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` 时，真实 transport 必须在 DNS、socket、重试和验证之前拒绝调用。
2. 凭据只存在于后端配置对象和请求鉴权头中，不进入 API、快照、日志、异常、报告、导出或 Git。
3. 适配器不得持久化原始提供方请求体或响应体。可持久化的只有本文白名单字段。
4. API 请求、环境变量或数据库字段都不能选择测试 transport。测试 transport 只能由测试代码直接注入工厂。
5. 不因检测到 Key、Base URL 或其他凭据自动选择真实适配器，也不得在真实适配器不可用时静默回退 `mock`。

## 3. 提供方无关模型契约

### 3.1 `ModelRequest`

`ModelRequest` 是进程内严格对象，拒绝额外字段。它只有以下四个顶层字段：

| 字段 | 类型 | 必填/默认 | 约束 |
| --- | --- | --- | --- |
| `question` | string | 必填 | 去除首尾空白后长度 `1..20000` |
| `context` | `ModelContext[]` | `[]` | 最多 100 项，按 `position` 升序且位置不重复 |
| `prompt` | string | 必填 | 去除首尾空白后长度 `1..50000` |
| `generation` | `GenerationConfig` | 必填 | 必须在创建任务时解析完整并写入快照 |

`ModelContext` 只有 `position: integer >= 1` 和 `text: string`。它故意不含 `doc_id`、`chunk_id`、标签、分数或 metadata；这些字段留在运行快照中供评测和溯源，不发送给模型。

`GenerationConfig`：

| 字段 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `model` | string | mock 为 `mock-ragops-v1`；真实适配器必须显式解析 | 非空，最长 200 |
| `temperature` | number | `0.0` | `0.0..2.0` |
| `top_p` | number | `1.0` | 大于 0 且不大于 1 |
| `max_output_tokens` | integer | `512` | `1..8192` |
| `stop` | string[] | `[]` | 最多 8 项，每项非空且最长 200 |
| `seed` | integer 或 null | `null` | 适配器不支持而值非 null 时明确失败 |

最小模型请求：

```json
{
  "question": "如何重置演示账户密码？",
  "context": [
    {
      "position": 1,
      "text": "演示账户可在设置页选择重置密码。"
    }
  ],
  "prompt": "仅依据给定上下文回答；证据不足时明确说明。",
  "generation": {
    "model": "mock-ragops-v1",
    "temperature": 0.0,
    "top_p": 1.0,
    "max_output_tokens": 512,
    "stop": [],
    "seed": null
  }
}
```

请求白名单以拒绝列表双重约束。下列值即使出现在样本中，也不得进入 `ModelRequest`、Prompt 拼接或提供方 payload：`reference_answer`、`gold_document_ids`、`gold_evidence_ids`、`relevance_grade`、`usefulness`、`supports_claim`、`expected_diagnoses`、`historical_output`、整份 `metadata`、数据集/样本/任务内部 ID。

### 3.2 `ModelResponse`

`ModelResponse` 的所有字段都必须存在；无法从本次调用直接确认的值为 `null`，不得复制请求值冒充提供方实际值。

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `answer` | string | 本次模型输出；允许空字符串但随后可被响应校验判为错误 |
| `actual_model` | string 或 null | 提供方响应明确返回的模型标识；未返回时为 null |
| `finish_reason` | enum 或 null | `stop`、`length`、`content_filter`、`tool_call`、`other`；未知为 null |
| `latency_ms` | integer | 从适配器开始调用到取得可解析响应的单调时钟耗时，非负 |
| `usage` | `TokenUsage` 或 null | 只有提供方返回可解析用量时才存在 |
| `provider_request_id` | string 或 null | 提供方返回的请求 ID；不得自行生成冒充 |
| `is_mock` | boolean | mock 适配器或注入测试 transport 必须为 true |

`TokenUsage` 包含 `input_tokens`、`output_tokens`、`total_tokens`，三项均为非负整数。只要无法可靠解析其中任一项，整个 `usage` 为 null；本阶段不估算 Token。模型响应不含成本，运行与报告中的 `cost` 固定为 null，直到有独立的版本化价格快照能力。

最小成功响应：

```json
{
  "answer": "[mock] 演示账户可在设置页选择重置密码。",
  "actual_model": "mock-ragops-v1",
  "finish_reason": "stop",
  "latency_ms": 0,
  "usage": null,
  "provider_request_id": null,
  "is_mock": true
}
```

### 3.3 `ModelError`

适配器失败统一抛出/返回 `ModelError`，不得把 SDK 异常、URL、鉴权头或响应正文直接透传。

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `code` | `ModelErrorCode` | 下表稳定错误码 |
| `message` | string | 固定、安全、用户可见的说明 |
| `retryable` | boolean | 对本次失败类型是否允许自动重试，不代表调用方必须重试 |
| `attempts` | integer | 实际发起 transport 的总次数；配置/禁用错误为 0 |
| `provider_request_id` | string 或 null | 仅当提供方安全返回时记录 |
| `retry_after_ms` | integer 或 null | 解析并截断后的建议等待时间；未提供为 null |

错误示例：

```json
{
  "code": "PROVIDER_TIMEOUT",
  "message": "Model provider did not respond before the configured deadline.",
  "retryable": true,
  "attempts": 3,
  "provider_request_id": null,
  "retry_after_ms": null
}
```

稳定错误码：

| 错误码 | 自动重试 | 说明 |
| --- | --- | --- |
| `EXECUTION_ADAPTER_NOT_FOUND` | 否 | 请求的适配器未注册，包括本阶段的 `codex` |
| `PROVIDER_NOT_CONFIGURED` | 否 | 选中适配器的必需服务器配置缺失 |
| `EXTERNAL_CALLS_DISABLED` | 否 | 真实 transport 被总开关禁止 |
| `PROVIDER_CAPABILITY_UNSUPPORTED` | 否 | 请求使用了适配器不支持的非默认参数或能力 |
| `PROVIDER_AUTHENTICATION_FAILED` | 否 | 上游 401/403 或等价鉴权失败 |
| `PROVIDER_RATE_LIMITED` | 是 | 上游 429 或等价限流 |
| `PROVIDER_TIMEOUT` | 是 | 单次或总截止时间到期 |
| `PROVIDER_TRANSPORT_ERROR` | 是 | DNS、连接、TLS 或连接重置等传输失败 |
| `PROVIDER_SERVER_ERROR` | 是 | 上游 5xx |
| `PROVIDER_RESPONSE_INVALID` | 否 | 空响应、非法 JSON、缺少回答或字段类型错误 |

## 4. 适配器、能力与工厂

公共接口不假设提供方具备 API Key、Base URL 或 HTTP：

```python
class ModelAdapter(Protocol):
    adapter_id: str
    capabilities: AdapterCapabilities

    def generate(self, request: ModelRequest) -> ModelResponse: ...


class ModelAdapterFactory(Protocol):
    def create(
        self,
        adapter_id: str,
        server_config: object,
        *,
        test_transport: ModelTransport | None = None,
    ) -> ModelAdapter: ...
```

`AdapterCapabilities` 的稳定字段为：

```json
{
  "external_network": false,
  "supports_seed": true,
  "supports_stop": true,
  "reports_usage": false,
  "reports_request_id": false
}
```

工厂规则：

1. `adapter_id` 必须显式，禁止按是否存在凭据猜测。
2. `mock` 配置不要求 Key 或 Base URL；其 `external_network=false`。
3. `openai_compatible` 使用专属 `OpenAICompatibleConfig`，只有该配置可以要求 Base URL，并按其 `auth_mode` 决定是否要求 Key。
4. 未注册值返回 `EXECUTION_ADAPTER_NOT_FOUND`，不得回退。
5. 适配器能力不支持请求中的非默认值时返回 `PROVIDER_CAPABILITY_UNSUPPORTED`，不得静默丢弃参数。

`ModelTransport` 只接收已经过网络总开关和脱敏边界检查的 HTTP 请求描述，并返回状态、白名单响应头和字节正文。生产工厂不得从环境变量、API 或持久化数据构造测试 transport。

## 5. 本阶段两个适配器

### 5.1 `mock`

- `adapter_id="mock"`，不创建 HTTP client，不读取真实提供方配置。
- 默认模型为 `mock-ragops-v1`，`actual_model` 同值，`is_mock=true`，`usage=null`，`provider_request_id=null`。
- 默认回答只读请求白名单：有上下文时取第一项 `text` 的前 500 个 Unicode 字符并添加 `[mock] `；无上下文时返回 `[mock] Insufficient context for: {question}`。
- 它不得读取参考答案、gold 标签、历史回答或样本 metadata。测试可注入显式脚本响应，但脚本 fixture 也不得来自这些标签字段。

### 5.2 `openai_compatible`

本阶段目标是完整映射 `/chat/completions` 请求与响应，但所有验收都使用内存测试 transport，不访问真实 URL。

专属配置：

| 字段 | 默认 | 必填规则 |
| --- | --- | --- |
| `base_url` | null | 必填，必须为 `http` 或 `https`；真实运行建议 `https` |
| `auth_mode` | `bearer` | `bearer` 或 `none` |
| `api_key` | null | `auth_mode=bearer` 时必填；永不序列化 |
| `default_model` | null | 必填；任务可显式覆盖 |

提供方 payload 的消息顺序固定：

1. `system` 消息内容为 `request.prompt`。
2. `user` 消息由 `Question:\n{question}\n\nContext:\n` 加按位置排序的 `[n]\n{text}` 块组成；无上下文时 Context 为 `(none)`。
3. 映射 `model`、`temperature`、`top_p`、`max_tokens`；`stop=[]` 与 `seed=null` 时省略对应字段。

只解析 `choices[0].message.content`、响应 `model`、`choices[0].finish_reason`、`usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens` 及 `x-request-id`。原始正文和其他字段用完即丢弃。回答字段缺失、非字符串或 JSON 非法均为 `PROVIDER_RESPONSE_INVALID`。

注入 `test_transport` 时：

- 工厂只能在测试组合根以显式参数注入，应用配置不能触达该参数。
- 不检查或使用真实 Base URL/Key，不打开 socket，响应的 `is_mock=true`。
- 一次模拟成功只证明映射正确，提供方状态仍为 `configured_unverified`，绝不能改成 `verified`。

## 6. 网络总开关、超时与重试

配置默认值和硬上限：

| 配置 | 默认 | 允许范围/语义 |
| --- | --- | --- |
| `RAGOPS_MODEL_EXECUTION_ADAPTER` | `mock` | `mock`、`openai_compatible` |
| `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED` | `false` | 唯一真实网络总开关 |
| `RAGOPS_MODEL_REQUEST_TIMEOUT_MS` | `10000` | `100..30000`，单次尝试上限 |
| `RAGOPS_MODEL_TOTAL_TIMEOUT_MS` | `25000` | `100..60000`，且不小于单次上限 |
| `RAGOPS_MODEL_MAX_ATTEMPTS` | `3` | `1..3`；包含第一次，不是“重试次数” |
| `RAGOPS_MODEL_RETRY_BASE_MS` | `250` | `0..2000` |
| `RAGOPS_MODEL_RETRY_MAX_DELAY_MS` | `2000` | `0..5000` |
| `RAGOPS_OPENAI_COMPAT_BASE_URL` | 空 | 只供专属适配器使用 |
| `RAGOPS_OPENAI_COMPAT_AUTH_MODE` | `bearer` | `bearer`、`none` |
| `RAGOPS_OPENAI_COMPAT_API_KEY` | 空 | 仅后端 secret |
| `RAGOPS_OPENAI_COMPAT_DEFAULT_MODEL` | 空 | 真实适配器默认模型 |

重试算法：

1. 在第一次 transport 调用前检查总开关；禁用时 `attempts=0`。
2. 单次超时为 `min(request_timeout_ms, total_deadline_remaining)`。
3. 仅重试 `RATE_LIMITED`、`TIMEOUT`、`TRANSPORT_ERROR` 和 `SERVER_ERROR`，最多总计 3 次。
4. 默认退避为 `min(250 * 2^(attempt-1), 2000)` 毫秒。429 的 `Retry-After` 可覆盖退避，但截断到 5000 毫秒。
5. 若等待会越过总截止时间则不再等待或发起调用，返回最后错误；总耗时不得超过总上限加 100 毫秒的调度容差。
6. 鉴权、配置、能力和响应格式错误从不自动重试。

## 7. 配置状态 API

`GET /api/v1/model-execution/status` 返回 `200` 且不得探测提供方：

```json
{
  "schema_version": "2.0",
  "backend_execution_adapter": "mock",
  "external_calls_enabled": false,
  "execution_available": true,
  "active_adapter": {
    "adapter_id": "mock",
    "is_mock": true,
    "capabilities": {
      "external_network": false,
      "supports_seed": true,
      "supports_stop": true,
      "reports_usage": false,
      "reports_request_id": false
    }
  },
  "providers": [
    {
      "provider_id": "openai_compatible",
      "configuration_status": "not_configured",
      "base_url_configured": false,
      "credential_configured": false,
      "default_model_configured": false,
      "last_verified_at": null,
      "verification_message": null
    }
  ]
}
```

三态语义：

- `not_configured`：专属配置按 `auth_mode` 不完整。只检查存在性与本地格式，不发网络请求。
- `configured_unverified`：本地配置完整，但从未对完全相同的配置执行显式真实验证，验证失败，或进程已重启。
- `verified`：操作员显式授权后，在当前进程中用真实 transport 对完全相同配置成功验证。模拟 transport 永远不能产生该状态。

本阶段不提供真实验证入口，因此离线验收中只会出现前两态。未来显式验证必须重新检查总开关；任何 Base URL、鉴权模式、凭据或默认模型变化以及进程重启都清除内存验证记录，回到 `configured_unverified`。状态响应只暴露“是否配置”，不得返回值、URL、Key 指纹或响应正文。

## 8. 任务创建、快照与状态

### 8.1 新任务请求

`POST /api/v1/evaluation-jobs` 的 2.0 请求：

```json
{
  "schema_version": "2.0",
  "dataset_id": "dataset-demo-v2",
  "name": "offline contract run",
  "execution": {
    "adapter_id": "mock",
    "prompt": {
      "version": "support-rag-v2",
      "text": "仅依据给定上下文回答；证据不足时明确说明。"
    },
    "generation": {
      "model": "mock-ragops-v1",
      "temperature": 0.0,
      "top_p": 1.0,
      "max_output_tokens": 512,
      "stop": [],
      "seed": null
    },
    "context_policy": "dataset_contexts"
  },
  "metrics": [],
  "quality_gate": null
}
```

字段规则：

- `schema_version`：新客户端必填 `2.0`。
- `name`：可空；null 时为 `{dataset_name} evaluation`。
- `execution.adapter_id`：默认 `mock`，但响应快照中必须显式。
- `execution.prompt.version` 与 `text`：2.0 必填且非空；Prompt 文本可持久化但不得含凭据。
- `context_policy`：`dataset_contexts`、`none`、`retrieval`。本阶段 `retrieval` 未实现，创建时返回 `409 EXECUTION_MODE_UNAVAILABLE`，不得当作给定上下文运行。
- `metrics`：默认 `[]`，元素仍为 `name`、`version`、`parameters`。
- `quality_gate`：默认 null；非空时为 `QualityGate`，是唯一能产生质量 passed/failed 的输入。

`QualityGate` 固定为 `version`、`rules` 和 `score_metric`。`rules` 含 1..50 项，每项为 `metric_name`、`operator`（`gte`、`gt`、`lte`、`lt`、`eq`）和有限数值 `threshold`；`score_metric` 为指标名或 null。任一规则所需指标不是 `status=ok` 时，质量为 `partial/unknown`，不能按 0 或通过处理；指标执行错误时为 `error/unknown`。只有全部规则都有可用值时为 `evaluated`，全部规则满足才 `passed`，否则 `failed`。`quality_score` 只有在 `score_metric` 指向值域 `0..1` 的数值型 `ok` 指标时才等于该值乘 100，否则为 null。

现有任务客户端若同时缺少 `schema_version` 和 `execution`，按 1.0 兼容请求处理：固定归一化为 `adapter_id=mock`、内置 Prompt 文本 `ragops-default-v1`、`generation.model=mock-ragops-v1`、其他生成参数取默认值，`prompt_version` 仅映射为 Prompt 版本。旧 `model_version` 保留为 `legacy_model_label` 展示字段，不能当作本次 requested/actual model；旧 `config_version` 只作兼容标签，新 `config_version` 仍由完整快照计算。若请求同时出现 `execution` 与任一旧 `model_version`、`prompt_version`、`config_version`，返回 `422 AMBIGUOUS_EXECUTION_CONFIG`。

创建时只校验适配器注册、配置完整性、总开关和能力，不做提供方探测。有效任务返回 `202`；不可用执行方式不创建任务。任务创建后即使运行环境改变，也保留原快照；执行时仍须再次检查当前网络总开关。

### 8.2 不可变 `ExecutionSnapshot`

任务创建事务内固定以下字段：

| 字段 | 类型 |
| --- | --- |
| `contract_version` | 固定 `2.0` |
| `adapter_id` | `mock` 或 `openai_compatible` |
| `provider_id` | mock 为 null；真实适配器为 `openai_compatible` |
| `prompt` | `{version, text}` |
| `generation` | 解析默认值后的完整 `GenerationConfig` |
| `context_policy` | `dataset_contexts`、`none`、`retrieval` |
| `dataset` | `{id, version, schema_version, content_sha256}` |
| `metric_config` | 创建时的完整指标配置 |
| `quality_gate` | 解析后的 `QualityGate` 或 null |
| `external_calls_enabled_at_creation` | boolean，仅审计；不能绕过执行时开关 |
| `created_at` | UTC RFC 3339 时间 |
| `config_version` | 快照非 secret 内容的规范 JSON SHA-256 |

快照不得含 Key、鉴权头、环境变量原值、原始提供方配置或测试 transport。配置版本由上述非 secret 内容的规范 JSON SHA-256 生成，字段名为 `config_version`；它不是连接已验证证明。

### 8.3 三类状态

| 类型 | 枚举 | 规则 |
| --- | --- | --- |
| 任务生命周期 `status` | `queued`、`running`、`completed`、`failed`、`cancelled` | 全失败为 `failed`；部分失败仍为 `completed` |
| 执行结果 `outcome` | `succeeded`、`partial_failed`、`failed`、null | 非终态为 null |
| 质量状态 `quality_status` | `not_evaluated`、`evaluated`、`partial`、`error`、`legacy_unknown` | 创建时 `not_evaluated`；不能由 outcome 推导 |
| 质量结论 `quality_verdict` | `passed`、`failed`、`unknown` | 默认 `unknown`；只有显式质量门规则可产生 passed/failed |

`quality_score` 为 `number 0..100` 或 null，默认 null。执行成功率只能进入运行指标，不能写入 `quality_score`。

所有终态任务，包括全部样本失败的任务，都必须生成可查询报告。失败报告的执行汇总如实记录失败，质量保持 `not_evaluated`/`unknown`，不得让报告永久 `REPORT_NOT_READY`。

`EvaluationJobResponse` 必须保留现有 ID、名称、生命周期、计数、进度、失败、时间和 links 字段，并新增 `schema_version="2.0"`、`execution_snapshot`、`quality_status`、`quality_verdict`、`quality_score`。现有 `model_version`、`prompt_version` 和 `metric_config` 在 2.x 内保留为快照的兼容投影。旧行可返回 `adapter_id="legacy_deterministic"`，但该值只读且不能用于创建新任务。

## 9. 数据集 2.0 与 1.0 兼容

### 9.1 2.0 样本

新样本将原始输入、标签、上下文来源和历史输出分开：

```json
{
  "schema_version": "2.0",
  "sample_id": "sample-001",
  "question": "如何重置演示账户密码？",
  "labels": {
    "reference_answer": "在设置页选择重置密码。",
    "gold_document_ids": ["doc-account"],
    "gold_evidence_ids": ["ev-reset"],
    "expected_diagnoses": []
  },
  "contexts": [
    {
      "origin": "provided",
      "rank": 1,
      "rank_before": null,
      "retrieval_run_id": null,
      "doc_id": "doc-account",
      "chunk_id": "chunk-reset",
      "evidence_ids": ["ev-reset"],
      "text": "演示账户可在设置页选择重置密码。",
      "score": null,
      "relevance_grade": 3,
      "usefulness": true
    }
  ],
  "historical_output": null,
  "tags": ["synthetic"],
  "metadata": {}
}
```

`contexts[].origin` 为 `provided`、`retrieved`、`legacy_unknown`：

- `provided`：人工或外部调用方直接给定；`retrieval_run_id` 必须为 null。
- `retrieved`：某次可追溯检索实际返回；`retrieval_run_id` 必须非空。
- `legacy_unknown`：旧数据无法证明来源；不得按检索结果计分。

`rank` 在样本内唯一且从 1 开始；`rank_before` 仅在有可追溯 rerank 前排名时使用。`doc_id`、`chunk_id` 非空；`score` 只记录来源系统返回值，不伪造。`relevance_grade` 为 null 或 `0..3`，`usefulness` 为 boolean 或 null。

`historical_output` 为 null 或 `{answer, citations, recorded_at}`。它仅用于展示导入前已有的回答，不是本次运行输出，不进入 `ModelRequest`，不作为执行失败的回退值。

### 9.2 1.0 归一化

现有 `/api/v1` 客户端可继续发送 `schema_version: "1.0"`。为兼容旧客户端，顶层和样本都缺失 `schema_version` 时仅在 `/api/v1` 视为 `1.0`；显式 null、空白或未知值返回 422。归一化规则固定如下：

| 1.0 字段 | 2.0 内部字段 | 兼容语义 |
| --- | --- | --- |
| `question` | `question` | 原样保留 |
| `reference_answer` | `labels.reference_answer` | 标签，绝不进入模型请求 |
| `gold_document_ids` | `labels.gold_document_ids` | 标签 |
| `gold_evidence_ids` | `labels.gold_evidence_ids` | 标签 |
| `expected_diagnoses` | `labels.expected_diagnoses` | 标签 |
| `retrieved_contexts` | `contexts` | `origin=legacy_unknown`，不得因旧字段名断言真实检索 |
| `answer` | `historical_output.answer` | 历史回答，不是本次输出 |
| `citations` | `historical_output.citations` | 历史引用；缺少支持判断保持 null |
| `tags`、`metadata` | 同名字段 | 保留，但不进入模型请求 |

新 2.0 输入禁止旧字段与新字段混用，混用返回 `422 AMBIGUOUS_SCHEMA_FIELDS`。未知版本返回 `422 UNSUPPORTED_SCHEMA_VERSION`，`error.details.supported_versions` 固定为 `["1.0", "2.0"]`。

创建与导入均为事务原子操作：任一行失败则接受 0 行。批内重复 `sample_id` 返回 422；与数据库已有样本冲突返回 409。错误详情使用 `errors[]`，每项固定为 `row`（从 1 开始或 null）、`sample_id`、`field`（点路径）、`code`、`message`，便于前端定位。

## 10. 样本运行与 API 投影

任务创建时为每个样本生成独立 `run_id`。`GET /evaluation-jobs/{job_id}/samples`、报告内部样本和导出样本使用同一个 `EvaluationSampleResult` 结构，不得分别发明字段。

最小成功结果：

```json
{
  "schema_version": "2.0",
  "id": "job-sample-001",
  "sample_id": "sample-001",
  "question": "如何重置演示账户密码？",
  "labels": {
    "reference_answer": "在设置页选择重置密码。",
    "gold_document_ids": ["doc-account"],
    "gold_evidence_ids": ["ev-reset"],
    "expected_diagnoses": []
  },
  "reference_answer": "在设置页选择重置密码。",
  "historical_answer": null,
  "run": {
    "run_id": "run-001",
    "status": "succeeded",
    "adapter_id": "mock",
    "provider_id": null,
    "requested_model": "mock-ragops-v1",
    "actual_model": "mock-ragops-v1",
    "is_mock": true,
    "finish_reason": "stop",
    "answer": "[mock] 演示账户可在设置页选择重置密码。",
    "contexts": [
      {
        "origin": "provided",
        "rank": 1,
        "rank_before": null,
        "retrieval_run_id": null,
        "doc_id": "doc-account",
        "chunk_id": "chunk-reset",
        "evidence_ids": ["ev-reset"],
        "text": "演示账户可在设置页选择重置密码。",
        "score": null,
        "relevance_grade": 3,
        "usefulness": true
      }
    ],
    "citations": [],
    "latency_ms": 0,
    "usage": null,
    "cost": null,
    "provider_request_id": null,
    "attempt_count": 1,
    "attempts": [
      {
        "number": 1,
        "status": "succeeded",
        "latency_ms": 0,
        "error_code": null,
        "retry_delay_ms": 0,
        "started_at": "2026-09-05T08:00:00Z",
        "finished_at": "2026-09-05T08:00:00Z"
      }
    ],
    "error": null,
    "started_at": "2026-09-05T08:00:00Z",
    "finished_at": "2026-09-05T08:00:00Z"
  },
  "quality_status": "not_evaluated",
  "metric_results": [],
  "diagnoses": [],
  "review_status": "pending",
  "reviewed_at": null
}
```

`run.status` 枚举为 `queued`、`running`、`succeeded`、`failed`、`cancelled`。运行中 `answer`、`actual_model`、`finish_reason`、`usage`、`cost`、`provider_request_id`、`error` 和 `finished_at` 可为 null。失败时 `answer=null`、`error=ModelError`，并仍保存上下文、尝试和时间。

`labels` 使用第 9 节的同一结构，只供 API 展示和评测；它不进入模型请求。`run.contexts[]` 使用第 9 节上下文的全部字段。`attempts[].status` 为 `succeeded`、`failed`、`timeout`、`cancelled`，`error_code` 只能是 `ModelErrorCode` 或 null；只记录安全摘要，不记录请求/响应正文。

`run.citations[]` 固定字段为 `citation_id`、`claim_id`（可空）、`raw`、`target_type`（`context_item`、`document`、`external`）、`target_id`、`resolved`、`supports_claim`（可空）、`support_judge_version`（可空）。解析器只能填写 `resolved`；没有独立语义判断时 `supports_claim=null`。

兼容投影：现有样本响应顶层 `answer` 暂时保留，值只能等于 `run.answer`；无本次运行时为 null，绝不能回退 `historical_answer` 或 `reference_answer`。现有 `retrieval_results` 暂时投影 `run.contexts`，但新客户端必须读取带 `origin` 的 `run.contexts`。弃用字段至少保留整个 2.x 周期。

## 11. 指标和质量状态

`MetricResult.status` 扩展为：

| 状态 | `value` | 含义 |
| --- | --- | --- |
| `ok` | number 或 boolean | 所需输入存在且指标已执行 |
| `not_evaluated` | null | 指标实现/判定器未运行或本阶段未实现 |
| `not_applicable` | null | 该样本语义上不适用，例如无引用时的引用解析率 |
| `unknown` | null | 输入存在但来源或含义无法证明 |
| `error` | null | 指标执行失败；详情只含安全错误码 |
| `legacy` | null 或旧值 | 旧记录原样保留，不能按 2.0 语义重解释 |

每个指标仍包含 `metric_name`、`metric_version`、`status`、`value`、`details`。报告聚合还包含 `evaluated_count`、`excluded_count` 和各状态计数；只有 `status=ok` 的值进入聚合。

强制语义：

1. `execution_success_rate = succeeded_count / total_count` 是运行指标，不是质量指标，不参与 `quality_score` 或 `quality_verdict`。
2. Recall@K、MRR@K、NDCG@K 和 rerank 效果只接受 `origin=retrieved` 且 `retrieval_run_id` 属于本次运行的上下文。`provided` 为 `not_evaluated`，`legacy_unknown` 为 `unknown`。
3. 给定上下文可在有明确人工相关性标签时计算上下文精度/相关性，但详情必须标 `context_origin=provided`，不得改名为检索召回。
4. 引用解析单独使用 `citation_resolution_rate`。语义支持使用 `citation_support_rate`；任一引用缺少 `supports_claim` 时该指标为 `not_evaluated`，不得用相关片段或 gold 命中推断支持。
5. 旧 `citation_hit_rate` 在 2.0 中弃用；兼容计算只有在所有引用都有显式 `supports_claim` 时才可 `ok`，否则为 `not_evaluated`。
6. 未配置质量门时，即使所有可执行指标均成功，任务仍为 `quality_status=not_evaluated`、`quality_verdict=unknown`、`quality_score=null`。

## 12. HTTP 与错误语义

统一 API 错误信封保持：

```json
{
  "error": {
    "code": "EXTERNAL_CALLS_DISABLED",
    "message": "External model calls are disabled by server policy.",
    "details": {},
    "request_id": "request-001",
    "retryable": false
  }
}
```

| 场景 | HTTP | API 错误码 | 行为 |
| --- | --- | --- | --- |
| 未知适配器/不支持参数 | 422 | `EXECUTION_ADAPTER_NOT_FOUND` / `PROVIDER_CAPABILITY_UNSUPPORTED` | 不创建任务 |
| 提供方未配置 | 409 | `PROVIDER_NOT_CONFIGURED` | 不创建任务，不探测 |
| 外部调用被禁用 | 403 | `EXTERNAL_CALLS_DISABLED` | 不创建任务或不发 transport |
| 本阶段请求 retrieval | 409 | `EXECUTION_MODE_UNAVAILABLE` | 不静默改用给定上下文 |
| 输入字段/版本错误 | 422 | `VALIDATION_ERROR` / `UNSUPPORTED_SCHEMA_VERSION` | 原子回滚 |
| 重复样本/幂等冲突 | 409 | `DUPLICATE_SAMPLE_ID` / `IDEMPOTENCY_KEY_CONFLICT` | 保留原数据 |
| 上游鉴权/响应/5xx/传输 | 502 | 对应 `ModelError.code` | 已接受异步任务时持久化到 run，不改 HTTP 历史 |
| 上游限流 | 503 | `PROVIDER_RATE_LIMITED` | 可带截断后 `retry_after_ms` |
| 上游超时 | 504 | `PROVIDER_TIMEOUT` | 持久化实际 attempts |

异步任务一旦以 202 接受，后续提供方失败通过任务、样本和报告的 `run.error` 查询，不能把后台失败伪装成原 POST 的 HTTP 错误。已知终态任务的报告返回 200；只有非终态返回 `409 REPORT_NOT_READY`。

## 13. 报告与导出

报告必须分开运行和质量：

```json
{
  "schema_version": "2.0",
  "id": "report-001",
  "job_id": "job-001",
  "status": "completed",
  "generated_at": "2026-09-05T08:00:01Z",
  "execution_summary": {
    "outcome": "succeeded",
    "total_count": 1,
    "succeeded_count": 1,
    "failed_count": 0,
    "success_rate": 1.0
  },
  "quality_summary": {
    "status": "not_evaluated",
    "verdict": "unknown",
    "score": null,
    "evaluated_sample_count": 0
  },
  "execution_snapshot": {
    "contract_version": "2.0",
    "adapter_id": "mock",
    "provider_id": null,
    "prompt": {
      "version": "support-rag-v2",
      "text": "仅依据给定上下文回答；证据不足时明确说明。"
    },
    "generation": {
      "model": "mock-ragops-v1",
      "temperature": 0.0,
      "top_p": 1.0,
      "max_output_tokens": 512,
      "stop": [],
      "seed": null
    },
    "context_policy": "dataset_contexts",
    "dataset": {
      "id": "dataset-demo-v2",
      "version": "v2",
      "schema_version": "2.0",
      "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    },
    "metric_config": [],
    "quality_gate": null,
    "external_calls_enabled_at_creation": false,
    "created_at": "2026-09-05T08:00:00Z",
    "config_version": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "metrics": [
    {
      "metric_name": "execution_success_rate",
      "metric_version": "2.0.0",
      "status": "ok",
      "value": 1.0,
      "evaluated_count": 1,
      "excluded_count": 0,
      "details": {
        "aggregation": "successful_samples / total_samples"
      }
    }
  ],
  "links": {
    "job": "/api/v1/evaluation-jobs/job-001",
    "samples": "/api/v1/evaluation-jobs/job-001/samples",
    "export": "/api/v1/evaluation-jobs/job-001/report/export"
  }
}
```

导出固定为：

```json
{
  "schema_version": "2.0",
  "exported_at": "2026-09-05T08:00:02Z",
  "report": {},
  "samples": []
}
```

其中 `report` 是上面的完整报告，`samples` 是第 10 节完整结果，不是删减版。API 列表、报告和导出中的同名字段类型、枚举和 null 语义必须一致。未知 Token/成本为 null，前端显示“未知”；未执行指标显示“未评估”，不得显示 0。

## 14. 持久化与幂等迁移

后端实现必须引入版本化迁移，不能继续用 `create_all` 升级旧库。冻结的迁移链：

1. `0001_mvp_baseline`：描述当前 main 的表结构。
2. `0002_model_execution_contract`：增加本节字段并迁移 1.0 数据。

对没有迁移版本表但符合当前 MVP 结构的数据库，先验证必需表/列，再 stamp `0001_mvp_baseline`，随后执行 0002；结构不匹配则停止并报错，不猜测或删库。迁移必须在事务中可重复执行，连续执行两次第二次为空操作。

冻结的新增持久化字段：

| 表 | 字段 | 旧行回填 |
| --- | --- | --- |
| `dataset_samples` | `normalized_schema_version`、`context_origin`、`historical_answer`、`historical_citations` | `1.0`、`legacy_unknown`、复制旧 `answer`、复制旧 `citations` |
| `evaluation_jobs` | `contract_version`、`adapter_id`、`execution_snapshot`、`quality_status`、`quality_verdict`、`quality_score` | `1.0`、`legacy_deterministic`、null、`legacy_unknown`、`unknown`、null |
| `evaluation_job_samples` | `run_id`、`run_snapshot`、`quality_status` | null、null、`legacy_unknown` |
| `evaluation_reports` | `schema_version`、`execution_summary`、`quality_summary`、`execution_snapshot` | `1.0`、由历史计数复制、legacy unknown、null |

旧列不在 0002 删除或改名。新代码只把新运行回答写入 `evaluation_job_samples.run_snapshot/answer`，不得修改 `dataset_samples.historical_answer`、参考标签或内容哈希。旧报告继续可查，使用兼容投影：`actual_model=null`、`is_mock=null`、provider 状态未知、质量 `legacy_unknown`；不得从 `model_version` 或成功状态倒推真实模型、mock 或质量通过。

新建空库通过迁移到 head；`create_all` 仅可留作隔离单测临时库，不能作为应用升级路径。迁移失败不得自动删除、重建或覆盖用户数据库。

## 15. 前后端与 QA 验收断言

- 后端：捕获 `ModelRequest` 和 OpenAI 兼容 payload，使用唯一哨兵证明所有标签/历史字段均未泄漏。
- 后端：有假凭据但总开关关闭时，真实 transport spy 调用数必须为 0；配置/status/readiness 同样为 0。
- 后端：覆盖 401/403、429、timeout、5xx、网络错误、空/非法 JSON和字段缺失，断言错误码、总尝试次数、单次/总时间与脱敏。
- 后端：同一数据集两次 mock 运行产生独立 run，评测读取各自本次回答；原样本、标签和哈希不变。
- 数据：1.0 导入、2.0 导入、未知版本、缺失/null/空白、批内/库内重复 ID、context/citation 关系均有字段路径断言。
- 迁移：从 1.0 fixture 数据库执行两次迁移，旧样本、任务、报告和复核状态仍可查询。
- 前端：同时展示前端模式、后端适配器、提供方三态；`api + mock + configured_unverified` 可以同时出现。
- 前端：执行成功但无质量门时显示“执行成功 / 质量未评估 / 分数未知”，不得显示 100 或 passed。
- 指标：`provided`/`legacy_unknown` 不产生检索召回分；可解析引用但无语义判断时支持指标为 `not_evaluated`。

## 16. Codex 扩展点

未来适配器可通过同一 `ModelAdapter` 和工厂注册 `adapter_id="codex"`，但本阶段不实现、不登录、不探测，也不把 ChatGPT Plus 或其他订阅解释为通用 API 额度。后续开始前必须依据届时官方文档和一次用户授权的受控实验确认：

- 官方支持的程序化集成入口是否适合本产品，而不是依赖交互式客户端或未公开接口。
- 账号/组织授权、执行环境、数据处理边界、权限和额度限制。
- 结构化输出、取消、单次/总超时、并发和限流语义。
- 实际模型标识、请求 ID、Token 用量是否稳定可用，不能缺失时估算。

无论未来提供方如何，仍必须遵守本契约的请求白名单、外部调用总开关、错误脱敏、显式选择、无静默回退和状态诚实原则。
