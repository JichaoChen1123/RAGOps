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
  Search,
  Settings,
} from 'lucide-react';
import { NavLink, Outlet, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { apiMode } from '../api/client';
import type { ViewScenario } from '../types';

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

export function WorkspaceShell() {
  const { projectId = 'demo' } = useParams();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const scenario = (searchParams.get('state') as ViewScenario | null) ?? 'normal';
  const page = pageTitles.find((item) => location.pathname.includes(item.match)) ?? pageTitles[4];

  const changeScenario = (next: ViewScenario) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'normal') params.delete('state');
    else params.set('state', next);
    setSearchParams(params);
  };

  const preserveState = (path: string) => scenario === 'normal' ? path : `${path}?state=${scenario}`;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Activity size={20} /></div>
          <div><strong>RAGOps</strong><span>Quality Console</span></div>
          <button className="icon-button sidebar-collapse" aria-label="收起侧边栏"><PanelLeftClose size={17} /></button>
        </div>

        <button className="project-switcher" type="button">
          <span className="project-avatar">CS</span>
          <span><small>当前项目</small><strong>客服 RAG 生产线</strong></span>
          <ChevronDown size={15} />
        </button>

        <nav aria-label="主导航">
          <span className="nav-section">项目</span>
          <NavLink to={preserveState(`/projects/${projectId}/overview`)}><Gauge size={17} />项目概览</NavLink>
          <NavLink to={preserveState(`/projects/${projectId}/datasets`)}><Database size={17} />数据集</NavLink>
          <span className="nav-section">评测与诊断</span>
          <NavLink to={preserveState(`/projects/${projectId}/evaluations`)}><FlaskConical size={17} />评测任务<span className="nav-count">3</span></NavLink>
          <span className="nav-disabled"><GitCompareArrows size={17} />版本对比<span>即将推出</span></span>
          <span className="nav-disabled"><BarChart3 size={17} />趋势看板<span>即将推出</span></span>
          <span className="nav-section">配置</span>
          <span className="nav-disabled"><Boxes size={17} />模型与 Prompt</span>
          <span className="nav-disabled"><Settings size={17} />项目设置</span>
        </nav>

        <div className="sidebar-footer">
          <button type="button"><CircleHelp size={16} />使用帮助</button>
          <div className="operator"><span>JC</span><div><strong>Jichao</strong><small>项目管理员</small></div><ChevronDown size={14} /></div>
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
            <button className="icon-button" type="button" aria-label="搜索"><Search size={18} /></button>
            <span className="shortcut">⌘ K</span>
          </div>
        </header>
        <main className="content"><Outlet context={{ scenario }} /></main>
      </div>
    </div>
  );
}

export interface WorkspaceOutletContext {
  scenario: ViewScenario;
}
