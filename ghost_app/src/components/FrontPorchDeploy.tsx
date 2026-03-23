import { useState, useEffect, useRef } from 'react';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { predictivePreflightCheck, runDeploymentPreScan } from '../utils/tauri';
import type { PreflightReport, PredictionResult } from '../utils/tauri';
import type { DeploymentPreScanResult } from '../state/deploymentState';
import '../styles/deploy.css';

interface DeployProgress {
  step: number;
  total_steps: number;
  label: string;
  fraction: number;
}

interface Props {
  /** Called when pre-scan completes; transitions to deployment ceremony. */
  onPreScanComplete: (result: DeploymentPreScanResult) => void;
}

function formatInvokeError(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function FrontPorchDeploy({ onPreScanComplete }: Props) {
  const [deploying, setDeploying] = useState(false);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [progress, setProgress] = useState<DeployProgress | null>(null);
  const [scanLog, setScanLog] = useState<string[]>([]);
  const [preflight, setPreflight] = useState<PreflightReport | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let unlistenProgress: UnlistenFn | undefined;
    let unlistenScan: UnlistenFn | undefined;

    listen<DeployProgress>('deploy-progress', (event) => {
      setProgress(event.payload);
      if (event.payload.label !== 'Scanning LAN' && event.payload.label !== 'Starting local worker') {
        setScanLog([]);
      }
    }).then((fn) => {
      unlistenProgress = fn;
    });

    listen<string>('scan-log', (event) => {
      setScanLog((prev) => [...prev, event.payload]);
    }).then((fn) => {
      unlistenScan = fn;
    });

    return () => {
      unlistenProgress?.();
      unlistenScan?.();
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [scanLog]);

  const handlePreflight = async () => {
    setPreflightLoading(true);
    setPreflightError(null);
    try {
      const r = await predictivePreflightCheck();
      setPreflight(r);
    } catch (err) {
      setPreflightError(formatInvokeError(err));
    } finally {
      setPreflightLoading(false);
    }
  };

  const handleDeploy = async () => {
    setDeploying(true);
    setDeployError(null);
    setScanLog([]);
    try {
      const result = await runDeploymentPreScan();
      onPreScanComplete(result);
    } catch (err) {
      console.error('Pre-scan failed:', err);
      setDeployError(formatInvokeError(err));
      setDeploying(false);
    }
  };

  const pct = progress ? Math.round(progress.fraction * 100) : 0;
  const showScanLog =
    deploying && (progress?.label === 'Scanning LAN' || progress?.label === 'Starting local worker');

  const deployFails = (preflight?.predictions ?? [])
    .filter((p) => p.domain === 'deploy' && p.outcome === 'likely_fail')
    .sort((a, b) => b.predictiveP - a.predictiveP);
  const workersDown = (preflight?.predictions ?? []).filter(
    (p) => p.domain === 'worker' && p.outcome === 'likely_down'
  );
  const discoveryPred = (preflight?.predictions ?? []).find((p) => p.domain === 'discovery');
  const routingPred = (preflight?.predictions ?? []).find((p) => p.domain === 'routing');

  return (
    <div className="deploy-screen">
      <div className="ghost-mask-container">
        <img src="/ghost.svg" alt="GHOST" className="ghost-mask-svg" />
      </div>

      <div className="deploy-title">
        {deploying ? 'GHOST Awakening' : 'GHOST Awaits'}
      </div>

      {deploying ? (
        <div className="loading-bar-container">
          <div className="loading-bar-track">
            <div className="loading-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="micro-status">
            {progress?.label || 'Initializing…'}
          </div>
          {showScanLog && scanLog.length > 0 && (
            <div
              className="scan-log"
              style={{
                marginTop: 12,
                maxHeight: 160,
                overflow: 'auto',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                padding: 8,
                background: 'rgba(0,0,0,0.25)',
                borderRadius: 4,
                textAlign: 'left',
              }}
            >
              {scanLog.map((line, i) => (
                <div key={i} style={{ marginBottom: 2 }}>
                  {line}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      ) : (
        <>
          {deployError && (
            <div
              className="deploy-error"
              style={{
                maxWidth: 520,
                margin: '0 auto 16px',
                padding: 12,
                fontSize: 12,
                lineHeight: 1.45,
                textAlign: 'left',
                color: '#ffb4b4',
                background: 'rgba(180, 40, 40, 0.2)',
                border: '1px solid rgba(255, 80, 80, 0.35)',
                borderRadius: 6,
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {deployError}
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
            <button className="deploy-btn" onClick={handleDeploy} disabled={deploying}>
              Deploy GHOST
            </button>
            <button
              type="button"
              className="deploy-btn"
              style={{ opacity: 0.85, fontSize: 12, padding: '8px 16px' }}
              onClick={handlePreflight}
              disabled={deploying || preflightLoading}
            >
              {preflightLoading ? 'Preflight…' : 'Preflight Check'}
            </button>
            {preflightError && (
              <div
                style={{
                  maxWidth: 520,
                  fontSize: 11,
                  color: '#ffb4b4',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {preflightError}
              </div>
            )}
            {preflight && (
              <div
                className="preflight-panel"
                style={{
                  maxWidth: 560,
                  marginTop: 8,
                  padding: 12,
                  textAlign: 'left',
                  fontSize: 11,
                  lineHeight: 1.4,
                  background: 'rgba(30, 30, 45, 0.6)',
                  borderRadius: 8,
                  border: '1px solid rgba(120, 120, 180, 0.25)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                <div style={{ marginBottom: 8, opacity: 0.9 }}>
                  Preflight (informational only — no deploy changes)
                </div>
                <div style={{ marginBottom: 6 }}>
                  <strong>Likely fail steps</strong> (by risk p)
                  {deployFails.length === 0 ? (
                    <span style={{ opacity: 0.7 }}> — none flagged</span>
                  ) : (
                    <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                      {deployFails.map((p: PredictionResult, i: number) => (
                        <li key={i}>
                          step {p.context.stepIndex ?? '?'} p={p.predictiveP.toFixed(2)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div style={{ marginBottom: 6 }}>
                  <strong>Likely down workers</strong>
                  {workersDown.length === 0 ? (
                    <span style={{ opacity: 0.7 }}> — none flagged</span>
                  ) : (
                    <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                      {workersDown.map((p: PredictionResult, i: number) => (
                        <li key={i}>
                          {p.context.workerId ?? '?'} failure_p={p.predictiveP.toFixed(2)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div style={{ marginBottom: 6 }}>
                  <strong>Discovery risk</strong>
                  {discoveryPred ? (
                    <span>
                      {' '}
                      {discoveryPred.outcome} (p={discoveryPred.predictiveP.toFixed(2)})
                    </span>
                  ) : (
                    <span style={{ opacity: 0.7 }}> — n/a</span>
                  )}
                </div>
                <div>
                  <strong>Routing instability</strong>
                  {routingPred ? (
                    <span>
                      {' '}
                      {routingPred.outcome} (p={routingPred.predictiveP.toFixed(2)})
                    </span>
                  ) : (
                    <span style={{ opacity: 0.7 }}> — n/a</span>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
