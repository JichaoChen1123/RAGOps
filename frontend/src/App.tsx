import { Navigate, Route, Routes } from 'react-router-dom';
import { WorkspaceShell } from './components/WorkspaceShell';
import { DatasetsPage } from './pages/DatasetsPage';
import { DiagnosisPage } from './pages/DiagnosisPage';
import { EvaluationsPage } from './pages/EvaluationsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { OverviewPage } from './pages/OverviewPage';
import { ReportPage } from './pages/ReportPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/projects/demo/overview" replace />} />
      <Route path="/projects/:projectId" element={<WorkspaceShell />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="datasets" element={<DatasetsPage />} />
        <Route path="evaluations" element={<EvaluationsPage />} />
        <Route path="evaluations/:taskId/report" element={<ReportPage />} />
        <Route path="evaluations/:taskId/samples/:sampleId" element={<DiagnosisPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
