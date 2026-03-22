import { useState, useEffect, useRef } from 'react';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { runDeploymentPreScan } from '../utils/tauri';
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
                maxWidth: 480,
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
          <button className="deploy-btn" onClick={handleDeploy} disabled={deploying}>
            Deploy GHOST
          </button>
        </>
      )}
    </div>
  );
}
