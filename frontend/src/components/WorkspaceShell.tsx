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
import { apiMode } from '../api/client';
import type { ViewScenario } from '../types';
import { Dialog, Toast } from './Interaction';

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

  const changeScenario = (next: ViewScenario) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'normal') params.delete('state');
    else params.set('state', next);
    setSearchParams(params);
  };

  const preserveState = (path: string) => scenario === 'normal' ? path : `${path}?state=${scenario}`;
  const matchedTargets = useMemo(() => searchTargets.filter((target) =>
    `${target.label} ${target.description}`.toLowerCase().includes(searchQuery.trim().toLowerCase())), [searchQuery]);

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
                <span className="project-avatar">CS</span><span><strong>客服 RAG 生产线</strong><small>当前项目 · Mock</small></span>
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
            <span className={`api-mode api-${apiMode}`}><i />{apiMode === 'mock' ? 'MOCK 数据' : 'LIVE API'}</span>
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
          <div><strong>1. 准备数据集</strong><p>在数据集页导入示例 JSONL，或新建一个 Mock 数据集。</p></div>
          <div><strong>2. 发起评测</strong><p>选择数据集、模型与 Prompt 版本，生成可追踪的演示任务。</p></div>
          <div><strong>3. 定位故障</strong><p>从完成任务进入报告，再下钻失败样本核对检索证据与引用。</p></div>
        </div>
        <p className="form-hint">顶部“数据场景”可切换加载、空数据、失败和部分数据状态；带 MOCK 标识的写入仅保存在当前页面会话。</p>
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
          <div><Bot size={16} /><span><small>MODEL</small><strong>qwen3-32b@2026-08</strong></span><i>ACTIVE</i></div>
          <div><SlidersHorizontal size={16} /><span><small>PROMPT</small><strong>support-rag@v12</strong></span><i>PINNED</i></div>
          <div><Database size={16} /><span><small>DATASET</small><strong>客服黄金问答集 · v3.4</strong></span><i>120 SAMPLES</i></div>
        </div>
        <p className="form-hint">当前 Mock 工作台展示最近一次评测的版本快照；连接配置 API 后可编辑并创建新版本。</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </div>
  );
}

export interface WorkspaceOutletContext {
  scenario: ViewScenario;
}
