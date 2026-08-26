# RAGOps 评测测试样例

这些文件是 QA 基线，不包含真实用户数据，也不表示平台已经实现。

## 文件说明

- `valid-samples.jsonl`：6 条有效评测 trace。每行是一个独立 JSON 对象，可用于导入预览、E2E 报告和诊断展示。
- `invalid-samples.jsonl`：校验测试 envelope。测试工具应取每行的 `input` 作为被测请求，并将错误码与 `expected_error` 比较；该文件本身不是直接上传的数据集。
- `metric-cases.json`：指标纯函数 oracle，包含输入、中间口径和期望结果。

## 有效样例最小字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `schema_version` | string | 夹具 schema 版本 |
| `sample_id` | string | 数据集内唯一、非空的稳定 ID |
| `question` | string | 用户问题，trim 后非空 |
| `reference_answer` | string/null | 金标答案；不可回答问题可为 null |
| `gold_document_ids` | string[] | 与问题相关的文档 ID |
| `gold_evidence_ids` | string[] | 用于 context recall 的最小证据单元 ID |
| `retrieved_contexts` | object[] | 按 `rank` 递增的检索 trace，含 doc/chunk/evidence/text |
| `answer` | string | 被评测回答 |
| `citations` | object[] | claim 到 chunk 的显式引用 |
| `tags` | string[] | 场景标签 |
| `expected_diagnoses` | string[] | 用于测试诊断规则的预期候选原因 |

这里的 trace 同时带检索结果和回答，便于在尚未连接真实 provider 时稳定复现。生产数据导入若只接收问题和 gold，应由测试适配器投影所需字段；评测结果接口仍需能表达完整 trace。

## 校验要求

- JSON 按 UTF-8 解析；禁止重复 key。
- `sample_id` 在一个数据集版本内唯一。
- `rank` 从 1 开始且在样本内唯一；API 返回时严格递增。
- `citations[].chunk_id` 必须能解析到同一样本的 `retrieved_contexts[].chunk_id`，否则保留为诊断错误但不得指向错误上下文。
- `gold_evidence_ids` 中的 ID 必须能被金标语料解析；无 gold 的不可回答样例允许空数组。
- 夹具中 `expected_diagnoses` 是测试 oracle，不应作为模型输入。

## 本地快速解析

PowerShell 可在不安装依赖的情况下检查基本 JSON 语法：

```powershell
Get-Content examples/eval-samples/valid-samples.jsonl |
  ForEach-Object { $_ | ConvertFrom-Json | Out-Null }

Get-Content examples/eval-samples/invalid-samples.jsonl |
  ForEach-Object { $_ | ConvertFrom-Json | Out-Null }

Get-Content -Raw examples/eval-samples/metric-cases.json |
  ConvertFrom-Json | Out-Null
```

正式 CI 还必须执行 schema、唯一性、rank、gold/citation 引用完整性和数值 oracle 校验，不能只验证 JSON 可解析。
