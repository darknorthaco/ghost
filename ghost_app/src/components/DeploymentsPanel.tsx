import { useState, useEffect } from 'react';
import { getGhostHealth, loadLlmConfig } from '../utils/tauri';

type ComponentStatus = 'running' | 'stopped' | 'error' | 'unknown';

interface ComponentEntry {
  name: string;
  version: string;
  status: ComponentStatus;
  detail?: string;
}

function badgeClass(status: ComponentStatus): string {
  return status === 'running' ? 'active' : 'offline';
}

function badgeLabel(entry: ComponentEntry): string {
  if (entry.status === 'unknown') return 'Checking…';
  return entry.detail ?? (entry.status === 'running' ? 'Running' : 'Stopped');
}

export default function DeploymentsPanel() {
  const [components, setComponents] = useState<ComponentEntry[]>([
    { name: 'GHOST API', version: '—', status: 'unknown' },
    { name: 'Engine metrics', version: '—', status: 'unknown' },
    { name: 'LLM / execution config', version: '—', status: 'unknown' },
  ]);
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<string>('');

  const refresh = async () => {
    setLoading(true);
    const updated: ComponentEntry[] = [
      { name: 'GHOST API', version: '—', status: 'unknown' },
      { name: 'Engine metrics', version: '—', status: 'unknown' },
      { name: 'LLM / execution config', version: '—', status: 'unknown' },
    ];

    try {
      const health = await getGhostHealth() as Record<string, unknown>;
      const st = health.status === 'ok' || health.status === 'healthy' ? 'running' : 'error';
      updated[0] = {
        name: 'GHOST API',
        version: typeof health.version === 'string' ? health.version : '0.1.0',
        status: st,
        detail: String(health.status ?? 'unknown'),
      };
    } catch {
      updated[0] = { ...updated[0], status: 'stopped', detail: 'Not reachable' };
    }

    try {
      const resp = await fetch('http://127.0.0.1:8765/v1/metrics', { signal: AbortSignal.timeout(2_000) });
      const m = resp.ok ? await resp.json() as Record<string, unknown> : null;
      updated[1] = {
        name: 'Engine metrics',
        version: 'v1',
        status: resp.ok && m ? 'running' : 'stopped',
        detail: m
          ? `retrieve_total=${m.retrieve_total ?? '—'} p95=${m.retrieve_latency_ms_p95 ?? '—'}ms`
          : 'Unavailable',
      };
    } catch {
      updated[1] = { ...updated[1], status: 'stopped', detail: 'Unavailable' };
    }

    try {
      const cfg = await loadLlmConfig() as Record<string, unknown>;
      const model = typeof cfg.model === 'string' ? cfg.model : '—';
      const mode = typeof cfg.execution_mode === 'string' ? cfg.execution_mode : 'manual';
      updated[2] = {
        name: 'LLM / execution config',
        version: '1.0.0',
        status: 'running',
        detail: `${model} / ${mode}`,
      };
    } catch {
      updated[2] = { ...updated[2], status: 'stopped', detail: 'Not configured' };
    }

    setComponents(updated);
    setLastChecked(new Date().toLocaleTimeString());
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Deployments</span>
        <button className="console-send-btn" onClick={refresh} disabled={loading}>
          {loading ? 'Checking…' : 'Refresh'}
        </button>
      </div>

      <div className="card">
        <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Active Deployment</span>
          {lastChecked && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 'normal' }}>
              Last checked: {lastChecked}
            </span>
          )}
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Version</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {components.map(c => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{c.version}</td>
                <td>
                  <span className={`status-badge ${badgeClass(c.status)}`}>
                    {badgeLabel(c)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
