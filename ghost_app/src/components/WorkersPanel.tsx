import { useState, useEffect, useRef } from 'react';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { scanAndRegisterWorkers } from '../utils/tauri';

const API = 'http://127.0.0.1:8765';

interface BanditArm {
  preset_id: string;
  alpha: number;
  beta: number;
  mean: number;
  pulls: number;
  total_reward: number;
}

/** Preset arms from GET /v1/bandit/{scope} — Thompson sampling posteriors. */
export default function WorkersPanel() {
  const [arms, setArms] = useState<BanditArm[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [scanLog, setScanLog] = useState<string[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  const fetchBandit = () => {
    setLoading(true);
    setScanResult(null);
    fetch(`${API}/v1/bandit/global`)
      .then((r) => r.json())
      .then((d) => {
        setArms(Array.isArray(d.arms) ? d.arms : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  const runScan = () => {
    setScanning(true);
    setScanResult(null);
    setScanLog([]);
    scanAndRegisterWorkers()
      .then((r) => {
        setScanning(false);
        setScanResult(
          `Scanned ${r.scanned} node(s), registered ${r.registered} worker(s)`
        );
        fetchBandit();
      })
      .catch((e) => {
        setScanning(false);
        setScanResult(`Scan failed: ${e}`);
      });
  };

  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    listen<string>('scan-log', (event) => {
      setScanLog((prev) => [...prev, event.payload]);
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [scanLog]);

  useEffect(() => {
    fetchBandit();
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Bandit (global scope)</span>
        <button
          className="console-send-btn"
          onClick={runScan}
          disabled={scanning}
          title="Optional: scan LAN for distributed workers (legacy fabric)"
        >
          {scanning ? 'Scanning…' : 'Scan LAN'}
        </button>
        <button className="console-send-btn" onClick={fetchBandit}>
          Refresh
        </button>
      </div>
      {scanResult && (
        <div className="scan-result" style={{ fontSize: '0.85em', marginBottom: 8 }}>
          {scanResult}
        </div>
      )}
      {scanning && (
        <div
          className="scan-log"
          style={{
            marginBottom: 12,
            maxHeight: 180,
            overflow: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            padding: 8,
            background: 'rgba(0,0,0,0.2)',
            borderRadius: 4,
            textAlign: 'left',
          }}
        >
          {scanLog.length > 0 ? (
            scanLog.map((line, i) => (
              <div key={i} style={{ marginBottom: 2 }}>
                {line}
              </div>
            ))
          ) : (
            <div style={{ opacity: 0.7 }}>Scanning…</div>
          )}
          <div ref={logEndRef} />
        </div>
      )}

      {loading ? (
        <div className="empty-state">Loading bandit snapshot…</div>
      ) : arms.length === 0 ? (
        <div className="empty-state">
          No bandit arms yet. Start the GHOST API and ingest corpus data, or check optimizer scope.
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Preset</th>
              <th>Mean</th>
              <th>Pulls</th>
              <th>α</th>
              <th>β</th>
              <th>Total reward</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((a) => (
              <tr key={a.preset_id}>
                <td style={{ fontFamily: 'var(--font-mono)' }}>{a.preset_id}</td>
                <td>{a.mean?.toFixed?.(4) ?? '—'}</td>
                <td>{a.pulls}</td>
                <td>{a.alpha?.toFixed?.(3) ?? '—'}</td>
                <td>{a.beta?.toFixed?.(3) ?? '—'}</td>
                <td>{a.total_reward?.toFixed?.(4) ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
