import {
  Activity,
  BarChart3,
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
          <span className="nav-disabled" title="版本对比入口将在后续阶段开放"><GitCompareArrows size={17} /><span className="nav-label">版本对比</span><span>即将推出</span></span>
          <span className="nav-disabled" title="趋势详情可从项目概览打开"><BarChart3 size={17} /><span className="nav-label">趋势看板</span><span>从概览查看</span></span>
          <span className="nav-section">配置</span>
          <span className="nav-disabled" title="当前版本只读"><Boxes size={17} /><span className="nav-label">模型与 Prompt</span></span>
          <span className="nav-disabled" title="当前版本只读"><Settings size={17} /><span className="nav-label">项目设置</span></span>
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
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </div>
  );
}

export interface WorkspaceOutletContext {
  scenario: ViewScenario;
}
