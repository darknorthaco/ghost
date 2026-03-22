import { useState, useEffect } from 'react';

const API = 'http://127.0.0.1:8765';

/** Governance POST /v1/admin/* requires policy headers — UI is read-only for bandit snapshot. */
export default function RoutingPanel() {
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/v1/bandit/global`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((d) => {
        setSnapshot(d);
        setErr(null);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Routing &amp; optimizer</span>
      </div>

      <div className="card">
        <div className="card-title">Bandit snapshot (global)</div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.6 }}>
          Retrieval preset selection uses Thompson sampling. Administrative actions (bandit reset,
          hybrid invalidate, FTS rebuild) require governance approval via{' '}
          <code style={{ fontSize: 11 }}>POST /v1/admin/*</code> with policy headers — not exposed
          here to preserve stewardship gates.
        </p>
      </div>

      {err && (
        <div className="empty-state" style={{ color: 'var(--accent-crimson)' }}>
          Could not load bandit: {err}
        </div>
      )}

      {snapshot && (
        <div className="card">
          <div className="card-title">GET /v1/bandit/global</div>
          <pre
            style={{
              color: 'var(--text-secondary)',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              whiteSpace: 'pre-wrap',
            }}
          >
            {JSON.stringify(snapshot, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
