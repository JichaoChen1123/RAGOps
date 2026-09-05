# 离线接入验收样本

本目录只包含人工构造数据和内存 HTTP 响应，不含真实用户数据、凭据或提供方地址。

| 文件 | 用途 |
| --- | --- |
| `valid-v2.jsonl` | 2.0 合法样本、标签隔离、给定上下文及可空字段 |
| `legacy-v1.jsonl` | 1.0 兼容导入和 `legacy_unknown` 上下文 |
| `invalid-v2.json` | 空白、null、混用字段、关系错误、未知版本和重复 ID |
| `provider-responses.json` | A01/A04 的成功、鉴权、限流、5xx 和异常响应脚本 |
| `legacy-v1.sql` | A08 旧 SQLite 数据库的最小可复现建库脚本 |

所有值均为合成值。`SENTINEL_` 前缀专用于证明标签、历史输出和 metadata 不进入模型请求；它不是凭据。

结构自检：

```powershell
pwsh -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
```

行为验收：

```powershell
uv run --project backend pytest -c backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py -q
```

行为测试面向冻结的 2.0 契约。后端阶段 2 实现未集成时失败是预期信号，不得删除失败用例或标记 skip。
