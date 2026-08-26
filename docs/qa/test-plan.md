# RAGOps MVP 测试计划、验收标准与质量门禁

## 1. 文档状态

- 对应 issue：`WOR-42`
- 版本：`0.1`
- 状态：测试设计基线，待产品、后端、算法和前端契约合并后校准
- 当前仓库基线：只有项目标题，尚无可执行实现、API 定义或 UI。因此本文记录的是验收契约和测试设计，不代表任何测试已经执行或通过。

本文覆盖从数据集导入、评测任务执行到报告、诊断和版本对比的 MVP 主流程。示例路由、状态名和性能阈值是用于驱动实现的候选契约；若后续设计文档给出不同定义，应在编码前统一更新本文和测试夹具。

## 2. 质量目标与范围

### 2.1 质量目标

1. 用户可用一份可复现的数据集完成“导入 → 运行 → 查看报告 → 定位失败样本 → 对比版本”的闭环。
2. 指标结果可由固定输入独立复算，边界值、空分母和缺失值不会被静默美化。
3. 异步任务状态单向、可追踪、可恢复；失败不会生成伪成功报告。
4. 页面在加载、空数据、部分数据、失败和权限异常时均给出明确状态。
5. PR 进入主分支前，契约、单元、集成和静态检查形成可重复的质量门禁。

### 2.2 测试范围

- 产品：数据集管理、评测配置、任务状态、评测报告、样本诊断、版本对比和趋势。
- 后端：输入校验、分页筛选、幂等、状态机、错误模型、持久化、并发和任务恢复。
- 算法：Recall@K、MRR@K、NDCG@K、Context Precision、Context Recall、Faithfulness、Answer Relevancy、引用命中率、延迟和成本。
- 前端：关键页面、筛选、深链、刷新恢复、空态、异常态、长文本和可访问性。
- 工程：夹具校验、单元/集成/E2E 分层、覆盖率、依赖与密钥扫描、可复现报告。

### 2.3 暂不纳入 MVP 阻断门禁

- 对真实第三方大模型分数做逐位相等断言；此类结果只做区间、漂移和人工抽检。
- 大规模分布式压测、跨地域容灾、计费结算和复杂租户权限。
- 未经产品确认的自动根因修复。诊断只给出证据和候选原因。

## 3. 测试前置与统一判定规则

### 3.1 环境

| 环境 | 外部依赖 | 数据 | 用途 |
| --- | --- | --- | --- |
| 单元测试 | 全部 stub/fake，固定随机种子 | `examples/eval-samples/metric-cases.json` | 公式、校验、状态转换 |
| 集成测试 | 临时数据库、队列和对象存储；模型/Embedding 使用确定性 fake | 有效和无效 JSONL | API、持久化、失败恢复 |
| E2E | 与生产同构的测试部署；默认 fake provider | `valid-samples.jsonl` | 用户闭环和页面状态 |
| 夜间评测 | 允许调用固定版本的真实 provider | 固定金标集，不含敏感信息 | 漂移、兼容性和性能趋势 |

每次执行必须记录：Git SHA、数据集校验和、schema 版本、服务版本、模型/Prompt/Embedding/Rerank 版本、随机种子、时间范围和失败用例列表。

### 3.2 统一规则

- 浮点比较默认绝对误差 `1e-6`；展示层允许四舍五入到 4 位，但 API 保留未格式化数值。
- 排名指标先按 `doc_id` 去重，保留第一次出现的排名；同一文档重复返回不得重复增加召回。
- `K` 必须为正整数；`K <= 0` 返回参数错误，不返回 0 分。
- 无 gold / 无可判定 claim 等空分母场景返回 `null` 并携带 `not_applicable` 原因，不得写成 0。
- Judge 类指标必须保存 judge 名称、版本、Prompt 版本和原始判定；确定性单测使用 stub judge。
- 时间统一为 UTC ISO 8601，耗时以毫秒整数存储，金额使用十进制定点值并带币种。
- 错误响应至少包含稳定的 `code`、可读 `message` 和 `request_id`；字段错误还包含 `details[].field`。
- 同一评测任务引用的数据、模型和配置必须在创建时形成不可变快照。

## 4. 产品验收矩阵

优先级：P0 阻断 MVP 发布；P1 必须在正式发布前完成或由负责人书面接受风险；P2 可进入后续迭代。

| ID | 级别 | 测试输入/前置 | 操作步骤 | 期望结果 |
| --- | --- | --- | --- | --- |
| AC-001 | P0 | `valid-samples.jsonl`，全新项目 | 创建数据集并导入文件，查看预览 | 导入成功且为 6 条；中文、引用和数组字段不丢失；页面显示 schema 版本、成功数、失败数和校验摘要 |
| AC-002 | P0 | `invalid-samples.jsonl` | 逐条提交 `input` 对象，再提交包含两条重复 ID 的批次 | 每条按夹具的 `expected_error` 拒绝；错误定位到行和字段；原子导入模式不留下半批数据 |
| AC-003 | P0 | 已导入有效数据集；确定性 fake provider | 创建评测，选择 Prompt/模型/Embedding/Rerank 版本并提交 | 仅创建一个任务；返回任务 ID 和配置快照；列表中状态为 `queued`；重复幂等键返回同一任务 |
| AC-004 | P0 | AC-003 的任务 | 启动 worker，观察任务从排队到结束，再刷新页面 | 合法状态为 `queued → running → succeeded`；进度不回退；刷新后状态保持；报告仅在完成后可用 |
| AC-005 | P0 | 成功任务和 `metric-cases.json` | 打开汇总报告，抽取至少 3 个样本独立复算 | 样本数、成功/失败数与任务一致；指标在 `1e-6` 内等于夹具；`null` 不展示为 0 |
| AC-006 | P0 | `rag-retrieval-miss-001` 等带预期诊断的样本 | 按失败类型筛选，打开样本诊断 | 筛选结果只包含匹配样本；展示问题、gold、检索上下文、答案、引用、指标证据和诊断原因；不只显示无证据标签 |
| AC-007 | P0 | 同一数据集的配置 A/B 两次成功评测 | 在版本对比中选择 A 为基线、B 为候选 | 样本集合和配置差异可见；绝对值、差值和改善/退化方向正确；不允许比较不兼容 schema 且不给提示 |
| AC-008 | P0 | 一个运行中任务和一个会失败的 provider stub | 分别取消任务、触发 provider 超时后重试 | 取消最终为 `cancelled` 且无成功报告；失败为 `failed` 并保留错误码；重试创建可追踪的新 attempt，不覆盖旧记录 |
| AC-009 | P1 | 空项目、空数据集、无匹配筛选结果 | 依次访问概览、数据集、任务和报告页面 | 每个页面给出针对性的空态、下一步入口和清除筛选方式；不显示无限 loading 或 500 堆栈 |
| AC-010 | P1 | 50 个上下文、万字答案、失效引用、含中文/emoji 文本 | 打开样本详情并切换上下文/引用 | 页面可展开收起且无明显卡死；失效引用醒目标记；文本不乱码、不溢出；复制内容与原始值一致 |
| AC-011 | P1 | 两个并发用户同时启动同一配置 | 同时发送创建请求并轮询列表 | 幂等键相同时只有一个逻辑任务；不同键可并行；任务进度和报告不串线 |
| AC-012 | P1 | 完成任务后重启 API、worker 和数据库连接 | 重启后打开原任务和报告 | 状态、配置快照、样本结果和报告仍存在；未完成任务按设计恢复或明确失败，不长期停在 `running` |
| AC-013 | P1 | 至少 3 个时间点的相同评测配置 | 打开趋势看板，切换指标和日期范围 | 趋势按执行完成时间排序；样本集变化有标识；tooltip、图例和表格数值一致 |
| AC-014 | P1 | 服务端返回 401/403/404/409/422/429/500 | 从相应页面触发请求 | UI 区分登录、权限、资源不存在、冲突、校验、限流和系统错误；保留 request ID，重试按钮只在安全场景出现 |

MVP 业务验收通过条件：AC-001 至 AC-008 全部通过；AC-009 至 AC-014 无未接受的高风险失败；不存在数据丢失、跨任务污染或错误指标。

## 5. API 测试矩阵

下表使用候选 `/api/v1` 路由表达资源语义。后端契约发布后，应以 OpenAPI 为真源生成契约测试，并建立“本表 ID → 最终 operationId”的映射。

| ID | 资源/候选操作 | 测试输入 | 操作 | 期望结果 |
| --- | --- | --- | --- | --- |
| API-001 | `POST /datasets` | 合法名称、schema 版本 | 创建两次不同名称数据集 | 201；ID 唯一；创建时间和版本存在；默认统计为 0 |
| API-002 | `POST /datasets` | 空名称、超长名称、未知字段、错误类型 | 参数化提交 | 422；稳定错误码；指出字段；不写数据库 |
| API-003 | `POST /datasets/{id}/samples:import` | 6 条有效 JSONL | 导入并读取详情 | 202/201；最终 `accepted=6,rejected=0`；原文本 UTF-8 无损 |
| API-004 | 同上 | 无效 envelope 中的各 `input` | 分别导入 | 422 或行级失败；错误码与夹具一致；行号从契约约定的基数开始且一致 |
| API-005 | 同上 | 一批含重复 `sample_id` | 原子模式导入 | 409/422；整批回滚；重试修正文件后可成功 |
| API-006 | `GET /datasets` | 25 个数据集 | 测试默认分页、边界页、非法 cursor/limit、名称筛选 | 顺序稳定、无重复/遗漏；非法分页 422；响应包含下一页游标或总数契约 |
| API-007 | `GET/DELETE /datasets/{id}` | 存在、不存在、被任务引用的数据集 | 查询和删除 | 存在返回 200；不存在 404；被引用时 409 或软删除，历史报告仍可读 |
| API-008 | `POST /evaluations` | 数据集、完整版本配置、`Idempotency-Key` | 首次与重复提交 | 首次 202；重复返回相同任务 ID；配置快照不可变 |
| API-009 | 同上 | 缺数据集、空数据集、未知模型、非法 K、冲突版本 | 参数化提交 | 404/409/422 按错误类型返回；不产生队列消息或脏任务 |
| API-010 | `GET /evaluations/{id}` | queued/running/succeeded/failed/cancelled 各任务 | 逐一查询 | 状态、进度、attempt、时间和错误字段符合状态；完成态不可回退 |
| API-011 | `GET /evaluations` | 多状态、多配置、多时间任务 | 组合筛选和分页 | AND/OR 语义符合 OpenAPI；稳定排序；未知筛选 422；跨项目数据不可见 |
| API-012 | `POST /evaluations/{id}:cancel` | queued、running、各终态任务 | 取消并重复取消 | queued/running 最终 cancelled；重复请求幂等；终态返回原状态或明确 409 |
| API-013 | `POST /evaluations/{id}:retry` | failed、cancelled、running 任务 | 发起重试 | failed 可新建 attempt 并关联来源；running 被拒绝；旧错误和旧结果不覆盖 |
| API-014 | worker 状态回写 | 重复、乱序、过期 attempt 的事件 | 按不同顺序投递 | 重复事件幂等；非法回退和旧 attempt 被拒绝/忽略并留审计日志 |
| API-015 | `GET /reports/{evaluation_id}` | 未完成、成功、失败、未知任务 | 查询报告 | 未完成 409/202，成功 200，失败不给伪报告，未知 404；汇总计数守恒 |
| API-016 | `GET /reports/{id}/samples` | metric 范围、诊断标签、全文、排序、分页 | 单项和组合查询 | 返回集合与条件一致；null 指标可单独筛选；排序中 null 位置稳定 |
| API-017 | `GET /reports/{id}/samples/{sample_id}` | 正常、长上下文、失效引用 | 查询样本详情 | 返回可定位的 context/chunk/claim；失效引用保留并标记，不被静默删除 |
| API-018 | `POST /comparisons` | 同 schema A/B、不同 schema A/B、缺失样本 | 创建比较 | 同 schema 成功；不兼容输入明确拒绝或标记；交集/并集口径在响应中声明 |
| API-019 | `GET /trends` | 多时间点、多配置、空范围 | 查询与聚合 | 顺序、聚合窗口和时区正确；空范围 200 + 空数组；不同样本集有覆盖率信息 |
| API-020 | 通用错误与追踪 | 模拟 provider 超时、队列不可用、数据库失败、限流 | 调用受影响接口 | 映射为稳定错误码；响应不泄露密钥/栈；`request_id` 可关联结构化日志 |
| API-021 | 并发/隔离 | 两项目同名 dataset/sample/task | 并发 CRUD 和查询 | 资源以项目隔离；ID 猜测不返回他方内容；计数和缓存键不串租户 |
| API-022 | 输入安全 | 超大文件、深层 JSON、公式注入文本、HTML/脚本、路径字符 | 上传并在报告读取 | 按大小/深度限制拒绝或安全存储；下载 CSV 防公式注入；UI 输出转义；不发生路径穿越 |

### 5.1 异步任务状态机断言

候选状态：`queued`、`running`、`succeeded`、`failed`、`cancelled`。

| 当前状态 | 事件 | 允许的下一状态 | 必须验证 |
| --- | --- | --- | --- |
| queued | worker claim | running | 只被一个 worker 领取；记录 `started_at` 和 attempt |
| queued | cancel | cancelled | 队列中的重复消息不能重新启动它 |
| running | progress | running | `0 <= progress <= 100` 且单 attempt 内不回退 |
| running | complete | succeeded | 结果与汇总在同一逻辑提交后可见；记录 `finished_at` |
| running | terminal error | failed | 保存稳定错误码和可脱敏详情；不得生成成功报告 |
| running | cancel acknowledged | cancelled | 已完成的部分结果按契约标记 partial，不纳入正式对比 |
| 任一终态 | 任意旧事件 | 原终态 | 不回退；事件被幂等消费并可审计 |

故障注入至少覆盖：worker 在领取后退出、计算中退出、结果写入前退出、结果写入后 ACK 前退出、队列重复投递、provider 超时/429、数据库瞬断、对象存储写失败。

## 6. 指标计算验收

### 6.1 公式与口径

| 指标 | MVP 口径 | 关键边界 |
| --- | --- | --- |
| Recall@K | 前 K 个去重检索文档覆盖的 gold 文档数 / gold 文档总数 | 无 gold 为 null；K 超过返回数时用全部返回结果 |
| MRR@K | 第一个相关文档排名的倒数；前 K 无相关文档为 0 | 无 gold 为 null；重复文档先去重 |
| NDCG@K | `DCG/IDCG`，`DCG=sum((2^rel-1)/log2(rank+1))` | 无 gold/IDCG=0 为 null；必须固定 relevance grade 来源 |
| Context Precision | 相关 context 出现位置上的 `Precision@rank` 平均值 | 无检索 context 且有 gold 时为 0；无可判定 gold 为 null |
| Context Recall | 被检索 context 覆盖的 gold evidence unit 数 / gold evidence unit 总数 | evidence unit 必须有稳定 ID；无 gold evidence 为 null |
| Faithfulness | 被 context 支持的回答 claim 数 / 可判定 claim 总数 | 无 claim 或 judge 无法判定为 null，并记录原始判定 |
| Answer Relevancy | 固定版本 judge 对“问题—回答”相关性的 `[0,1]` 分数 | 单测使用 stub；真实模型只断言范围和版本元数据 |
| Citation Hit Rate | 可解析且确实支持相邻 claim 的引用数 / 回答中全部引用数 | 回答无引用时：有可引用 claim 为 0，无 claim 为 null |
| 延迟 | 样本端到端毫秒数的 count/mean/p50/p95/p99 | 明确 nearest-rank 分位算法；缺失值不按 0 计算 |
| 成本 | 各 provider usage 按固定价格版本计算并求和 | 缺 usage 单独计数；币种和价目版本必填；不得把缺失记 0 |

### 6.2 固定样例

`examples/eval-samples/metric-cases.json` 是机器可读的 oracle，至少包含以下断言：

| Case | 输入摘要 | 期望 |
| --- | --- | --- |
| `ranked-mixed` | gold A/B；返回 X/A/Y/B | R@3=0.5，MRR@3=0.5，NDCG@3=0.3868528072；R@4=1 |
| `duplicate-document` | gold A/B；返回 A/A/B | 去重后 R@2=1、MRR@2=1、NDCG@2=1 |
| `no-gold` | gold 空 | Recall/MRR/NDCG 均为 null，reason=`not_applicable` |
| `context-partial` | relevance flags `[1,0,1]`；覆盖 2/3 gold evidence | Context Precision=5/6，Context Recall=2/3 |
| `faithfulness-partial` | 3 个 claims，2 个被支持 | Faithfulness=2/3，失败 claim ID 被保留 |
| `citation-partial` | 3 个引用，2 个有效且支持 claim | Citation Hit Rate=2/3 |
| `latency-and-cost-missing` | 延迟 100/200/1000；成本 0.01/null/0.03 | mean=433.333333，p50=200，p95=1000；cost=0.04，missing=1 |

算法单元测试必须同时断言分子、分母、去重后的排名或 claim 判定等中间量，避免“最终分数碰巧正确”。

### 6.3 Judge 类指标策略

- 用 stub judge 固定返回 `supported/unsupported/unknown` 和分数，验证解析、聚合、unknown 处理与错误重试。
- 对真实 judge 固定模型版本、温度和 Prompt 版本；同一金标集重复 3 次，记录均值、方差和逐样本翻转率。
- 发布门禁不依赖单次真实 judge 的精确值。首个稳定基线建立后，再由产品和算法负责人确认允许漂移阈值。
- 保存最小必要的 judge 输入/输出并脱敏；不得把完整私有上下文写入 CI 日志。

## 7. 前端关键状态矩阵

| 页面/组件 | 状态 | 测试操作 | 期望结果 |
| --- | --- | --- | --- |
| 项目概览 | loading/empty/normal/error | 延迟、返回空数组、正常数据、500 | 骨架屏结束；空态有创建入口；正常卡片可跳转；错误态含 request ID 和安全重试 |
| 数据集列表 | 分页/筛选/删除冲突 | 翻页、搜索、清空、删除被任务引用数据集 | URL 保留筛选；无重复行；清空恢复；409 给出引用关系而非静默失败 |
| 导入向导 | 预览/部分错误/全错/大文件 | 选择三类 fixture 并提交 | 展示编码、schema、有效/无效数和行级错误；禁用非法提交；原子模式说明清楚 |
| 新建评测 | 默认/校验/提交中/重复提交 | 缺字段、选择版本、双击提交 | 必填项明确；版本快照摘要可见；提交时防重复；成功后跳到唯一任务 |
| 任务列表/详情 | queued/running/succeeded/failed/cancelled | 用状态 stub 轮换并刷新 | 状态颜色之外还有文字；进度不回退；终态停止轮询；失败可复制 request ID |
| 报告概览 | normal/partial/null metric | 注入完整、部分和 null 指标响应 | 计数守恒；null 显示“不适用/缺失”而非 0；图表与表格口径一致 |
| 样本诊断 | 长文本/多 context/失效引用 | 打开 `context-pollution-001` 等样本 | gold、context、answer 可对照；引用点击定位；诊断展示证据；长文本可折叠 |
| 版本对比 | A/B 交换/缺失样本/不兼容 | 交换基线，切换交并集，传不同 schema | 差值符号同步变化；覆盖率可见；不兼容阻止或醒目标识 |
| 趋势看板 | 空范围/单点/多点 | 切换日期、指标、版本 | 空态准确；单点不伪造趋势线；多点顺序正确；图例、tooltip、表格一致 |
| 全局 | 401/403/404/429/500/离线 | 拦截相应响应 | 明确区分；不会无限重试；恢复网络后可安全重试；不泄漏内部栈 |

前端自动化优先级：P0 主流程使用浏览器 E2E；筛选、格式化和状态映射使用组件测试；视觉快照只覆盖稳定组件，不能代替语义断言。关键交互需验证键盘可达、可见焦点、表单 label、图表文本替代和非颜色唯一编码。

## 8. 样例数据设计

### 8.1 文件

- `examples/eval-samples/valid-samples.jsonl`：6 条可导入的评测 trace，覆盖正常、检索缺失、重排失败、上下文污染、缺引用和正确拒答。
- `examples/eval-samples/invalid-samples.jsonl`：校验用 envelope，每行包含 `case_id`、`input` 和 `expected_error`。
- `examples/eval-samples/metric-cases.json`：无需模型即可复算的指标 oracle。
- `examples/eval-samples/README.md`：字段、用法和数据治理说明。

### 8.2 扩展金标集原则

- 每个主要业务域至少 30 条，问题类型覆盖事实、列表、多跳、时间敏感、歧义、不可回答和恶意提示。
- 每条 gold 由两人独立标注，冲突由第三人仲裁；保留标注版本和 evidence unit。
- 诊断标签不只保存根因名称，还要保存可验证证据，例如 gold 未出现在 top-K、错误 claim 未被任何 context 支持。
- 划分 development/validation/test，测试集不得用于 Prompt 调参；相似问题按语义簇分组后再切分，避免泄漏。
- 所有样例使用合成或获授权文本，不包含密钥、个人敏感信息或受限文档原文。

## 9. 非功能与可靠性测试

以下是初始候选阈值，必须在架构和容量目标确认后更新，未确认前不作为“已经达标”的声明。

| 类别 | 场景 | 候选目标 |
| --- | --- | --- |
| API 性能 | 列表/详情在 10 万样本数据集上查询 | p95 < 2 s，错误率 < 1% |
| 导入 | 10,000 条、文件不超过 10 MB | 受理响应 p95 < 2 s；后台导入 < 5 min |
| 并发 | 10 个评测任务、确定性 fake provider | 不丢任务、不重复计费、不跨任务污染 |
| 恢复 | worker 被强制终止并重启 | 任务在可见超时内恢复或失败，绝不永久 running |
| 安全 | OWASP 常见输入、越权 ID、日志脱敏 | 无跨项目读取；响应/日志无 token、密钥和完整敏感上下文 |
| 可观测性 | 任一失败样本和 provider 调用 | 可由 task/sample/request/trace ID 串联，日志不依赖模糊文本搜索 |

## 10. CI 质量门禁建议

### 10.1 每个 PR 的阻断门禁

1. 格式化、lint、类型检查、Markdown 链接检查和 OpenAPI/schema 校验通过。
2. 所有 JSON/JSONL fixture 可解析，`sample_id` 唯一，gold 引用和 citation 引用完整。
3. 指标单元测试全通过；核心指标模块语句覆盖率至少 95%、分支覆盖率至少 90%。
4. 全仓单元+集成测试通过；实现稳定后以语句 80%、分支 75% 作为最低线，并禁止覆盖率下降。
5. 数据库 migration 在空库升级、上一版本升级和回滚策略检查中通过。
6. API 契约兼容性检查通过；破坏性变更必须显式版本化并同步前端契约。
7. 依赖漏洞、许可证、secret 扫描无未豁免的 high/critical。
8. P0 浏览器 E2E 使用 fake provider 通过，失败时上传脱敏日志、截图/trace 和测试报告。

阻断条件：任何 P0 失败、指标 oracle 不一致、状态机非法回退、数据丢失/串租户、凭据泄漏、不可解释的 flaky 重跑通过，均不得合并。

### 10.2 非 PR 流水线

- 夜间：真实 provider 小金标集、漂移统计、完整 E2E、依赖扫描和中等规模性能测试。
- 每周：恢复演练、较大数据集、队列重复/乱序和对象存储故障注入。
- 发布前：固定 commit 的回归报告、未关闭 P0/P1 清单、migration 演练、回滚演练和数据备份恢复证据。
- flaky 测试必须记录 owner、原因和到期日；隔离不能让对应功能被默认视为通过。

### 10.3 建议流水线顺序

`fixture/schema → lint/type → unit(metric first) → integration(API + DB + queue) → build → E2E(fake provider) → security → publish report`

并行执行不相互依赖的 lint、单元和安全扫描；只有所有阻断门禁成功后才允许生成可发布制品。

## 11. 风险清单

| ID | 风险 | 影响 | 当前缓解/待办 | 建议责任方 |
| --- | --- | --- | --- | --- |
| R-01 | API、schema 和状态名尚未冻结 | 测试与实现漂移 | 后端 OpenAPI 合并后映射 API ID；契约变更触发测试更新 | 后端 + QA |
| R-02 | 指标公式可能与算法设计口径不同 | 分数不可比 | 算法负责人确认去重、空分母、NDCG grade、judge unknown 规则 | 算法 + QA |
| R-03 | LLM judge 非确定性和版本漂移 | 回归误报/漏报 | stub 单测、版本固定、重复测量和翻转率；真实 judge 不做逐位断言 | 算法 |
| R-04 | gold 标注错误或泄漏到调参集 | 指标虚高 | 双人标注、仲裁、语义簇切分、测试集访问控制 | 产品 + 算法 |
| R-05 | 异步消息重复或乱序 | 重复计费、状态回退 | 幂等键、attempt/version 校验、终态保护、故障注入 | 后端 |
| R-06 | provider 429/超时/部分返回 | 任务卡死或伪成功 | 有界重试、退避、熔断、partial 语义和失败码 | 后端 |
| R-07 | 长上下文/大数据集导致 UI 和查询退化 | 核心报告不可用 | 分页/虚拟化、异步聚合、容量基准 | 前端 + 后端 |
| R-08 | 成本统计缺 usage 或价格版本 | 账目错误 | 缺失单列、币种/价目版本必填、Decimal 计算 | 后端 + 算法 |
| R-09 | 日志/报告泄露原始上下文或密钥 | 合规与安全事故 | 合成 CI 数据、字段级脱敏、日志审查和 secret scan | DevOps + 后端 |
| R-10 | 覆盖率门槛被低价值断言“刷高” | 缺陷进入主干 | 关键 mutation/边界测试、P0 traceability、review checklist | QA |
| R-11 | 样本集合变化却直接画趋势 | 趋势误导 | 报告展示 dataset version/coverage，默认阻止不兼容比较 | 产品 + 前端 |
| R-12 | 当前无实现，性能阈值缺容量依据 | 门禁不现实 | 产品确认规模，架构压测建立基线后冻结 SLO | 产品 + DevOps + QA |

## 12. 进入/退出标准与执行报告

### 12.1 开始正式执行前

- PRD、指标定义、OpenAPI/schema、状态机和核心页面交互已冻结到可引用版本。
- 测试环境可重复创建，fake provider 和样例数据可用。
- P0 验收项已映射到自动化或明确的人工步骤，缺陷严重度和 owner 已约定。

### 12.2 发布候选退出标准

- AC-001 至 AC-008 以及所有 P0 API/指标/E2E 用例通过。
- 无开放的 blocker/critical/high 缺陷；P1 例外有 owner、到期日和书面风险接受。
- 指标 oracle、migration/恢复、权限隔离和安全门禁通过。
- 报告包含真实输入、步骤、期望/实际、环境和证据链接；不得只写“测试通过”。

### 12.3 最小测试报告模板

```text
Git SHA / build：
环境与时间：
数据集文件、schema 版本、SHA-256：
模型/Prompt/Embedding/Rerank/judge 版本：
执行范围（测试 ID）：
结果：通过 / 失败 / 阻塞 / 未执行（分别计数）：
失败明细：输入、步骤、期望、实际、request/trace ID、缺陷链接：
未执行原因与风险接受：
结论：可发布 / 有条件可发布 / 不可发布：
```
