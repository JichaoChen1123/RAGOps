# 离线基础验收入口

这里提供阶段 2 可运行的资产自检，以及阶段 3 使用的本地 API、重启持久化、浏览器和 Docker 闭环脚本。所有任务固定使用 `mock` 适配器；脚本不会读取或验证真实模型凭据。

## 阶段 2

```powershell
pwsh -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
uv run --project backend pytest -c backend/pyproject.toml tests/backend/test_offline_contract_acceptance.py -q
```

第一条只验证人工样本和错误 oracle。第二条执行真实 FastAPI、SQLite 和内存 `httpx.MockTransport` 行为，不是源码字符串检查。

## 阶段 3

无 Docker 的本地后端和重启持久化：

```powershell
pwsh -File tests/acceptance/offline-readiness/run-local-restart.ps1 -RepoRoot .
```

连接已经启动的后端执行一次 API 闭环：

```powershell
pwsh -File tests/acceptance/offline-readiness/invoke-api-loop.ps1 `
  -BaseUrl http://127.0.0.1:8000 `
  -StatePath ./offline-api-state.json
```

Docker 隔离闭环：

```powershell
pwsh -File tests/acceptance/offline-readiness/run-docker-loop.ps1 -RepoRoot .
```

真实浏览器检查见 [浏览器检查表](browser-checklist.md)。浏览器脚本和截图只能补充 API 闭环；不得用截图代替 `invoke-api-loop.ps1` 的创建、导入、发布、运行、报告和导出断言。

## 证据要求

每次执行记录提交 SHA、命令、退出码、通过/失败数、SQLite 状态文件和未验证项。真实提供方连接与真实问答质量在本阶段必须记录为“未执行，按范围禁止”。
