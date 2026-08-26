# RAG 故障诊断规则

诊断规则把指标、执行 trace 和配置差异组合成可审计的“候选根因”。单个低分通常只能说明症状，不能直接证明根因。每条结果必须返回 `evidence`、`confidence`、`severity` 和下一步验证动作。

## 1. 规则输入与输出

### 1.1 必需输入

- 用例标签：`answerable`、`required_fact`、`gold_evidence`、场景切片。
- 各检索阶段候选：初始向量/BM25、融合、Rerank 后排名和相关性标签。
- 最终上下文：顺序、token、截断、重复、来源、事实支持映射。
- 回答：声明、引用、拒答、Faithfulness 和 Answer Relevancy 证据。
- Trace：组件状态、超时、重试、延迟、模型/Prompt/语料/索引/Chunk 配置版本。
- 基线：同一数据集与 case 的上一稳定版本；没有基线时只给绝对症状，不给“退化”结论。

### 1.2 标准输出

```json
{
  "rule_id": "retrieval.missing_evidence",
  "rule_version": "1.0.0",
  "severity": "high",
  "confidence": 0.86,
  "status": "suspected",
  "evidence": [
    {"metric": "recall_at_5", "value": 0.0, "threshold_ref": "profile.default.recall_at_5.low"},
    {"gold_chunk_id": "chunk-42", "found_in_stage": null}
  ],
  "suggestions": ["检查金标证据是否存在于当前 corpus_version", "扩大候选池并对比 BM25 与向量召回"]
}
```

`confidence` 是证据强度，不是发生概率。阈值从 `diagnosis_profile` 读取，并记录 profile 版本；MVP 可以使用业务确认的配置值，但不能把样例值写死在代码中。

## 2. 决策顺序

先检查数据和执行完整性，再诊断检索、上下文和生成，避免把上游失败误判为模型幻觉。

```text
数据/工具有效？
  ├─ 否 → 数据管道或工具调用失败
  └─ 是 → 金标证据进入候选池？
           ├─ 否 → 语料缺失 / 检索缺失 / Embedding 不匹配
           └─ 是 → Rerank 后仍在有效窗口？
                    ├─ 否 → Rerank 无效 / 截断 / Chunk 问题
                    └─ 是 → 最终上下文足够且干净？
                             ├─ 否 → 上下文污染 / Chunk 粒度
                             └─ 是 → 回答是否忠实、相关、正确引用？
                                      ├─ 否 → Prompt 约束弱 / 模型幻觉 / 引用失败
                                      └─ 是 → 无质量故障或仅性能/成本问题
```

## 3. 诊断规则目录

### D01 检索缺失 `retrieval.missing_evidence`

- 症状：Recall@K 与 Context Recall 低，缺失的 required facts 可映射到未命中的金标证据。
- 强证据：金标文档存在于当前语料快照，但在所有初始候选池中都不存在；对应检索 span 成功完成。
- 排除：若金标文档不在 `corpus_version`，转为 `corpus.missing_evidence`；若检索 span 失败，转为工具/执行故障。
- 定位：召回器、过滤条件、查询改写、租户/权限过滤、K 或索引新鲜度。
- 建议：审计 query rewrite 与 filter；扩大候选 K；按检索器分别跑 Recall；确认文档 ID 对齐和索引时间。
- 严重性：answerable 用例的核心事实完全缺失为 high；只缺补充事实为 medium。

### D02 语料缺失 `corpus.missing_evidence`

- 症状：金标 `doc_id/content_hash` 在运行锁定的语料快照中不存在或版本不一致。
- 强证据：语料清单查询为 absent，或文档入库/权限 trace 明确失败。
- 排除：不能因为 Recall 为 0 就推断语料缺失。
- 建议：修复摄取、权限和增量索引；更新过期金标时必须发布新数据集版本。

### D03 Chunk 粒度不当 `chunk.granularity_suspected`

该规则分为两种子型，默认只标记 `suspected`，必须通过切分 A/B 才能确认。

**过小/过碎**：

- 证据组合：文档级 Recall 高、Chunk 级 Recall 或 Context Recall 低；同一 required fact 的支持 span 跨多个相邻 Chunk；候选中出现大量同文档相邻片段；单 Chunk 缺少指代对象或表头。
- 建议：增加窗口/overlap，做结构化切分或父子 Chunk 检索，并比较事实覆盖与 token 成本。

**过大/噪声多**：

- 证据组合：Recall/Context Recall 高但 Context Precision 低；相关 span 占 Chunk token 比例低；上下文频繁截断；大 Chunk 挤掉其他必需证据。
- 建议：按标题/段落/表格边界切分，缩小 Chunk，Rerank 句段或压缩上下文。

### D04 Embedding 不匹配 `retrieval.embedding_mismatch_suspected`

- 症状：向量召回漏掉金标，而 BM25/关键词或人工检索能稳定命中；退化集中于特定语言、术语、代码、表格或新领域切片。
- 强证据：同一候选规模下 vector Recall 显著低于 lexical Recall，且查询改写/过滤与索引状态正常。
- 辅助证据：相关与不相关样本的相似度分布高度重叠；更换领域 Embedding 的离线 A/B 恢复 Recall。
- 排除：索引未更新、维度/归一化配置错误应归为索引配置故障；不能用“向量分数低”单独定性。
- 建议：建立 hard negative；按切片 A/B Embedding；检查 query/document 前缀、语言归一化与混合检索。

### D05 Rerank 无效 `rerank.no_gain_or_regression`

- 症状：金标证据出现在初始候选池，但 Rerank 后跌出 K，或 MRR/NDCG 不升反降。
- 计算证据：保存每个相关项的 `rank_before`、`rank_after` 和 `delta`; 批次级比较 `ΔMRR`、`ΔNDCG@K`、`ΔRecall@K` 及置信区间。
- 确认：同一候选集上禁用 Rerank 的成对对照优于启用版本，且差异超过配置的实际意义阈值。
- 定位：Reranker 领域不匹配、输入截断、query-document 拼接错误、分数方向/排序实现错误。
- 建议：先检查 rank 和 score 方向；记录模型输入；调大 Rerank 候选窗口；用 hard negative 微调或回滚。

### D06 上下文污染 `context.pollution`

- 症状：Recall 和 Context Recall 可接受，但 Context Precision 低；最终窗口含重复、矛盾、过期或弱相关内容。
- 强证据：回答中的错误声明可追溯到某个 distractor；或冲突来源没有新鲜度/权威性排序。
- 辅助证据：移除可疑上下文的反事实运行提升 Faithfulness/Answer Relevancy。
- 定位：去重、Rerank、来源权威性、时间过滤、上下文打包和 token 预算。
- 建议：去重近似 Chunk；按来源与新鲜度加权；过滤低 usefulness 项；显式标注冲突并要求模型说明。

### D07 Prompt 约束弱 `generation.prompt_constraint_weak`

- 症状：Context Recall 高，回答相关，但 Faithfulness 或引用覆盖率低；回答包含上下文之外的扩写，且格式/引用要求未被遵守。
- 强证据：相同模型和上下文下，增强“仅依据证据、无证据则拒答、逐声明引用”约束的对照运行显著改善。
- 与幻觉区分：未做 Prompt 对照时只能标记 `suspected`；若明确约束已存在且稳定违反，可同时触发模型幻觉规则。
- 建议：结构化输出、声明级引用、冲突处理和拒答条件；把关键约束放到高优先级消息；增加 few-shot 反例。

### D08 模型幻觉 `generation.hallucination`

- 症状：一个或多个可验证声明为 `unsupported` 或 `contradicted`，Faithfulness 低。
- 高置信条件：回答所需的正确证据已完整进入上下文；Prompt 约束明确；声明仍与证据冲突或凭空出现。
- 降低置信条件：Context Recall 低、上下文冲突未处理、judge 证据不足，此时优先报告上游问题。
- 建议：更换/校准生成模型；降低自由度；强制引用后验证；生成后做声明级校验，不通过则拒答或重生成。

### D09 引用失败 `citation.invalid_or_unsupported`

- 症状：引用解析失败、目标不存在、引用与声明不相邻、目标不支持声明，或 Citation Coverage 低。
- 定位：输出格式、引用 ID 映射、上下文编号漂移、生成模型“装饰性引用”。
- 建议：只向模型暴露稳定的 context ID；使用结构化 citation 数组；服务端验证 target；前端突出 unsupported 引用。

### D10 拒答错误 `generation.refusal_error`

- 误拒答：`answerable=true` 且 Context Recall 足够，但模型拒答。
- 漏拒答：`answerable=false`、没有充分证据，但模型给出事实性答案。
- 建议：把检索置信、证据完整性和风险等级输入拒答策略；分开校准可回答与不可回答阈值。

### D11 工具/链路失败 `execution.component_failure`

- 触发：任一必需 span 为 `error/timeout/cancelled`，响应解析失败，或预期 stage 完全缺失。
- 证据：`trace_id`、`span_id`、组件、错误码、重试次数、上游/下游状态。
- 规则：执行故障优先级高于质量低分；受影响的质量指标标为 `error` 或降低诊断置信度，不能当 0 分参与平均。
- 建议：按错误码配置重试/熔断；监控错误率；保留脱敏输入和依赖版本以复现。

### D12 性能或成本回归 `operation.regression`

- 触发：在同一 case 集合上，候选版本的阶段 p95、超时率或单位成功回答成本超过基线配置阈值，且质量收益不足以满足发布策略。
- 证据：成对 delta、bootstrap 置信区间、关键路径 span、token/调用次数变化。
- 建议：调整 K、Rerank 窗口、上下文压缩、缓存和模型路由；用质量-成本 Pareto 图决策。

## 4. 多故障归因和优先级

一个用例可命中多条规则。按下列原则排序，而不是强行只给一个根因：

1. `execution/data` 高于 `retrieval`，`retrieval` 高于 `context`，`context` 高于 `generation`。
2. 有直接 trace/ID 证据的 `confirmed` 高于只有指标组合的 `suspected`。
3. 下游规则保留，但若依赖上游输入不完整则降低 confidence，并在 `blocked_by_rule_ids` 中引用上游规则。
4. 批次诊断必须提供受影响 case 数和切片集中度；零散单例不得推断全局组件故障。

建议严重性：核心答案错误、权限越界、不可回答仍编造为 `critical/high`；答案不完整、排名回退为 `medium`；格式与轻微成本波动为 `low`。最终映射由业务 profile 配置。

## 5. 规则引擎接口

规则定义建议采用版本化 YAML/JSON，计算节点只读规范化特征：

```yaml
id: rerank.no_gain_or_regression
version: 1.0.0
scope: [case, run]
requires:
  - retrieval.pre_rerank
  - retrieval.post_rerank
  - labels.relevance
when:
  all:
    - feature: relevant_present_pre_rerank
      op: eq
      value: true
    - feature: relevant_dropped_from_top_k
      op: eq
      value: true
emit:
  severity: high
  confidence_from: rerank_evidence_strength
```

规则结果不可覆盖人工结论。人工复核以独立 annotation 记录 `accepted/rejected/edited`、理由和 reviewer，用于后续标定规则准确率。

## 6. MVP 实现范围

MVP 先实现确定性、证据充分的规则：D01 检索缺失、D02 语料缺失、D05 Rerank 无效、D06 上下文污染、D09 引用失败、D11 链路失败。D03 Chunk、D04 Embedding、D07 Prompt 和 D08 幻觉保留为 `suspected`，通过 A/B 或声明级证据提升置信度。

上线规则自身也要评测：在人工标注故障集上报告每个 `rule_id` 的 precision、recall、误报案例和 `unknown` 比例，并按版本回归。没有真实标注集之前只交付 schema、规则和验证流程，不报告虚构准确率。
