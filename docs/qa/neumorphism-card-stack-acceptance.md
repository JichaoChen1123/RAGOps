# WOR-69 前端重设计验收记录

验收日期：2026-09-05。起点为 `main` 的 `7c3c1dff622838575648d746f75343cf56ab3b60`，在独立分支 `agent/ragops/bd1953fd5894` 开发。本次仅改变前端表现、导航/弹窗可访问性和卡片浏览；API client、数据模型、Mock fixture 与后端业务代码保持原契约。

## 代码实现

- 五个业务页面、404、壳层、导航、模式状态、表单、对话框、表格、反馈、指标、图表、证据与报告区域已统一新拟物主题。
- 最近运行和报告样本支持最多三层卡片、键盘/点击切换、选中项恢复、空/单项情况；报告可切换完整表格，复核筛选在两种视图间保留。
- 手机端展开完整导航；对话框提供初始焦点、Tab 循环、Escape、焦点恢复；表格在自身区域滚动，不扩展页面宽度。
- API、执行器、提供方配置三轴独立；执行成功不推导质量结果，模拟记录、未知 Token/成本、未评指标仍明确显示。

页面信息架构、组件清单、视觉字段、API 依赖与优先级见 [设计说明](../design/neumorphism-card-stack.md)。

## 自动化检查

| 检查 | 结果 |
| --- | --- |
| `npm --prefix frontend run typecheck` | 通过。 |
| `npm --prefix frontend test` | 7 个文件、52 项通过，含原有 43 项及新增 9 项。 |
| `npm --prefix frontend run build` | 通过，生产资源构建成功。 |
| `git diff --check` | 通过。 |
| 既有 WOR-49 / WOR-55 契约脚本 | 通过。 |
| `backend/.venv/Scripts/python.exe scripts/validate_repository.py` | 通过，检查文档链接、JSON/JSONL 和 YAML。 |

新增测试覆盖：三层数量、只挂载当前记录控件、循环切换、Home/End、焦点保留、后层点击、重排/筛选/空数据、单项禁用、嵌套输入按键、执行/质量分离、手机导航、对话框焦点、报告卡片/表格筛选与提供方状态读取失败。

Windows 沙箱曾阻止 npm/uv 缓存写入和 Vite/Edge 子进程；获得工具权限后完成安装与检查。这些启动限制不计为代码检查通过的依据，最终成功结果来自实际执行。

## 浏览器与视觉验收

使用仓库已有 `playwright-core` 和本机无头 Edge，无新增依赖。检查脚本为 `frontend/scripts/redesign-browser.mjs`，输出完整 JSON 与原始截图至 `docs/qa/screenshots/neumorphism/`。

| 范围 | 实际检查 |
| --- | --- |
| Mock 路由 | 1440×900、820×900、390×900 下的概览、数据集、任务、报告、样本诊断与 404。 |
| Mock 关键流程 | 桌面与 390px 下创建草稿、详情、导入并发布 12 条示例、搜索、创建任务、读取已有报告、卡片切换、表格切换、JSON 下载、诊断、引用定位、人工确认、源文档对话框。 |
| 状态 | 390px 下加载、空、失败、部分数据；显式状态与重试语义保留，原单测覆盖刷新失败保留旧数据。 |
| 本地 API | 后端固定 mock 且关闭外部调用；使用已发布的本地示例数据，创建任务后显式刷新至终态，读取报告和诊断。桌面与 390px 截图覆盖状态、长 ID、运行快照与未知值。 |
| 动效 | 正常动效下后层散开；揭牌前后阴影不增大；按钮自身 transform 为 none；reduced-motion 下 transition 为 0s 且前层不揭牌。 |
| 文字对比 | 六种文字 token 在两种表面上共 12 组计算，最低 5.18:1，满足普通正文 AA 4.5:1。 |
| 页面边界 | 所有记录的视口均满足 `scrollWidth <= clientWidth + 1`；非空页、无 pageerror/console error、无非 localhost HTTP 请求。 |

已打开并人工目视检查桌面概览/数据集/诊断、手机概览/数据集/报告、API 桌面报告/手机诊断与手机创建对话框截图。关键文字、操作和证据内容未发现重叠或遮挡。长表格使用局部滚动，长卡片内容可内部滚动；并不声称所有内容同时出现在首屏。

可审计结果：[`mock-checks.json`](screenshots/neumorphism/mock-checks.json)、[`api-checks.json`](screenshots/neumorphism/api-checks.json)。两份均应为 `passed: true`，不要把失败截图或旧运行日志当作最终证据。

## 复现

先按前端 README 安装依赖，启动本地 Mock 服务：

```powershell
$env:VITE_API_MODE = 'mock'
npm --prefix frontend run dev -- --host 127.0.0.1 --port 15173 --strictPort
```

在另一个终端执行：

```powershell
node frontend/scripts/redesign-browser.mjs mock
```

API 验收使用独立本地数据库和不带凭据的后端：

```powershell
uv sync --project backend --frozen
$env:RAGOPS_DATABASE_URL = 'sqlite:///./redesign-acceptance.sqlite'
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
$env:RAGOPS_OPENAI_COMPAT_API_KEY = ''
$env:RAGOPS_OPENAI_COMPAT_BASE_URL = ''
$env:RAGOPS_OPENAI_COMPAT_DEFAULT_MODEL = ''
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18000
```

另开终端运行前端 API 模式，然后在另一个终端执行验收脚本：

```powershell
$env:VITE_API_MODE = 'api'
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:18000'
npm --prefix frontend run dev -- --host 127.0.0.1 --port 15174 --strictPort
```

```powershell
node frontend/scripts/redesign-browser.mjs api
```

脚本首次导入固定示例，重复运行时复用已有可用示例；每次会新增本地 mock 任务。可通过 `RAGOPS_FRONTEND_URL` 改前端地址、`RAGOPS_BROWSER_EXECUTABLE` 指定本机 Chromium 可执行文件。验收结束后关闭本次前后端进程；没有持久服务交付。

## 未验证项

没有调用真实外部模型、使用真实凭据或验证提供方连接；没有运行 Docker/生产部署验收、Safari/Firefox、实体手机或读屏器人工测试。对比度结果是主题文字 token 的计算，不能代替完整的辅助技术合规审计。GitHub CI 由 PR 触发，交付时不等待或代替本地检查；PR 留待负责人验收，不自行合并。
