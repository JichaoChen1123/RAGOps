import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { EvaluationTask } from '../types';
import { formatDateTime } from '../lib/format';
import { CardStack } from './CardStack';
import { StatusBadge } from './StatusBadge';

export function TaskStack({ tasks, projectId }: { tasks: EvaluationTask[]; projectId: string }) {
  return <CardStack items={tasks} label="最近运行卡片" getLabel={(task) => task.name} renderItem={(task) => <>
    <div className="record-heading"><span className="record-kind">评测运行</span>{task.isMock === true && <em className="mock-label">SIMULATED</em>}</div>
    <h3>{task.name}</h3><p className="record-id">{task.id}</p>
    <dl className="record-states">
      <div><dt>生命周期</dt><dd><StatusBadge value={task.status} /></dd></div>
      <div><dt>执行结果</dt><dd>{task.outcome ? <StatusBadge value={task.outcome} /> : '尚无结果'}</dd></div>
      <div><dt>质量状态</dt><dd><StatusBadge value={task.qualityStatus} /></dd></div>
      <div><dt>质量分</dt><dd className="record-score">{task.qualityScore ?? '未知'}</dd></div>
    </dl>
    <dl className="record-details">
      <div><dt>数据集</dt><dd>{task.datasetName}</dd></div>
      <div><dt>执行器 / 模型</dt><dd>{task.adapterId ?? '未知'} / {task.modelVersion ?? '未知'}</dd></div>
      <div><dt>Prompt</dt><dd>{task.promptVersion ?? '未知'}</dd></div>
    </dl>
    <footer className="record-footer"><span>{formatDateTime(task.completedAt ?? task.createdAt)}</span>
      {['completed', 'failed', 'cancelled'].includes(task.status)
        ? <Link className="button button-secondary" aria-label={`查看 ${task.name} 报告`} to={`/projects/${projectId}/evaluations/${task.id}/report`}>查看报告 <ArrowRight size={16} /></Link>
        : <span className="record-pending">{task.status === 'running' ? `进度 ${task.progress}%` : '等待执行'} · 终态后可读报告</span>}
    </footer>
  </>} />;
}
