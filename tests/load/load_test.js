/**
 * Forge Load Test — POST /jobs Burst Test.
 *
 * Uses autocannon to blast the POST /jobs endpoint with concurrent requests.
 * Measures throughput (req/sec), latency distributions (p50, p99), and error rates.
 *
 * Prerequisites:
 *   - API server running on http://localhost:8000
 *   - Postgres and Redis running via docker compose up -d
 *
 * Usage:
 *   node tests/load/load_test.js
 *
 * Or use npx directly:
 *   npx autocannon -c 10 -d 30 -m POST -H "X-API-Key=forge_dev_key_123" \
 *     -H "Content-Type=application/json" \
 *     -b '{"job_type":"send_email","payload":{},"idempotency_key":"UNIQUE","priority":0}' \
 *     http://localhost:8000/api/jobs
 */

const autocannon = require('autocannon');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const TARGET_URL = process.env.API_URL || 'http://localhost:8000/api/jobs';
const DURATION = parseInt(process.env.DURATION || '30', 10);   // seconds
const CONNECTIONS = parseInt(process.env.CONNECTIONS || '10', 10);
const PIPELINE = parseInt(process.env.PIPELINE || '1', 10);

console.log('╔══════════════════════════════════════════════════════════╗');
console.log('║            Forge Load Test — POST /jobs Burst           ║');
console.log('╠══════════════════════════════════════════════════════════╣');
console.log(`║  Target:      ${TARGET_URL.padEnd(41)}║`);
console.log(`║  Duration:    ${(DURATION + 's').padEnd(41)}║`);
console.log(`║  Connections: ${String(CONNECTIONS).padEnd(41)}║`);
console.log(`║  Pipeline:    ${String(PIPELINE).padEnd(41)}║`);
console.log('╚══════════════════════════════════════════════════════════╝');
console.log();

const instance = autocannon({
  url: TARGET_URL,
  connections: CONNECTIONS,
  duration: DURATION,
  pipelining: PIPELINE,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'forge_dev_key_123',
  },
  // Generate a unique body per request to bypass idempotency
  setupClient(client) {
    client.setBody(JSON.stringify({
      job_type: 'send_email',
      payload: { to: 'loadtest@forge.io', subject: 'Load Test' },
      idempotency_key: `load_${crypto.randomUUID()}`,
      priority: Math.floor(Math.random() * 10),
    }));
  },
  // Re-generate body before each request
  requests: [
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': 'forge_dev_key_123',
      },
      setupRequest(req, context) {
        req.body = JSON.stringify({
          job_type: 'send_email',
          payload: { to: 'loadtest@forge.io', subject: 'Load Test' },
          idempotency_key: `load_${crypto.randomUUID()}`,
          priority: Math.floor(Math.random() * 10),
        });
        return req;
      },
    },
  ],
}, (err, result) => {
  if (err) {
    console.error('Load test error:', err);
    process.exit(1);
  }

  // Print human-readable summary
  const summary = [
    '# Forge Load Test Results',
    '',
    `**Date:** ${new Date().toISOString()}`,
    `**Target:** ${TARGET_URL}`,
    `**Duration:** ${DURATION}s`,
    `**Connections:** ${CONNECTIONS}`,
    `**Pipeline:** ${PIPELINE}`,
    '',
    '## Throughput',
    '',
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Total Requests | ${result.requests.total} |`,
    `| Avg Req/sec | ${result.requests.average} |`,
    `| Min Req/sec | ${result.requests.min} |`,
    `| Max Req/sec | ${result.requests.max} |`,
    `| Total Data | ${(result.throughput.total / 1024).toFixed(1)} KB |`,
    '',
    '## Latency (ms)',
    '',
    `| Percentile | Value |`,
    `|------------|-------|`,
    `| p50 (Median) | ${result.latency.p50} ms |`,
    `| p90 | ${result.latency.p90} ms |`,
    `| p99 | ${result.latency.p99} ms |`,
    `| p999 | ${result.latency.p999} ms |`,
    `| Avg | ${result.latency.average} ms |`,
    `| Min | ${result.latency.min} ms |`,
    `| Max | ${result.latency.max} ms |`,
    '',
    '## Status Codes',
    '',
    `| Code | Count |`,
    `|------|-------|`,
  ];

  // Add status code breakdown
  if (result.statusCodeStats) {
    for (const [code, stats] of Object.entries(result.statusCodeStats)) {
      summary.push(`| ${code} | ${stats.count} |`);
    }
  }

  summary.push('');
  summary.push(`## Errors`);
  summary.push('');
  summary.push(`| Metric | Value |`);
  summary.push(`|--------|-------|`);
  summary.push(`| Timeouts | ${result.timeouts} |`);
  summary.push(`| Non-2xx | ${result.non2xx} |`);
  summary.push(`| Errors | ${result.errors} |`);
  summary.push('');

  const markdownContent = summary.join('\n');

  // Print to console
  console.log('\n' + markdownContent);

  // Also print the autocannon default table
  console.log('\n--- Raw autocannon output ---');
  console.log(autocannon.printResult(result));

  // Save to file
  const outputPath = path.join(__dirname, '..', '..', 'docs', 'load_test_results.md');
  fs.writeFileSync(outputPath, markdownContent, 'utf-8');
  console.log(`\n✅ Results saved to: ${outputPath}`);
});

// Track progress
autocannon.track(instance, { renderProgressBar: true });
