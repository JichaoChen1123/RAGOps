# RAGOps 测试目录约定

当前仓库尚无应用实现和测试框架，本目录先定义落地结构，避免以占位测试制造“已通过”的假象。

后续实现进入仓库时，测试建议按以下结构提交：

```text
tests/
  unit/
    metrics/          # 读取 metric-cases.json 的纯函数测试
    validation/       # schema、边界和错误码
    state_machine/    # 合法/非法状态转换与幂等
  integration/
    api/              # OpenAPI 契约、数据库和分页筛选
    workers/          # 队列、重试、重复/乱序消息、恢复
  contract/
    frontend_backend/ # 前后端请求/响应兼容性
    providers/        # provider adapter 的固定响应契约
  e2e/                # fake provider 驱动的 P0 用户闭环
  performance/        # 有版本的容量基准，不在普通 PR 默认运行
```

测试 ID、输入、步骤和预期结果以 `docs/qa/test-plan.md` 为入口。固定夹具位于 `examples/eval-samples/`。任何真实 provider 测试必须与确定性测试分组，不能让网络或模型波动成为 PR 门禁的随机因素。

首批自动化实施顺序：

1. JSON/JSONL schema 与引用完整性校验。
2. `metric-cases.json` 的指标 oracle 单元测试。
3. 异步任务状态机和幂等单元测试。
4. 数据集、评测任务、报告和对比 API 集成测试。
5. AC-001 至 AC-008 的浏览器 E2E。

当前可执行的 fixture 自检：

```powershell
pwsh -File tests/fixtures/validate-fixtures.ps1
```

该脚本校验基线数量、ID 唯一性、rank 连续性、citation 引用和关键指标 oracle。它不替代后续 JSON Schema/OpenAPI 契约测试。

WOR-49 可见交互与模式边界契约自检：

```powershell
pwsh -File tests/acceptance/validate-wor-49.ps1
```

该命令只验证验收资产、Mock/API 双模式期望、写操作映射和 README 说明完整，不代表应用实现已经通过。实现进入仓库后，仍需执行 `docs/qa/wor-49-visible-interactions.md` 中列出的前端、后端与集成门禁。
