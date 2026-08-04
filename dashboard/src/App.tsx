import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OverviewPage } from './pages/OverviewPage';
import { JobsPage } from './pages/JobsPage';
import { DlqPage } from './pages/DlqPage';
import { WorkersPage } from './pages/WorkersPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="dlq" element={<DlqPage />} />
          <Route path="workers" element={<WorkersPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
