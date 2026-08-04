import React from 'react';
import { Cpu } from 'lucide-react';

export const WorkersPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Workers</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Monitor active worker processes and concurrency utilization
        </p>
      </div>

      <div className="rounded-xl border border-border bg-bg-secondary p-10 flex flex-col items-center gap-4">
        <Cpu className="w-10 h-10 text-text-muted" />
        <p className="text-sm text-text-muted">
          Worker monitoring will be implemented in a future phase.
        </p>
      </div>
    </div>
  );
};
