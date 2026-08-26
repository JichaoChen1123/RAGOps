import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return <div className="standalone-state"><span>404</span><h1>页面不存在</h1><p>这个 RAGOps 路由不存在，或资源已经被移除。</p><Link className="button button-primary" to="/projects/demo/overview"><ArrowLeft size={15} />返回项目概览</Link></div>;
}
