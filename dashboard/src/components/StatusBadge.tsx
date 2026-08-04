import React from 'react';
import type { JobStatus } from '../lib/types';

/**
 * StatusBadge — Renders a pill-shaped badge with semantic color for each job status.
 *
 * Uses the CSS utility classes from index.css (.status-badge, .status-*)
 * which map to the @theme design tokens. The "running" status gets a
 * pulsing dot animation via CSS keyframes.
 */

interface StatusBadgeProps {
  status: JobStatus;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  return (
    <span className={`status-badge status-${status} ${className}`}>
      {status}
    </span>
  );
};
