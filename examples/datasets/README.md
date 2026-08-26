# RAG 评测数据集格式

本目录提供 RAGOps 的 JSONL 交换格式：

- `rag_eval_case.schema.json`：JSON Schema Draft 2020-12，可校验每行记录。
- `rag_eval_sample.jsonl`：一条完整样例，数据仅用于说明结构，不代表实验结果。

## 使用方式

一个 JSONL 文件每行是一个独立 JSON 对象。推荐 UTF-8、LF 换行。导入时先按 schema 校验，再检查跨记录唯一性和业务约束。

```bash
python -X utf8 -m jsonschema -i examples/datasets/rag_eval_sample.jsonl examples/datasets/rag_eval_case.schema.json
```

常见 JSON Schema CLI 不能直接把 JSONL 当 JSON 数组；生产导入器应逐行解析和校验。上面的命令只适合把单行样例临时作为一个 JSON 文件时使用。

## 顶层结构

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 交换格式版本；发生破坏性变更时升级主版本 |
| `case` | 稳定测试输入、期望答案、必需事实、金标证据和切片标签 |
| `run` | 某配置的一次实际检索、上下文、回答、trace 和 usage |
| `evaluation` | 可选评分和诊断；重评分时可单独写后端结果表 |

### 关键约束

- `case.case_id` 在同一数据集版本中唯一；相同测试用例跨运行保持不变。
- `run.run_id + case.case_id` 唯一。
- `gold_evidence` 可以只标文档，也可以精确到 Chunk/span；`relevance_grade >= 2` 参与二值相关指标。
- `retrieval.candidates[].stage` 区分原始候选和 Rerank 结果；每个 stage 的 rank 从 1 连续递增。
- `context.items` 必须是实际发给模型的文本顺序，不能用检索候选代替。
- `response.citations[].target_id` 必须能解析到本次上下文或白名单来源；解析结果由评测器写回。
- `metric_results[].status` 为 `ok` 时才允许有数值；输入缺失用 `not_applicable`，计算失败用 `error`。
- 样例中的分数只是结构示意，不是平台基准、承诺或真实实验结果。

## 数据制作流程

1. 从真实任务分层采样问题，去除个人信息和访问凭证。
2. 标注 `answerable`、参考答案和最小 `required_facts`。
3. 在锁定的 `corpus_version` 上标注金标文档/Chunk/span 与 0～3 相关性。
4. 双人复核高风险、不可回答和冲突来源样本；保留标注版本和争议说明。
5. 按语言、问题类型、业务线、答案新鲜度和难度写 `slice_tags`。
6. 发布不可变 `dataset_version` 和内容哈希。修订标签时创建新版本，不静默覆盖。

## 最小数据集与完整运行记录

只制作测试集时可以省略 `run` 和 `evaluation`，但 `case` 必须包含问题、`answerable`、参考答案/期望动作、required facts 和金标证据。执行后由平台补齐运行及评分字段。

为降低存储风险，生产环境可用 `content_ref + content_hash` 替代大段正文；导出给人工复核时再按权限解析。任何来源 URI 都不能绕过原系统的租户和权限检查。
