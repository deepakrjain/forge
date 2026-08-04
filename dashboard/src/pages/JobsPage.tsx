import React from 'react';
import { ListTodo } from 'lucide-react';

export const JobsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Jobs</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Browse, filter, and inspect all queued and processed jobs
        </p>
      </div>

      <div className="rounded-xl border border-border bg-bg-secondary p-10 flex flex-col items-center gap-4">
        <ListTodo className="w-10 h-10 text-text-muted" />
        <p className="text-sm text-text-muted">
          Job listing and filtering will be implemented in Phase 7b.
        </p>
      </div>
    </div>
  );
};
