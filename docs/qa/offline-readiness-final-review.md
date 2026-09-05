# WOR-61 离线阶段最终复核

复核日期：2026-09-05；复核人：Multica Helper。

结论：D01 独立复测证据与实现一致，PR #27 已合入 `work/wor-61-offline-readiness`。本阶段规定的可执行离线门槛已满足，提交用户验收；总 PR [#21](https://github.com/JichaoChen1123/RAGOps/pull/21) 目标为 main，合并仍由用户决定。

Docker Engine 不可用时，阶段要求允许记录真实错误、未测范围和复现命令。因此本次离线交付可以提交验收，但本机容器启动/卷重启没有通过证明。真实模型连接和真实问答效果也没有验证或评测。

## 提交与小队交付

| 任务 | 责任人 | 原提交 / 子 PR | 交付复核 |
| --- | --- | --- | --- |
| WOR-62 | 项目负责人 | `6518416c500fefd4330197d514e982146e1d4fb0` | 公共契约冻结并集成；平台已 done |
| WOR-63 | 后端平台工程师 | `32c3d922a087772849a3c4c67b624830fe63fb26` / [#23](https://github.com/JichaoChen1123/RAGOps/pull/23) | 后端实现与后续集成修正已交付；平台已 done |
| WOR-64 | 前端可视化工程师 | `0515cfb3cb93203a8c2613741d8fc0125bbee04d` / [#24](https://github.com/JichaoChen1123/RAGOps/pull/24) | API 模式、质量语义及报告已交付；平台已 done |
| WOR-65 | 测试质量工程师 | `a693bdb28e3ac915e961747789aca36868cdd77d` / [#22](https://github.com/JichaoChen1123/RAGOps/pull/22) | 离线测试和人工样本已交付；平台已 done |
| WOR-66 | 测试质量工程师 | `1807279f386f9ae59d2fce9e21a6d14e8b42dd66` / [#25](https://github.com/JichaoChen1123/RAGOps/pull/25) | 使用文档和原始失败证据已集成；历史失败结论保留 |
| WOR-67 | 前端可视化工程师 | `6d6c49d80c9daebf97eaf7faac72ea04b7c32ac9` / [#26](https://github.com/JichaoChen1123/RAGOps/pull/26) | D01 rule_id/key 修复已集成并通过独立复测 |
| WOR-68 | 测试质量工程师 | `7b93b02830cd0d8086a519b7428dd2c63d79369f` / [#27](https://github.com/JichaoChen1123/RAGOps/pull/27) | 新脚本、三阶段 JSON、5 张截图及复测报告已审核并集成 |

WOR-66/67/68 保持 `in_review` 供用户验收；负责人不自动将这些任务置为 done。WOR-61 在本次最终复核和 GitHub 文档交付完成后进入 `in_review`。

精确关系：

- WOR-66 旧失败受测基线：`10ef6b33c4373ee98f6e82e9a053212e5105252f`。
- WOR-68 新浏览器/前端受测基线：`1698150bf8a63dfd534b4c10a2fc64287cbcf993`，包含修复和原 QA 资产；脚本版本为 `wor-68-d01-retest-v1`。
- 本轮审核的 QA 提交：`7b93b02830cd0d8086a519b7428dd2c63d79369f`。
- PR #27 合并提交：`2b9a0c5b6497c20582932655536bf5da1935b146`，目标为阶段分支；Git tree 与上述 QA 提交相同。
- 本文及阶段状态说明是合并后的文档交付；其提交由总 PR 的提交记录标识，不能据此重新归属浏览器实测 SHA。
- main 核对为 `dcb41b3034a232d47b94a3e5aaa8f17ab07288c4`。

## 证据审核与门槛

| 范围 | 证据与审核结果 |
| --- | --- |
| A01–A08 后端/评测/契约 | Git 比较旧失败 SHA 与 QA 提交，`backend/`、`tests/backend/`、`tests/evaluation/` 和冻结契约无差异。继承 WOR-66 的 109 项、32 项定向测试及 90.69% 分支覆盖率，明确归属旧 SHA |
| 新基线前端 | WOR-68 在 `1698150b...` 实测 typecheck、43 项 Vitest 和 production build，均退出 0；本轮审核未重复执行这些命令 |
| A09 浏览器 | 三个独立 JSON 与累计 state 逐项一致，退出码均为 0。创建/重启当前 DOM 和 API 均含三条真实 rule_id，主诊断分布均为 `retrieval.missing_evidence × 12` |
| 持久化与质量语义 | 创建/重启的任务、样本、报告 ID 和本次回答一致；执行成功、质量未评估、未知分数并存；参考/历史 null/本次回答、provided 上下文、引用空态与未知 Token 一致 |
| 断连 | 独立证据为 HTTP 502、错误与重试入口、无 fixture fallback。仅断连阶段记录 8 条预期 502 console error；前两阶段 console error 为 0，全部阶段 duplicate-key 为 0 |
| 截图 | 实际查看全部 5 张新 PNG：数据集与断连为 1440×900，报告为 1440×2020，重启诊断为 1440×1686，移动诊断为 390×2613。长图来自 1440×900 / 390×844 视口的 full-page 截图，页面内容与 JSON 相符 |
| 历史保留 | 逐个比较原 QA 提交的 6 份截图/JSON blob，全部未变；原失败报告仍单独标为历史证据 |
| 网络与凭据 | 三阶段 JSON 的外部请求均为空且 host 仅为本机；构建/日志三种凭据哨兵匹配 0、端口清理记录引用 WOR-68 的执行报告，本轮没有重建这些日志 |
| A10 | 本轮仓库/离线资产/WOR-49/WOR-55/脚本语法门禁通过；Docker 环境限制如实保留 |

脚本审核确认：读取 Git HEAD 并可校验预期 SHA；create 拒绝复用已有 state；restart 重新采集 DOM/API；三阶段分别写结果，保留累计失败；非本机请求、重复 key、语义失败及非断连 console error 仍触发非零退出。没有放宽生产语义或修改后端实现。

完整 QA 报告、机器证据和截图链接见 [独立验收记录](offline-readiness-acceptance.md)。本轮是负责人审核与集成，不冒充第二次浏览器或后端实测。

## 本轮实际检查

在 QA 提交 `7b93b02...` 的干净检出执行以下命令，退出码均为 0：

```powershell
python scripts/validate_repository.py
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/validate-wor-49.ps1 -RepoRoot .
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/validate-wor-55.ps1 -RepoRoot .
node --check frontend/scripts/offline-readiness-browser.mjs
git diff --check 1698150bf8a63dfd534b4c10a2fc64287cbcf993 HEAD
```

仓库计数为 28 Markdown、13 JSON、5 JSONL、2 YAML；fixture oracle 为 6/9/8。这是本轮干净检出的实测计数，未复现 QA 工作目录中的 40/18 计数，也不把该数字作为固定仓库总量。新增本文后的文档门禁再次通过，计数为 29 Markdown、13 JSON、5 JSONL、2 YAML。

另执行 Git 祖先、后端/契约差异、历史 blob、JSON 跨阶段一致性及 PNG 签名/尺寸检查，全部通过。GitHub PR #27 的四项检查已完成且为 SUCCESS：[CI run](https://github.com/JichaoChen1123/RAGOps/actions/runs/33962480975)。总 PR 新提交的 CI 独立触发，按其当前 head 查看，不沿用旧 head 的绿灯。

## 启动、接口、迁移与后续验证

- [快速启动](../quickstart.md) 提供 Windows PowerShell 的无 Docker 后端、前端 API 模式及配置步骤；默认执行器为 mock，模型外部调用开关为 false。
- [冻结契约](../architecture/model-execution-contract.md) 定义 provider-neutral 请求/响应/错误、配置公开字段、2.0 样本/运行/报告及兼容行为。超时、重试上限和敏感信息只由后端处理。
- [迁移与开发说明](../development.md) 和验收记录说明 `0001_mvp_baseline -> 0002_model_execution_contract` 幂等升级；保留旧数据/报告，不能删库替代迁移。
- [离线复现入口](../../tests/acceptance/offline-readiness/README.md) 提供本地 3 样本 API/SQLite 重启和 Docker 隔离闭环命令；[浏览器检查表](../../tests/acceptance/offline-readiness/browser-checklist.md) 规定全新 state 及三阶段顺序。

WOR-68 执行 `docker compose config --quiet` 退出 0；`docker info --format '{{json .ServerVersion}}'` 因 `dockerDesktopLinuxEngine` 命名管道不存在退出 1。本轮没有安装、启动或登录 Docker。已有可用 Engine 的 Windows 环境可按以下步骤补测：

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
docker compose config --quiet
powershell -NoProfile -ExecutionPolicy Bypass -File tests/acceptance/offline-readiness/run-docker-loop.ps1 -RepoRoot .
```

远端 Docker 检查只构建镜像，不验证本机容器和卷重启。真实接入另需用户授权的提供方、模型、后端鉴权配置、超时/限流/预算、合法数据来源与版本/标签质量，之后单独开展受控连接与问答质量评测。本阶段不请求这些凭据。

Codex 仍仅为 provider-neutral 工厂/能力接口的未来扩展点；入口适用性、账号授权、权限/额度、结构化输出、取消/超时/并发和 Token 用量均留待届时官方文档及受控实验确认。本阶段未实现或验证账号接入。

| 代码已实现 | 离线测试通过 | 真实连接已验证 |
| --- | --- | --- |
| 适配器、配置安全门、执行/结果存储、版本化数据与幂等迁移、前端语义及 D01 修复已集成 | 规定的可执行离线门槛通过，负责人审核完成；本机 Docker 容器/卷重启明确未测 | **未执行，按范围禁止**；真实问答效果未评测 |
