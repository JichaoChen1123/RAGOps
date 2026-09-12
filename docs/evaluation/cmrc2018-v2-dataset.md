## CMRC2018 v2 调试与保留验收集

派生文件位于 `data/CMRC2018/`：

- `cmrc2018_debug20_v2.jsonl`：20 条，SHA-256 `189965ec0c0da2fae4fd85a90ce94b95f1ba7721085d29c67113a68626943040`。
- `cmrc2018_holdout30_v2.jsonl`：30 条，SHA-256 `3e11960cfdb64860609997b32d51b158908a101a0ebe40a42ddb981442b36a7c`。

输入为 [CMRC2018 官方 dev 集](https://github.com/ymcui/cmrc2018/blob/master/squad-style-data/cmrc2018_dev.json)，固定随机种子为 `20260912`。使用 `scripts/convert_cmrc2018.py` 可重建这两份文件：

```powershell
python -X utf8 scripts/convert_cmrc2018.py --input W:\RAGOPS\RAGOps\data\CMRC2018\cmrc2018_dev.json --exclude W:\RAGOPS\recovery\cmrc2018-materials-20260912\cmrc2018_legacy_job_01a07f6f_samples.jsonl --output-dir data/CMRC2018 --seed 20260912
```

转换先排除恢复 JSONL 中的 10 个问题及其完整段落原文；再以完整 CMRC 段落原文分组、以种子稳定打乱，并且仅将完整组放入单一分区。此次选择 15 个原文组：调试集与保留集之间没有原文交集，问题和官方 ID 均不重复。

每条是 `schema_version: "2.0"`：完整官方段落仅位于 `contexts` 且 `origin=provided`；官方问题 ID 记录于 `metadata.source_id`，文章/段落来源也保留于 metadata。`labels.reference_answer` 为第一个有效官方标注，所有可在该完整段落精确定位的官方参考答案按现有多参考答案约定保留在 `metadata.reference_answers`。不含模型输入答案、模型输出或历史回答。

转换器在写入前会校验样本数、必填 v2 字段、问题/ID 唯一性、非空上下文、答案定位、旧样本排除和跨集原文隔离。附带单元测试覆盖稳定输出与这些分组/标签性质；50 条生成样本也已通过后端 `DatasetSampleInput` 的 v2 校验。
