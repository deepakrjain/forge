import React, { useState, useCallback } from 'react';
import { X, Send, ChevronDown } from 'lucide-react';
import { createJob } from '../lib/api';
import type { CreateJobBody } from '../lib/types';

/**
 * SubmitJobModal — Modal for creating new jobs.
 *
 * Features:
 *  - Job type dropdown (send_email, resize_image, generate_report)
 *  - JSON payload textarea with validation
 *  - Priority selector (0–10)
 *  - Idempotency key auto-generated (user can override)
 *  - Submit calls POST /jobs and reports success/error
 */

interface SubmitJobModalProps {
  isOpen: boolean;
  onClose: () => void;
  onJobCreated: () => void;
}

const JOB_TYPES = ['send_email', 'resize_image', 'generate_report'] as const;

const DEFAULT_PAYLOADS: Record<string, string> = {
  send_email: JSON.stringify({ to: 'user@example.com', subject: 'Hello', body: 'World' }, null, 2),
  resize_image: JSON.stringify({ url: 'https://example.com/image.jpg', width: 800, height: 600 }, null, 2),
  generate_report: JSON.stringify({ report_type: 'monthly', month: '2026-08' }, null, 2),
};

function generateIdempotencyKey(): string {
  return `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export const SubmitJobModal: React.FC<SubmitJobModalProps> = ({
  isOpen,
  onClose,
  onJobCreated,
}) => {
  const [jobType, setJobType] = useState<string>(JOB_TYPES[0]);
  const [payload, setPayload] = useState(DEFAULT_PAYLOADS[JOB_TYPES[0]]);
  const [priority, setPriority] = useState(0);
  const [idempotencyKey, setIdempotencyKey] = useState(generateIdempotencyKey);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const validateJson = useCallback((value: string): boolean => {
    try {
      JSON.parse(value);
      setJsonError(null);
      return true;
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'Invalid JSON');
      return false;
    }
  }, []);

  const handleJobTypeChange = (type: string) => {
    setJobType(type);
    setPayload(DEFAULT_PAYLOADS[type] || '{}');
    setJsonError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!validateJson(payload)) return;

    setIsSubmitting(true);
    try {
      const body: CreateJobBody = {
        job_type: jobType,
        payload: JSON.parse(payload),
        idempotency_key: idempotencyKey,
        priority,
      };
      await createJob(body);

      // Reset form for next submission
      setIdempotencyKey(generateIdempotencyKey());
      setPayload(DEFAULT_PAYLOADS[jobType] || '{}');
      setPriority(0);
      setError(null);
      onJobCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 rounded-xl border border-border bg-bg-secondary shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">Submit Job</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-5">
          {/* Job Type */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text-secondary uppercase tracking-wider">
              Job Type
            </label>
            <div className="relative">
              <select
                value={jobType}
                onChange={(e) => handleJobTypeChange(e.target.value)}
                className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-3 py-2.5
                           text-sm text-text-primary focus:border-accent focus:outline-none focus:ring-1
                           focus:ring-accent transition-colors cursor-pointer"
              >
                {JOB_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
            </div>
          </div>

          {/* Payload */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text-secondary uppercase tracking-wider">
              Payload (JSON)
            </label>
            <textarea
              value={payload}
              onChange={(e) => {
                setPayload(e.target.value);
                validateJson(e.target.value);
              }}
              rows={5}
              className={`w-full rounded-lg border bg-bg-primary px-3 py-2.5 text-sm text-text-primary
                         font-mono resize-y focus:outline-none focus:ring-1 transition-colors
                         ${jsonError
                           ? 'border-status-failed focus:border-status-failed focus:ring-status-failed'
                           : 'border-border focus:border-accent focus:ring-accent'
                         }`}
              spellCheck={false}
            />
            {jsonError && (
              <p className="text-xs text-status-failed">{jsonError}</p>
            )}
          </div>

          {/* Priority */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text-secondary uppercase tracking-wider">
              Priority
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={10}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                className="flex-1 accent-accent h-1.5"
              />
              <span className="w-8 text-center text-sm font-mono text-text-primary bg-bg-primary
                              border border-border rounded-md py-1">
                {priority}
              </span>
            </div>
            <p className="text-xs text-text-muted">0 = lowest, 10 = highest</p>
          </div>

          {/* Idempotency Key */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-text-secondary uppercase tracking-wider">
              Idempotency Key
            </label>
            <input
              type="text"
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-sm
                         text-text-primary font-mono focus:border-accent focus:outline-none
                         focus:ring-1 focus:ring-accent transition-colors"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-status-failed/30 bg-status-failed/10 px-4 py-3">
              <p className="text-sm text-status-failed">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary
                         hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !!jsonError}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         bg-accent text-white hover:bg-accent-hover disabled:opacity-50
                         disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
              {isSubmitting ? 'Submitting…' : 'Submit Job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
