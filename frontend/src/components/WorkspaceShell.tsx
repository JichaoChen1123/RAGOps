import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  ChevronDown,
  CircleHelp,
  Database,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  SlidersHorizontal,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import type { ModelExecutionStatus, ViewScenario } from '../types';
import { Dialog, Toast } from './Interaction';
import { StatusBadge } from './StatusBadge';

const scenarioLabels: Record<ViewScenario, string> = {
  normal: '正常数据',
  loading: '加载中',
  empty: '空数据',
  error: '请求失败',
  partial: '部分数据',
};

const pageTitles = [
  { match: '/samples/', title: '样本诊断', group: '评测与诊断' },
  { match: '/report', title: '评测报告', group: '评测与诊断' },
  { match: '/evaluations', title: '评测任务', group: '评测与诊断' },
  { match: '/datasets', title: '数据集管理', group: '数据资产' },
  { match: '/overview', title: '项目概览', group: '工作台' },
];

const searchTargets = [
  { label: '项目概览', description: '质量指标、趋势与最近评测', path: 'overview' },
  { label: '数据集管理', description: '导入、创建、筛选与归档数据集', path: 'datasets' },
  { label: '评测任务', description: '创建评测任务并进入报告', path: 'evaluations' },
];

export function WorkspaceShell() {
  const { projectId = 'demo' } = useParams();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [roadmapOpen, setRoadmapOpen] = useState(false);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<
    { state: 'loading' } | { state: 'success'; data: ModelExecutionStatus } | { state: 'error'; message: string }
  >({ state: 'loading' });
  const [searchQuery, setSearchQuery] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);
  const scenario = (searchParams.get('state') as ViewScenario | null) ?? 'normal';
  const page = pageTitles.find((item) => location.pathname.includes(item.match)) ?? pageTitles[4];

  useEffect(() => {
    const openCommandSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', openCommandSearch);
    return () => window.removeEventListener('keydown', openCommandSearch);
  }, []);

  useEffect(() => {
    let active = true;
    setRuntimeStatus({ state: 'loading' });
    void apiClient.getModelExecutionStatus().then((data) => {
      if (active) setRuntimeStatus({ state: 'success', data });
    }).catch((error: unknown) => {
      if (active) setRuntimeStatus({ state: 'error', message: error instanceof Error ? error.message : '状态 API 请求失败' });
    });
    return () => { active = false; };
  }, []);

  const changeScenario = (next: ViewScenario) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'normal') params.delete('state');
    else params.set('state', next);
    setSearchParams(params);
  };

  const preserveState = (path: string) => scenario === 'normal' ? path : `${path}?state=${scenario}`;
  const matchedTargets = useMemo(() => searchTargets.filter((target) =>
    `${target.label} ${target.description}`.toLowerCase().includes(searchQuery.trim().toLowerCase())), [searchQuery]);
  const providerStatus = runtimeStatus.state === 'success' ? runtimeStatus.data.providers[0] : undefined;
  const backendAdapterLabel = runtimeStatus.state === 'success'
    ? runtimeStatus.data.backendExecutionAdapter ?? '未知'
    : runtimeStatus.state === 'loading' ? '读取中' : '未知';
  const providerLabel = runtimeStatus.state === 'success'
    ? providerStatus?.configurationStatus === 'verified' ? '真实已验证'
      : providerStatus?.configurationStatus === 'configured_unverified' ? '已配置未验证'
        : providerStatus?.configurationStatus === 'not_configured' ? '未配置' : '未知'
    : runtimeStatus.state === 'loading' ? '读取中' : '未知';

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-is-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Activity size={20} /></div>
          <div><strong>RAGOps</strong><span>Quality Console</span></div>
          <button
            className="icon-button sidebar-collapse"
            type="button"
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
            aria-pressed={collapsed}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>

        <div className="project-switcher-wrap">
          <button
            className="project-switcher"
            type="button"
            aria-expanded={projectMenuOpen}
            aria-haspopup="menu"
            onClick={() => setProjectMenuOpen((value) => !value)}
          >
            <span className="project-avatar">CS</span>
            <span><small>当前项目</small><strong>客服 RAG 生产线</strong></span>
            <ChevronDown size={15} />
          </button>
          {projectMenuOpen && (
            <div className="project-menu" role="menu">
              <button type="button" role="menuitem" onClick={() => { setProjectMenuOpen(false); setFeedback('当前已是“客服 RAG 生产线”'); }}>
                <span className="project-avatar">CS</span><span><strong>客服 RAG 生产线</strong><small>当前项目 · {apiMode === 'mock' ? 'Mock fixture' : 'API 数据'}</small></span>
              </button>
              <button type="button" role="menuitem" disabled title="连接项目 API 后可切换">
                <span className="project-avatar">+</span><span><strong>其他项目</strong><small>连接项目 API 后可用</small></span>
              </button>
            </div>
          )}
        </div>

        <nav aria-label="主导航">
          <span className="nav-section">项目</span>
          <NavLink title="项目概览" to={preserveState(`/projects/${projectId}/overview`)}><Gauge size={17} /><span className="nav-label">项目概览</span></NavLink>
          <NavLink title="数据集" to={preserveState(`/projects/${projectId}/datasets`)}><Database size={17} /><span className="nav-label">数据集</span></NavLink>
          <span className="nav-section">评测与诊断</span>
          <NavLink title="评测任务" to={preserveState(`/projects/${projectId}/evaluations`)}><FlaskConical size={17} /><span className="nav-label">评测任务</span><span className="nav-count">3</span></NavLink>
          <button className="nav-item nav-coming-soon" type="button" aria-label="版本对比，即将推出" onClick={() => setRoadmapOpen(true)}>
            <GitCompareArrows size={17} />
            <span className="nav-item-copy"><span className="nav-label">版本对比</span><small>模型 / Prompt 回归</small></span>
            <span className="nav-badge nav-badge-next">NEXT</span>
          </button>
          <Link className="nav-item nav-secondary" aria-label="趋势看板，从概览查看" title="打开项目概览中的质量趋势" to={`${preserveState(`/projects/${projectId}/overview`)}#quality-trends`}>
            <BarChart3 size={17} />
            <span className="nav-item-copy"><span className="nav-label">趋势看板</span><small>质量 / 延迟 / 成本</small></span>
            <span className="nav-badge nav-badge-live">LIVE</span>
          </Link>
          <span className="nav-section">配置</span>
          <button className="nav-item nav-readonly" type="button" aria-label="模型与 Prompt，只读快照" onClick={() => setConfigurationOpen(true)}>
            <Boxes size={17} />
            <span className="nav-item-copy"><span className="nav-label">模型与 Prompt</span><small>当前运行版本</small></span>
            <span className="nav-badge">READ</span>
          </button>
          <button className="nav-item nav-disabled" type="button" aria-label="项目设置，连接 API 后开放" title="连接项目 API 后开放" disabled>
            <Settings size={17} />
            <span className="nav-item-copy"><span className="nav-label">项目设置</span><small>连接 API 后开放</small></span>
            <span className="nav-badge">API</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <button type="button" onClick={() => setHelpOpen(true)}><CircleHelp size={16} />使用帮助</button>
          <button className="operator" type="button" onClick={() => setFeedback('Mock 工作台不提供账户设置') }><span>JC</span><div><strong>Jichao</strong><small>项目管理员</small></div><ChevronDown size={14} /></button>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="page-heading">
            <span>{page.group} / <strong>{page.title}</strong></span>
            <h1>{page.title}</h1>
          </div>
          <div className="topbar-actions">
            <label className="scenario-select">
              <span>数据场景</span>
              <select aria-label="数据场景" value={scenario} onChange={(event) => changeScenario(event.target.value as ViewScenario)}>
                {Object.entries(scenarioLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <button className="runtime-axes" type="button" aria-label="查看运行模式状态" onClick={() => setConfigurationOpen(true)}>
              <span><small>前端</small><strong>{apiMode === 'mock' ? 'Mock fixture' : 'API 数据'}</strong></span>
              <span><small>执行器</small><strong>{backendAdapterLabel}</strong></span>
              <span><small>提供方</small><strong>{providerLabel}</strong></span>
            </button>
            <button className="icon-button" type="button" aria-label="搜索" onClick={() => setSearchOpen(true)}><Search size={18} /></button>
            <span className="shortcut">⌘ K</span>
          </div>
        </header>
        <main className="content"><Outlet context={{ scenario }} /></main>
      </div>

      <Dialog open={searchOpen} title="搜索工作台" eyebrow="COMMAND SEARCH" onClose={() => setSearchOpen(false)}>
        <label className="dialog-search"><Search size={16} /><input autoFocus aria-label="搜索页面" placeholder="搜索页面或功能" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /></label>
        <div className="search-results">
          {matchedTargets.map((target) => (
            <Link key={target.path} to={preserveState(`/projects/${projectId}/${target.path}`)} onClick={() => setSearchOpen(false)}>
              <strong>{target.label}</strong><span>{target.description}</span><ChevronDown size={14} />
            </Link>
          ))}
          {matchedTargets.length === 0 && <p>没有匹配的工作台入口。</p>}
        </div>
      </Dialog>

      <Dialog open={helpOpen} title="RAGOps 快速帮助" eyebrow="MVP GUIDE" onClose={() => setHelpOpen(false)}>
        <div className="help-grid">
          <div><strong>1. 准备数据集</strong><p>导入 2.0 人工样本并发布，保留上下文来源和片段标识。</p></div>
          <div><strong>2. 发起评测</strong><p>显式选择执行器；不可用方式由后端拒绝，不会回退到 Mock。</p></div>
          <div><strong>3. 定位故障</strong><p>从完成任务进入报告，再下钻失败样本核对检索证据与引用。</p></div>
        </div>
        <p className="form-hint">顶部同时展示前端数据源、后端执行器和提供方配置状态。API 数据不等于模型已连接；本阶段没有真实连接验证按钮。</p>
      </Dialog>
      <Dialog open={roadmapOpen} title="版本对比 · 下一阶段" eyebrow="ROADMAP / PHASE 2" onClose={() => setRoadmapOpen(false)}>
        <div className="availability-card">
          <div className="availability-icon"><GitCompareArrows size={19} /></div>
          <div><strong>入口已定义，交互将在下一阶段接入</strong><p>计划支持选择基线任务，对比模型、Prompt、检索配置与指标回归，并下钻到变化样本。</p></div>
        </div>
        <div className="roadmap-list" aria-label="版本对比计划能力">
          <div><span>01</span><strong>版本上下文</strong><small>Dataset / Model / Prompt / Retriever</small></div>
          <div><span>02</span><strong>指标回归</strong><small>Delta / Gate / Regression samples</small></div>
          <div><span>03</span><strong>故障差异</strong><small>Diagnosis diff / Evidence trace</small></div>
        </div>
      </Dialog>
      <Dialog open={configurationOpen} title="模型与 Prompt · 只读快照" eyebrow="ACTIVE EVALUATION CONTEXT" onClose={() => setConfigurationOpen(false)}>
        <div className="configuration-snapshot">
          <div><Database size={16} /><span><small>FRONTEND DATA SOURCE</small><strong>{apiMode === 'mock' ? 'Mock fixture（浏览器内存）' : 'RAGOps API（仅表示连接项目后端）'}</strong></span><i>{apiMode.toUpperCase()}</i></div>
          <div><Bot size={16} /><span><small>BACKEND EXECUTION ADAPTER</small><strong>{backendAdapterLabel}</strong></span><i>{runtimeStatus.state === 'success' && runtimeStatus.data.activeAdapter?.isMock ? 'MOCK' : 'READ ONLY'}</i></div>
          <div><SlidersHorizontal size={16} /><span><small>PROVIDER CONFIGURATION</small><strong>{providerStatus?.providerId ?? '提供方未知'} · {providerLabel}</strong></span>{providerStatus ? <StatusBadge value={providerStatus.configurationStatus} /> : <i>UNKNOWN</i>}</div>
        </div>
        {runtimeStatus.state === 'error' && <p className="form-hint">状态 API 读取失败：{runtimeStatus.message}。前端不会据此猜测执行器或提供方已连接。</p>}
        {runtimeStatus.state === 'success' && <dl className="detail-list runtime-detail"><div><dt>外部调用总开关</dt><dd>{runtimeStatus.data.externalCallsEnabled === null ? '未知' : runtimeStatus.data.externalCallsEnabled ? '已开启' : '已关闭'}</dd></div><div><dt>执行可用</dt><dd>{runtimeStatus.data.executionAvailable === null ? '未知' : runtimeStatus.data.executionAvailable ? '是' : '否'}</dd></div><div><dt>状态来源</dt><dd>{runtimeStatus.data.source === 'fixture' ? '前端模拟状态 fixture' : '后端状态 API（无提供方探测）'}</dd></div></dl>}
        <p className="form-hint">配置完整只表示“已配置但未验证”。本阶段不提供真实验证入口，也不会从浏览器发送凭据或提供方探测请求。</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </div>
  );
}

export interface WorkspaceOutletContext {
  scenario: ViewScenario;
}
