# Windows Codex ChatGPT 主机桥接

本指南用于在 Windows 主机运行官方 Codex App Server，并让 Docker 中的 RAGOps 后端通过
`host.docker.internal` 使用固定 HTTP 契约访问它。Codex 登录凭据始终留在 Windows 主机；不要复制
`auth.json`、Cookie、Token 或 API Key 到仓库、镜像或容器。

截至 2026-09-06，本实现依据 Codex CLI `0.153.4` 生成的 App Server JSON Schema 完成离线验证。
官方文档说明 App Server 使用省略 `jsonrpc` 字段的 JSON-RPC 2.0，stdio 传输为 JSONL，并要求先完成
`initialize` / `initialized` 握手。协议和 CLI 仍可能演进，升级后应先运行本页的离线测试：

- [Codex App Server 官方文档](https://developers.openai.com/codex/app-server)
- [Codex 配置参考](https://developers.openai.com/codex/config-reference)
- [Codex 身份验证](https://developers.openai.com/codex/auth)

## 安全架构

```text
Docker backend
  -> http://host.docker.internal:8765/v1/* + Bearer token
Windows RAGOps bridge (single worker, concurrency 1)
  -> one fresh `codex app-server --stdio` process and ephemeral thread per sample
Codex App Server
  -> existing Windows ChatGPT OAuth session
```

桥接具有以下硬约束：

- 所有 HTTP 路由都要求 Bearer Token；Token 至少 32 字节且应由 CSPRNG 生成。
- 默认只监听 `127.0.0.1`。监听 `0.0.0.0` 等非 loopback 地址必须同时传
  `--allow-non-loopback`；这是 Docker Desktop 访问主机服务所需的显式风险确认。
- HTTP 请求只接受 `question`、按 position 排序的 `context`、`prompt` 和 `model`。额外字段直接
  返回 `422`，因此不能传入命令、工作目录、Codex 配置、label、metadata、参考答案或历史答案。
- 每个样本创建新的空临时目录、App Server 进程和 `ephemeral` thread，固定
  `approvalPolicy=never`、`readOnly`、`networkAccess=false`，并验证 App Server 回传的策略。
- 进程与 thread 两层固定关闭 shell、web、MCP、apps、plugins、skills、memory、browser、image、
  hooks 和 multi-agent 等能力；外部请求不能覆盖这些设置。
- App Server 子进程环境会移除所有 `RAGOPS_*` 变量及常见模型 API Key 变量，桥接 Bearer Token 不会
  传给 Codex 子进程。
- `instructionSources` 必须为空。任何非空值都会在 `turn/start` 前失败。
- 只采纳 `item/completed` 中 `phase=final_answer` 的唯一 agent message。进度、delta、plan 和
  reasoning 被忽略；任何工具项、审批/输入请求或未知控制事件都会触发 `turn/interrupt` 并失败。
- 桥接不自动重提 `turn/start`。超时会 interrupt 当前 turn，避免由桥接重复消耗额度。
- `/v1/status` 仅调用 `account/read`、`model/list`、`account/rateLimits/read`，不生成内容；响应不返回
  email、account ID、余额、reset credit ID、OAuth Token 或原始 App Server 错误文本。

## 固定 HTTP 契约

`POST /v1/generate` 请求：

```json
{
  "question": "审计日志保留多久？",
  "context": [
    {"position": 1, "text": "企业版审计日志默认保留 180 天。"}
  ],
  "prompt": "只依据给定上下文回答。",
  "model": "从 /v1/status 返回的模型 ID"
}
```

成功响应与后端 `ModelResponse` 对齐：

```json
{
  "answer": "企业版审计日志默认保留 180 天。",
  "actual_model": "模型 ID 或 null",
  "finish_reason": null,
  "latency_ms": 1234,
  "usage": {"input_tokens": 42, "output_tokens": 12, "total_tokens": 54},
  "provider_request_id": null,
  "is_mock": false
}
```

桥接没有可由请求设置的 temperature、top_p、max tokens、stop、seed、cwd、命令或配置字段。
后端应在调用前明确拒绝 Codex 通道不支持的生成参数，不得静默丢弃或回退到其他通道。

## PowerShell 启动步骤

以下命令必须由用户在 Windows 本机执行。本仓库的自动测试不会登录账号或调用真实模型。

1. 检查 Codex CLI。桥接启动时还会强制要求 `0.153.4` 或更高版本。

   ```powershell
   codex --version
   codex app-server --help
   ```

2. 在 Windows 主机完成官方 ChatGPT OAuth 登录并检查状态。

   ```powershell
   codex login
   codex login status
   ```

3. 在 PowerShell A 生成临时高熵 Token。不要把输出写入 `.env`、命令历史或聊天记录。下列命令把
   Token 临时放入进程环境与剪贴板，便于 PowerShell B 读取；B 读取后应立即清空剪贴板。

   ```powershell
   $tokenBytes = New-Object byte[] 32
   $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
   try { $rng.GetBytes($tokenBytes) } finally { $rng.Dispose() }
   $env:RAGOPS_CODEX_BRIDGE_TOKEN = [Convert]::ToBase64String($tokenBytes)
   Set-Clipboard -Value $env:RAGOPS_CODEX_BRIDGE_TOKEN
   ```

4. 仍在 PowerShell A，从仓库根目录安装锁定依赖并前台启动桥接。Docker 需要非 loopback 监听；请用
   Windows 防火墙限制该端口只允许 Docker Desktop 虚拟网络，不要暴露到公共网络。

   ```powershell
   uv sync --project backend --extra dev --frozen
   uv run --project backend ragops codex-bridge `
     --host 0.0.0.0 `
     --port 8765 `
     --allow-non-loopback `
     --turn-timeout-seconds 120
   ```

5. 打开 PowerShell B，从剪贴板读取同一 Token，然后立即清空剪贴板。状态检查不会调用模型。

   ```powershell
   $env:RAGOPS_CODEX_BRIDGE_TOKEN = Get-Clipboard
   Set-Clipboard -Value ''
   $headers = @{ Authorization = "Bearer $env:RAGOPS_CODEX_BRIDGE_TOKEN" }
   Invoke-RestMethod -Uri 'http://127.0.0.1:8765/v1/status' -Headers $headers
   ```

6. 在 PowerShell B 启动 Docker 集成。`docker-compose.yml` 默认把容器侧 URL 设置为
   `http://host.docker.internal:8765`。

   ```powershell
   $env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'codex_chatgpt'
   $env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'true'
   $env:RAGOPS_CODEX_BRIDGE_BASE_URL = 'http://host.docker.internal:8765'
   docker compose up --build
   ```

7. 完成用户授权的单样本真实验收后，先用 `Ctrl+C` 停止 Docker 和 PowerShell A 中的桥接，再退出
   Codex 登录并清除当前 PowerShell 的 Token。

   ```powershell
   codex logout
   Remove-Item Env:RAGOPS_CODEX_BRIDGE_TOKEN -ErrorAction SilentlyContinue
   ```

## 恢复安全的 mock 模式

发生桥接错误、额度不足或完成真实验收后，在 PowerShell B 执行：

```powershell
docker compose down
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
Remove-Item Env:RAGOPS_CODEX_BRIDGE_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:RAGOPS_CODEX_BRIDGE_TOKEN -ErrorAction SilentlyContinue
docker compose up --build
```

mock 是默认值。Codex 不可用时，运行中的真实任务也不得自动回退为 mock；必须由用户显式切换并创建
新的验收任务，以免报告把真实结果与模拟结果混为一谈。

## 离线测试

替身进程覆盖初始化、状态 RPC、异步通知、最终消息、usage、model reroute、协议错误、工具事件、
instructionSources、超时与 interrupt。它不读取 Codex 登录文件，也不触发真实模型。

```powershell
uv run --project backend --extra dev pytest -c backend/pyproject.toml `
  tests/backend/test_codex_bridge.py -q
```

## 无法完全证明的隔离边界

这些限制必须保留在验收报告中，不能把“代码已实现”表述为“系统级隔离已证明”：

- App Server 的 `readOnly`/`networkAccess=false` 是 Codex 执行策略，不是独立 Windows 用户、VM 或
  容器级机密隔离。与用户同一 OS 身份运行的进程仍不应被视为无法读取所有已知主机路径。
- `instructionSources=[]` 只证明协议报告的 instruction file 列表为空，不证明服务端不存在内建指令。
- 禁用工具并在事件流中 fail-closed 能阻止桥接接受工具结果，但事件检测发生在 App Server 已报告事件
  之后；它不能替代 OS 审计或形式化证明。
- `ephemeral=true` 避免把该 thread 写成普通持久会话，但不证明上游服务没有按其数据政策记录请求。
- Docker 到 `0.0.0.0:8765` 使用明文 HTTP。Bearer Token 仅提供应用认证，不提供传输加密；必须依靠
  本机防火墙和可信 Docker 虚拟网络。跨主机使用需要另加 TLS 反向代理，当前实现不覆盖。
- 额度、可用模型和 actual model 以 App Server 当次返回为准；缺失值保持 `null`，不能从请求模型名、
  ChatGPT 套餐名称或历史结果推断。

因此当前仓库状态应分别记录为：桥接代码已实现、离线替身测试通过、真实 ChatGPT 连接未验证。只有
用户完成上述本机登录和单样本验收后，最后一项才能改为已验证。
