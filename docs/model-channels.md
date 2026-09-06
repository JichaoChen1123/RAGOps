# 模型双通道接入与验收

本页说明 RAGOps 的三个执行通道，以及 Windows PowerShell + Docker Desktop 下的个人本机部署方式。

## 状态边界

| 通道 | 用途 | 凭据位置 | 当前验证方式 |
| --- | --- | --- | --- |
| `mock` | 离线开发与回归测试 | 无 | 自动化测试，不联网 |
| `codex_chatgpt` | 使用账号可用的 Codex 订阅权益 | Windows 主机上的桥接专用 Codex 登录存储 | 官方 Codex App Server，经认证本机桥接 |
| `openai_compatible` | 一个可配置的 Chat Completions 提供方 | 后端 `.env` | 用户主动发起最小生成请求 |

`VITE_API_MODE=api` 只表示浏览器连接 RAGOps 后端。它不代表模型已经配置、登录或完成真实生成验证。

ChatGPT 账号通道不是通用 OpenAI API 余额，不保证无限调用，也不保证 ChatGPT 网页中的所有模型都可用。RAGOps 不抓取 Cookie、不读取或传输密码，也不要求复制 `auth.json`。认证、令牌刷新和退出登录均由 Codex 管理。官方参考：

- [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)

## 架构

```text
Browser
  -> RAGOps frontend
  -> RAGOps backend (Docker)
       -> mock adapter
       -> OpenAI-compatible Chat Completions provider
       -> authenticated host bridge
            -> Codex App Server (Windows host)
                 -> ChatGPT OAuth managed by Codex
```

Docker 容器不会自动拥有 Windows 主机的 Codex 登录状态。因此 `codex_chatgpt` 不在后端容器内读取登录文件，而是在 Windows 主机启动一个窄接口桥接服务。桥接只暴露固定的状态检查与问答请求，不接受任意命令、工作目录、Codex 配置或工具定义。

桥接安全约束：

- 所有模型端点要求至少 32 字符的 Bearer token；健康检查不执行 Codex。
- 默认仅监听 `127.0.0.1`；仅在显式使用 `-Docker` 时监听容器可达地址。
- 同一时间只执行一个 Codex 请求；每个样本新建独立临时会话。
- 审批为 `never`，沙箱为只读，网络关闭，动态工具、MCP、插件、应用、浏览器、计算机控制、多智能体、记忆和 shell 功能关闭。
- Codex 子进程不会继承 `RAGOPS_*`、`OPENAI_API_KEY` 等模型服务密钥环境变量。
- Codex 子进程强制使用 `%LOCALAPPDATA%\RAGOps\codex-bridge-home`，不读取日常 `%USERPROFILE%\.codex` 的 MCP、插件和项目配置。
- 只接收唯一且标记为 `final_answer` 的 `agentMessage` 结构化答案；工具类事件或未知控制事件会使本次运行失败。
- 每次生成使用一个新的临时空目录，结束后自动删除；目录中不放数据集、参考答案或业务仓库。
- 桥接会通过 `config/read` 和 `mcpServerStatus/list` 校验最终生效的配置层、禁用开关及 MCP 注册表，再校验 App Server 实际返回的工作目录、指令来源、审批策略、沙箱、联网、临时会话和模型。只检查发出的参数不算通过。

限制：当前 App Server 的线程契约可限制只读、联网和功能开关，但不能证明操作系统层面“只能读取这个空目录”。RAGOps 会在发现指令文件或工具事件时失败关闭；对隔离要求更高时，应把桥接放入单独 Windows 用户、虚拟机或受控专用运行环境。

## Windows 主机准备

在仓库根目录的 PowerShell 中检查 Codex，并为桥接专用目录完成官方 ChatGPT 登录：

```powershell
codex --version
.\scripts\manage_codex_bridge_login.ps1 -Action Status
.\scripts\manage_codex_bridge_login.ps1 -Action Login
.\scripts\manage_codex_bridge_login.ps1 -Action Status
```

桥接当前要求 Codex CLI `0.153.4` 或更高版本；启动脚本会再次检查版本，不满足时直接退出，不会尝试模型调用。

登录界面选择 ChatGPT 登录，不要选择 API Key。脚本只在 `%LOCALAPPDATA%\RAGOps\codex-bridge-home` 中运行官方登录流程，不复制日常认证文件，也不改变日常 Codex 的配置或登录。登录失效时重新运行 `-Action Login`；只退出桥接专用登录使用：

```powershell
.\scripts\manage_codex_bridge_login.ps1 -Action Logout
```

RAGOps 不会在启动、打开页面或读取状态时自动生成内容。

## 配置 ChatGPT 账号通道

先创建本地配置：

```powershell
Copy-Item .env.example .env
$token = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$token
```

把 `.env` 中以下项目设置为：

```dotenv
VITE_API_MODE=api
RAGOPS_MODEL_EXECUTION_ADAPTER=codex_chatgpt
RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=true
RAGOPS_CODEX_BRIDGE_URL=http://host.docker.internal:8765
RAGOPS_CODEX_BRIDGE_TOKEN=<上一步生成的随机 token>
RAGOPS_CODEX_DEFAULT_MODEL=
```

不要提交 `.env`。桥接 token 只是 RAGOps 本机组件之间的共享秘密，不是 ChatGPT 或 OpenAI 令牌。

终端 1 在 Windows 主机启动桥接：

```powershell
uv sync --project backend --extra dev --frozen
.\scripts\start_codex_bridge.ps1 -Docker
```

启动输出会显示桥接专用目录。每个 App Server 进程都将 `CODEX_HOME` 强制指向该目录，并在读取账号信息前验证有效配置中 `mcp_servers`、插件注册和相关功能开关均为空或关闭，且 MCP 运行注册表为空。验证失败不会调用模型。

`-Docker` 会监听 `0.0.0.0`，因为 Docker Desktop 通过 `host.docker.internal` 访问主机。必须保持 Windows Firewall 开启；不要在路由器映射端口 `8765`，也不要把它部署成共享或公网服务。

终端 2 启动 RAGOps：

```powershell
docker compose up --build
```

打开 `http://localhost:5173/projects/demo/evaluations`，新建任务并选择 `codex_chatgpt`：

1. 先点“检查登录”。该操作读取认证类型、可用模型和可查询到的额度状态，不生成回答。
2. 选择账号实际返回的模型，再点“真实小请求验证”。该操作会消耗一次账号可用的 Codex 权益。
3. 单条验证成功后，仅使用 1 条 CMRC 样本创建任务。
4. 检查报告中的通道、请求模型、实际返回模型、回答、延迟、usage 和请求 ID。提供方未返回的值必须显示未知。
5. 单条通过后再运行 10 条样本。
6. 运行 `docker compose restart`，确认历史任务仍存在；最近连接检查保存在进程内存中，后端重启后需要主动重验。

## 配置 OpenAI-compatible API 通道

当前只支持非流式 OpenAI Chat Completions 请求，不声称兼容 Responses API 或所有服务商。Base URL 是 API 根路径，通常已经包含 `/v1`；不要填写以 `/chat/completions` 结尾的完整接口地址。

```dotenv
VITE_API_MODE=api
RAGOPS_MODEL_EXECUTION_ADAPTER=openai_compatible
RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=true
RAGOPS_OPENAI_COMPAT_PROVIDER_NAME=Your provider
RAGOPS_OPENAI_COMPAT_BASE_URL=https://provider.example/v1
RAGOPS_OPENAI_COMPAT_AUTH_MODE=bearer
RAGOPS_OPENAI_COMPAT_API_KEY=<仅保存在本机 .env>
RAGOPS_OPENAI_COMPAT_DEFAULT_MODEL=<服务商模型 ID>
```

界面中的“付费小请求验证”会真实调用服务商，可能产生费用。认证失败不重试；限流、超时和服务端错误按后端上限重试。任何失败都不会自动切换到 Codex、另一个 API 或 mock。

如果服务商不需要鉴权，可显式设置 `RAGOPS_OPENAI_COMPAT_AUTH_MODE=none` 并留空 API Key。该模式只适合可信内网服务。

## 一条到十条样本验收

1. 保持外部调用关闭，运行后端、前端和 mock 测试，确认不联网。
2. 开启目标通道，只执行主动连接检查。
3. 创建仅含 1 条样本的数据集并发布。
4. 选择目标通道和模型创建任务，确认没有自动回退。
5. 检查样本模型输入只包含 Prompt、问题和本题上下文，不包含 `labels`、参考答案、`metadata` 或历史标准输出。
6. 检查任务执行状态与质量状态分开展示；未配置质量指标时保持“未评估”，不能显示 100 分。
7. 检查成功运行保存本次回答；失败运行保存安全错误码，不用参考答案补位。
8. 通过后再对 10 条 CMRC 样本重复执行。

## 常见错误

| 状态或错误 | 含义 | 处理 |
| --- | --- | --- |
| `CODEX_NOT_INSTALLED` | 主机找不到 Codex | 检查 `codex --version` 和 PATH，重启桥接 |
| `CODEX_CHATGPT_NOT_AUTHENTICATED` | 桥接专用目录未登录 | 运行 `manage_codex_bridge_login.ps1 -Action Login` |
| `CODEX_CHATGPT_WRONG_AUTH_MODE` | 桥接专用目录是 API Key 等非 ChatGPT 认证 | 用脚本退出后重新选择 ChatGPT 登录 |
| `PROVIDER_AUTHENTICATION_FAILED` | 登录失效或 API Key 被拒绝 | 重新登录或检查后端 `.env` |
| `CODEX_CHATGPT_USAGE_LIMITED` | 账号 Codex 权益当前受限 | 等待额度恢复；不会切换到付费 API |
| `PROVIDER_RATE_LIMITED` | 提供方限流 | 等待后重试；重试次数有上限 |
| `PROVIDER_TIMEOUT` | 超过总超时 | 检查桥接/服务商状态，必要时调整超时 |
| `CODEX_ISOLATION_VIOLATION` | 隔离证据缺失/不匹配，或出现禁止能力 | 根据界面中的 `reason_code` 和诊断 ID 查桥接日志；不接受本次答案 |
| `CODEX_PROTOCOL_INCOMPATIBLE` | App Server 返回了当前桥接未识别的协议事件 | 根据 `TURN_PROTOCOL_NOTIFICATION_UNRECOGNIZED` 及诊断 ID 核对本机 Schema；不要按工具违规处理 |

### 隔离诊断

桥接日志中的 `codex_bridge.protocol_stopped` 只记录诊断 ID、错误码、`reason_code`、协议 method、item 类型、阶段和必要关联 ID。它不会记录令牌、账号认证响应、Prompt、上下文、参考答案或推理内容。

主要原因码：

| `reason_code` | 含义 |
| --- | --- |
| `RPC_SERVER_REQUEST_DURING_RESPONSE` | 等待普通 RPC 响应时收到服务器反向请求 |
| `RPC_SERVER_REQUEST_DURING_TURN` | 生成期间收到服务器反向请求 |
| `THREAD_RESPONSE_FIELD_MISSING` | `thread/start` 缺少基础响应字段 |
| `THREAD_RESPONSE_FIELD_INVALID` | `thread/start` 基础响应字段类型错误 |
| `THREAD_SAFETY_FIELD_MISSING` | 无法获得必须验证的隔离字段 |
| `THREAD_SAFETY_FIELD_INVALID` | 隔离字段类型不符合协议 |
| `THREAD_DIRECTORY_INVALID` / `THREAD_DIRECTORY_MISMATCH` | 隔离目录无效或与临时目录不一致；日志只记录是否匹配 |
| `THREAD_PERMISSION_MISMATCH` | 审批、沙箱、网络或 ephemeral 权限不符合要求 |
| `THREAD_INSTRUCTION_SOURCES_PRESENT` | App Server 实际加载了额外指令文件 |
| `THREAD_MODEL_MISMATCH` | 实际线程模型与请求模型不一致，禁止自动回退 |
| `THREAD_ID_MISSING` | `thread/start` 未返回可关联的线程 ID |
| `MCP_SERVER_STARTUP_STATUS_OBSERVED` | 收到 MCP 服务启动状态通知，证明隔离环境仍尝试加载服务；不是工具调用 |
| `MCP_EFFECTIVE_CONFIG_UNVERIFIABLE` | `config/read` 缺少必须验证的 MCP、插件、功能开关或配置层字段 |
| `MCP_EFFECTIVE_CONFIG_NOT_EMPTY` | 最终生效配置仍包含 MCP 服务或插件配置 |
| `MCP_EFFECTIVE_FEATURE_NOT_DISABLED` | MCP/插件相关功能开关没有在最终配置中关闭 |
| `MCP_CONFIG_SOURCE_MISMATCH` | 最终用户配置层不属于桥接专用目录，或加载了项目配置层 |
| `MCP_SERVER_REGISTRY_UNVERIFIABLE` / `MCP_SERVER_REGISTRY_NOT_EMPTY` | MCP 注册表无法验证或仍存在已注册服务 |
| `MCP_TOOL_CALL_FORBIDDEN` | 检测到实际 MCP 工具调用或 MCP 工具条目 |
| `TURN_FORBIDDEN_ITEM_TYPE` / `TURN_FORBIDDEN_METHOD` | 检测到其他命令、文件、联网等禁止能力 |
| `TURN_PROTOCOL_NOTIFICATION_UNRECOGNIZED` | 未知通知；保持停止，但不宣称已调用工具 |

升级 Codex 后可在 Windows PowerShell 生成本机版本的官方协议 Schema：

```powershell
$schemaDir = Join-Path $env:TEMP "ragops-codex-schema"
New-Item -ItemType Directory -Path $schemaDir -Force | Out-Null
codex app-server generate-json-schema --experimental --out $schemaDir
Get-ChildItem -LiteralPath $schemaDir
```

当前实现按 `codex-cli 0.153.4` Schema 核对了 `ThreadStartResponse`、`ConfigReadResponse`、`ListMcpServerStatusResponse` 和 `ServerNotification`。`remoteControl/status/changed` 与 `configWarning` 只按精确事件名兼容；`mcpServer/startupStatus/updated` 单独诊断服务名、状态、failure reason 和 thread ID，但仍停止本次运行。其他未知事件继续 fail-closed，真实 MCP 工具调用继续拦截。

## 更新后只做一次真实验证

```powershell
git checkout main
git pull
.\scripts\manage_codex_bridge_login.ps1 -Action Status
```

如果显示未登录，只运行一次 `-Action Login`。然后关闭旧 Bridge 窗口，在终端 1 重新运行 `start_codex_bridge.ps1 -Docker`；终端 2 运行 `docker compose up --build`。网页先点“检查登录”，确认成功后只点一次“真实小请求验证”。失败时只提供新的 `reason_code` 和 `diagnostic_id`，不要连续重试，也不要发送登录文件或令牌。

## 恢复 mock

停止桥接，在 `.env` 中恢复：

```dotenv
VITE_API_MODE=api
RAGOPS_MODEL_EXECUTION_ADAPTER=mock
RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false
```

然后执行：

```powershell
docker compose up --build
```

这不会删除现有 `ragops-data` 数据卷。不要使用 `docker compose down --volumes`，除非明确要删除本地数据。
