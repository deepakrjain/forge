import React from 'react';
import { Skull } from 'lucide-react';

export const DlqPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dead Letter Queue</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Jobs that have exhausted all retry attempts
        </p>
      </div>

      <div className="rounded-xl border border-border bg-bg-secondary p-10 flex flex-col items-center gap-4">
        <Skull className="w-10 h-10 text-text-muted" />
        <p className="text-sm text-text-muted">
          DLQ management will be implemented in Phase 7b.
        </p>
      </div>
    </div>
  );
};
