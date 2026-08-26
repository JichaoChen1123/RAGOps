# RAG 评测指标、数据模型与执行流程

本文定义 RAGOps 的离线评测口径。目标不是只给出一个总分，而是保留从测试问题、检索、上下文、回答、引用到评分的完整证据链，使每次低分都能回溯到具体阶段。

## 1. 评测边界与公共约定

### 1.1 评测单元

一个 `eval_case` 是稳定的测试输入和期望；一个 `eval_run_item` 是某个系统配置在该用例上的一次执行。两者必须分离，避免运行结果污染数据集版本。

- 数据集必须不可变版本化：修改问题、期望答案或金标证据后生成新的 `dataset_version`。
- 系统配置必须有 `config_version`，至少包含语料快照、切分、Embedding、检索、Rerank、Prompt 和生成模型版本。
- 所有排序指标以 `rank` 为准，不使用未经校准的跨模型相似度分数直接比较。
- 缺失输入返回 `not_applicable`，不能用 0 代替。例如没有金标证据时不能计算 Recall@K。
- 用例级分数先计算，再做宏平均；同时报告有效样本数、跳过数和置信区间。流量平均可以另报，不能替代宏平均。
- 阈值属于数据集、业务场景和版本配置，本文不编造固定的“合格线”。上线前用基线分布和人工复核共同标定。

### 1.2 相关性与声明口径

检索相关性采用分级标注 `relevance_grade ∈ {0,1,2,3}`：

| 等级 | 含义 |
| --- | --- |
| 0 | 与问题无关或不能帮助作答 |
| 1 | 背景相关，但不直接支持必需事实 |
| 2 | 支持至少一个必需事实 |
| 3 | 直接且充分支持核心答案 |

二值指标把 `grade >= 2` 视为 relevant。每条期望答案拆为最小可验证的 `required_fact`；生成答案也拆为 `answer_claim`。事实和声明是 Context Recall、Faithfulness、引用支持判断的共同原子单位。

## 2. 指标体系

### 2.1 检索与排序

#### Recall@K

- 输入：`gold_evidence` 的相关文档/Chunk ID 集合 `G`，检索前 K 个结果 ID 集合 `R_K`，可选 ID 映射关系。
- 计算：`Recall@K = |G ∩ R_K| / |G|`。同一金标证据被多个重叠 Chunk 命中时只计一次；`|G| = 0` 时为 `not_applicable`。
- 定位：低分说明金标证据未进入可用窗口，但不能单独区分语料缺失、召回器失败、ID 对齐失败或 K 太小。
- 展示：K、得分、命中的金标 ID、漏掉的金标 ID，以及 Recall@1/3/5/10 曲线。

#### MRR

- 输入：有序检索结果和二值相关性标签。
- 计算：`MRR = mean(1 / first_relevant_rank)`；无相关结果时该用例记 0。
- 定位：Recall 尚可但 MRR 低，通常表示证据能召回但排名靠后，优先检查排序信号或 Rerank。
- 注意：每个用例只看第一个相关结果，不衡量多个证据是否齐全。

#### NDCG@K

- 输入：前 K 个结果的 `relevance_grade`，以及该用例完整 qrels（金标相关性集合）构造的理想排序。
- 计算：`DCG@K = Σ((2^grade_i - 1) / log2(i + 1))`，`NDCG@K = DCG@K / IDCG@K`；`IDCG@K = 0` 时为 `not_applicable`。
- 定位：同时反映相关性强弱和位置。Recall 正常而 NDCG 低，说明高价值证据被弱相关结果压后。
- 展示：实际/理想等级序列、每个位置的增益和分母，便于审计。IDCG 不能只对已召回结果重排，否则会掩盖漏召回；若 qrels 不完整，应标记为 pooled judgment 并展示标注覆盖率。

### 2.2 上下文质量

这里的 `context_item` 指最终送入生成模型的内容，不能用召回候选替代。

#### Context Precision@K

- 输入：按最终上下文顺序排列的 K 个 `context_item`，以及每项是否有助于支持任一 `required_fact` 的标签 `y_i ∈ {0,1}`。
- 计算：`P@i = Σ(y_j, j<=i)/i`；`ContextPrecision@K = Σ(P@i × y_i) / Σ(y_i)`。K 内无有用上下文时记 0。
- 定位：低分表示最终窗口被噪声占用或有用内容排序靠后，常见于宽松召回、Rerank 无效、去重失败或 Chunk 过大。
- 证据：保存每个上下文的 usefulness 标签、判定理由和 judge 版本。

#### Context Recall

- 输入：金标 `required_fact` 集合 `F`，最终上下文 `C`，每个事实是否能被 C 中至少一段证据支持。
- 计算：`ContextRecall = supported_required_facts / |F|`；没有必需事实的不可回答用例为 `not_applicable`。
- 定位：低分说明送入模型的证据不完整。结合检索 Recall 可区分“没召回”与“召回后被截断/过滤”。
- 证据：`fact_id -> supporting_context_item_ids` 映射，不能只存最终分数。

#### Context Utilization（扩展）

- 输入：回答声明与上下文支持映射、上下文 token 数。
- 计算：被至少一个回答声明使用的上下文 token（或句子）占总上下文 token（或句子）的比例。
- 定位：Context Recall 高但利用率低时，生成模型可能忽略了证据，或上下文组织方式阻碍阅读。

### 2.3 回答、事实性与引用

#### Faithfulness

- 输入：模型回答拆出的可验证 `answer_claim`，最终上下文，以及逐声明的 `supported / contradicted / unsupported` 判定。
- 计算：`Faithfulness = supported_claims / verifiable_claims`。纯格式或寒暄不算声明；没有可验证声明的正确拒答为 `not_applicable`，由拒答指标评价。
- 定位：检索和 Context Recall 良好但 Faithfulness 低，说明生成阶段出现无依据扩写、冲突采信或 Prompt 约束不足。
- 证据：每个声明必须保存支持的 `context_item_id`、字符区间/句子区间、判定理由和 judge 版本。

#### Answer Relevancy

- 输入：用户问题、可选对话历史、回答、期望的 `required_fact` 和动作约束。
- 计算：版本化 judge 分别给出 `directness`、`intent_coverage`、`conciseness` 的 0～1 分，默认等权平均；业务可在配置中改权重。MVP 不把向量余弦值当作可解释的最终分数。
- 定位：低分表示答非所问、关键信息遗漏或冗余掩盖答案；它不证明回答事实正确。
- 稳定性：保存 rubric、judge 模型和 Prompt 版本；边界样本进行人工抽检。

#### 引用命中率（Citation Hit Rate）

- 输入：回答中解析出的引用、引用目标、对应声明，以及目标内容是否支持该声明。
- 计算：`CitationHitRate = supporting_resolved_citations / parsed_citations`。无法解析、目标不存在、越权来源或不支持声明均不命中；回答没有引用时为 `not_applicable`，另报引用覆盖率。
- 定位：低分定位引用解析、ID 映射或“引用存在但证据不支持”的问题。
- 配套指标：`CitationCoverage = claims_with_supporting_citation / claims_requiring_citation`；二者必须同时展示，避免“只引用一个正确来源”获得虚高评价。

#### 拒答正确率

- 输入：`expected.answerable`、期望动作和系统实际 `refused` 判定。
- 计算：分别报告可回答样本的误拒答率和不可回答样本的正确拒答率；总准确率仅作概览。
- 定位：区分安全阈值过严、检索缺失导致的误拒答，以及无证据仍作答的风险。

### 2.4 性能与成本

#### 延迟

- 输入：一次运行的 trace/span 起止时间，至少包含 retrieval、rerank、generation、tool 和 total。
- 计算：用例级毫秒数；聚合报告 p50、p90、p95、p99、均值和超时率。阶段并行时总延迟按根 span 计算，不能把子 span 简单相加。
- 定位：利用关键路径定位检索、Rerank、模型首 token、生成或外部工具瓶颈。
- 扩展：同时记录 `time_to_first_token_ms` 与 `tokens_per_second`。

#### 成本

- 输入：模型/Embedding/Rerank 的输入输出 token 或计费单位、调用次数，以及运行时锁定的 `price_snapshot`。
- 计算：`Cost = Σ(usage_quantity × unit_price)`；按用例保存币种和明细，聚合报告均值、p95、每个成功回答成本。
- 定位：与质量指标联看，识别增加 K、上下文长度或模型升级是否带来足够收益。
- 约束：未知单价记 `unknown`，不能默认为 0；价格快照必须带生效时间和供应商。

### 2.5 指标依赖矩阵

| 指标 | 金标答案/事实 | 金标证据 | 有序候选 | 最终上下文 | 回答 | 引用 | Trace/Usage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Recall@K |  | 必需 | 必需 |  |  |  |  |
| MRR |  | 必需 | 必需 |  |  |  |  |
| NDCG@K |  | 分级标签 | 必需 |  |  |  |  |
| Context Precision | 事实有助判定 |  |  | 必需 |  |  |  |
| Context Recall | 必需 |  |  | 必需 |  |  |  |
| Faithfulness |  |  |  | 必需 | 必需 |  |  |
| Answer Relevancy | 推荐 |  |  |  | 必需 |  |  |
| 引用命中率 |  |  |  | 必需 | 必需 | 必需 |  |
| 拒答正确率 | `answerable` |  |  |  | 必需 |  |  |
| 延迟/成本 |  |  |  |  |  |  | 必需 |

## 3. 数据模型

### 3.1 核心关系

```text
evaluation_dataset 1 ── N eval_case 1 ── N required_fact
                               └─────── N gold_evidence
evaluation_run     1 ── N eval_run_item 1 ── N retrieval_candidate
                                      ├── N context_item
                                      ├── 1 model_response ── N answer_claim
                                      │                    └── N citation
                                      ├── N metric_result
                                      └── N diagnosis_result
eval_run_item      1 ── 1 trace ── N span
```

### 3.2 建议后端表

| 表 | 必需字段 | 用途/约束 |
| --- | --- | --- |
| `evaluation_dataset` | `id`, `name`, `version`, `content_hash`, `created_at` | `(name, version)` 唯一；发布后只读 |
| `eval_case` | `id`, `dataset_id`, `query`, `conversation_json`, `answerable`, `expected_action`, `slice_tags_json` | 问题与场景切片 |
| `required_fact` | `id`, `case_id`, `text`, `weight` | Context Recall 和答案完整度原子 |
| `gold_evidence` | `id`, `case_id`, `doc_id`, `chunk_id`, `span_json`, `relevance_grade`, `corpus_version` | `chunk_id` 可空以支持文档级金标 |
| `evaluation_run` | `id`, `dataset_id`, `config_version`, `git_sha`, `status`, `started_at`, `finished_at` | 一次可复现批次 |
| `eval_run_item` | `id`, `run_id`, `case_id`, `status`, `trace_id`, `error_code`, `started_at`, `finished_at` | 用例执行状态；`(run_id, case_id)` 唯一 |
| `retrieval_candidate` | `run_item_id`, `stage`, `rank`, `doc_id`, `chunk_id`, `score`, `relevance_grade`, `content_hash`, `metadata_json` | `stage` 区分 vector/BM25/fusion/rerank |
| `context_item` | `id`, `run_item_id`, `position`, `doc_id`, `chunk_id`, `text`, `token_count`, `truncated`, `source_uri` | 真实入模内容；敏感文本可对象存储，只留引用 |
| `model_response` | `id`, `run_item_id`, `text`, `refused`, `finish_reason`, `model`, `prompt_version` | 最终回答和生成配置 |
| `answer_claim` | `id`, `response_id`, `text`, `span_start`, `span_end`, `verdict`, `support_context_ids_json`, `judge_version` | Faithfulness 可审计证据 |
| `citation` | `id`, `response_id`, `claim_id`, `raw`, `target_type`, `target_id`, `resolved`, `supports_claim` | 引用解析和命中 |
| `metric_result` | `id`, `run_item_id`, `metric_name`, `metric_version`, `value`, `status`, `details_json`, `judge_version` | `status=ok/not_applicable/error`，不能仅存 value |
| `diagnosis_result` | `id`, `run_item_id`, `rule_id`, `rule_version`, `severity`, `confidence`, `evidence_json`, `suggestions_json` | 可解释故障结论 |
| `trace_span` | `trace_id`, `span_id`, `parent_span_id`, `name`, `start_at`, `end_at`, `status`, `attributes_json`, `usage_json`, `cost_json` | OpenTelemetry 风格执行链路 |
| `price_snapshot` | `id`, `provider`, `sku`, `unit`, `unit_price`, `currency`, `effective_at` | 可复算成本 |

高基数字段如正文、Prompt 和 judge 原始响应可放对象存储；关系库保存哈希、URI 与必要索引。所有 `details_json` 都应有 `schema_version`，后续可无损迁移。

### 3.3 单记录交换格式

批量导入/导出使用 JSONL，每行包含 `case`、`run` 和可选 `evaluation`。机器校验文件见 `examples/datasets/rag_eval_case.schema.json`，示例见 `examples/datasets/rag_eval_sample.jsonl`。该格式用于交换，不要求后端把嵌套 JSON 原样存成单表。

### 3.4 Trace 属性

建议统一 span 名称：

- `rag.query.prepare`
- `rag.retrieve.vector` / `rag.retrieve.keyword`
- `rag.retrieve.fusion`
- `rag.rerank`
- `rag.context.build`
- `rag.generate`
- `rag.tool.call`
- `rag.evaluate.<metric_name>`

公共属性至少包括 `run_id`、`run_item_id`、`case_id`、`config_version`、`model`、`corpus_version`、`top_k`、`status_code`。禁止把密钥或未经脱敏的用户隐私写入 span attribute。

## 4. 评测执行流程

1. **冻结输入**：校验数据集版本、语料版本和配置版本；为数据集生成内容哈希。
2. **执行并采集**：运行 query rewrite、检索、融合、Rerank、上下文构建、生成和工具调用；写入完整 trace 与各阶段候选。
3. **规范化**：解析回答声明和引用，对齐文档/Chunk ID，记录截断与去重结果。
4. **确定性评分**：先算 Recall@K、MRR、NDCG、延迟、成本和引用解析成功率。
5. **Judge 评分**：批量计算上下文 usefulness、事实支持、Faithfulness 和 Answer Relevancy；固定模型、温度、rubric 与 Prompt 版本。
6. **质量控制**：对 judge 错误重试；对低置信、冲突和阈值附近样本进入人工复核队列，不覆盖原始自动评分。
7. **诊断**：基于指标、trace 和配置运行版本化规则，输出证据、置信度和建议。
8. **聚合比较**：按数据集、业务切片、语言、问题类型和配置版本做宏平均及 bootstrap 置信区间；成对比较同一批 case，避免样本变化造成伪回归。
9. **发布**：保存运行快照，在看板展示总览、漏斗、分布、差异和失败样本，并允许下钻到 trace。

失败策略：单个 judge 或工具失败只把对应 metric 标为 `error`；运行仍可完成但显示数据完整率。核心执行失败则 `eval_run_item.status=failed`，不得把缺失指标自动填 0。

## 5. 前端展示字段

### 5.1 运行总览

- 标识：`run_id`、数据集名称/版本、`config_version`、`git_sha`、运行状态和时间范围。
- KPI：每个指标的均值、p50/p95（适用时）、置信区间、有效/跳过/错误样本数、相对基线变化。
- 筛选：`slice_tags`、语言、问题类型、answerable、模型、语料版本、诊断类型、严重级别。
- 成本性能：阶段延迟堆叠、TTFT、token、成本，以及质量-成本散点图。

### 5.2 用例下钻

- 输入与期望：问题、对话、参考答案、required facts、金标证据。
- 检索对比：各 stage 的 rank/score/grade、命中状态、Rerank 前后名次变化。
- 上下文：真实入模顺序、截断、token、usefulness 和支持事实高亮。
- 回答：声明高亮、supported/contradicted/unsupported、引用跳转与拒答状态。
- 分数：公式版本、输入计数、判定理由、judge 版本和 `not_applicable/error` 原因。
- 诊断：规则、严重性、置信度、证据链、建议和对应 trace span。

### 5.3 回归视图

前端比较接口应返回同一 `case_id` 的 `baseline_value`、`candidate_value`、`delta`、`regression` 和诊断变化。总览必须同时显示改善与退化用例数，不能只显示平均分变化。

## 6. MVP 与扩展路径

### MVP（首个可交付版本）

- 数据：版本化用例、required facts、金标证据、检索候选、最终上下文、回答、引用、trace 和 usage。
- 确定性指标：Recall@K、MRR、NDCG@K、引用解析/命中、总延迟与阶段延迟、token 与成本。
- Judge 指标：Context Precision、Context Recall、Faithfulness、Answer Relevancy；固定单一 rubric 并保存证据。
- 诊断：检索缺失、Rerank 无效、上下文污染、Prompt/幻觉候选、工具失败；规则见 `diagnosis-rules.md`。
- 看板：运行总览、版本对比、用例下钻、失败切片和 trace 时间线。

### 后续扩展

- Judge 校准：双 judge/仲裁、人工金标一致性、偏差和漂移监控。
- 反事实诊断：替换 oracle context、跳过 Rerank、切换检索器/Chunk 配置，估计各组件增益。
- 在线评测：用户反馈、任务成功率、无点击率、会话修复率，与离线用例关联。
- 安全与治理：PII 泄漏、权限越界引用、提示注入、来源新鲜度和冲突检测。
- 统计发布门禁：成对 bootstrap、最小可检测效应、分场景阈值和质量-成本 Pareto 前沿。
- 多轮与 Agent：对话状态保持、工具选择/参数正确率、计划完成度和端到端任务成功率。

## 7. 版本与审计要求

每个分数必须能回答“用什么输入、公式或 judge、何时算出、为何得到该值”。至少版本化 `dataset_version`、`corpus_version`、`config_version`、`metric_version`、`rule_version`、`judge_version`、`prompt_version` 和 `price_snapshot_id`。重新评分写新结果，不覆盖历史结果。
