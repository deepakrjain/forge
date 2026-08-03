import React from 'react';
import { Activity, Server, Cpu, Database } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <div className="dashboard-container">
      <header className="header">
        <div className="logo-group">
          <Activity className="logo-icon" />
          <h1>Forge Dashboard</h1>
        </div>
        <span className="badge">Phase 1: Initialized</span>
      </header>

      <main>
        <div className="grid">
          <div className="card">
            <div className="card-header">
              <span>API Gateway</span>
              <Server size={18} />
            </div>
            <div className="card-value">FastAPI</div>
          </div>

          <div className="card">
            <div className="card-header">
              <span>Worker Engine</span>
              <Cpu size={18} />
            </div>
            <div className="card-value">Python</div>
          </div>

          <div className="card">
            <div className="card-header">
              <span>Persistence & Queue</span>
              <Database size={18} />
            </div>
            <div className="card-value">Postgres + Redis</div>
          </div>
        </div>

        <div className="card">
          <h2 style={{ fontSize: '1.2rem', marginBottom: '0.75rem', color: '#f8fafc' }}>
            System Scaffold Status
          </h2>
          <p style={{ color: '#94a3b8', lineHeight: '1.6' }}>
            Monorepo packages successfully initialized. Docker Compose services for PostgreSQL and Redis are ready for local orchestration.
          </p>
        </div>
      </main>
    </div>
  );
};

export default App;
