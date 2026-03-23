use std::path::{Path, PathBuf};
use tauri::Emitter;
use tokio::process::Command;

use super::hide_console::hide_child_console;
use super::discovery::{
    self, base_to_broadcast, discover_workers_with_log, DEFAULT_DISCOVERY_TOTAL_TIMEOUT_MS,
};
use super::discovery_log::{DependencyInitEntry, DiscoveryLog, DiscoveryLogBuilder, FullDeployLogEntry};
use super::ghost_api::{GhostApiClient, RegisterWorkerRequest};

#[derive(Debug, Clone, serde::Serialize)]
pub struct DeployStep {
    pub index: usize,
    pub label: String,
    pub status: String,
}

/// Worker representation for deployment ceremony (frontend display).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoveredWorkerForCeremony {
    pub worker_id: String,
    pub host: String,
    pub port: u16,
    pub gpu_info: serde_json::Value,
    pub source_ip: String,
    pub signature_verified: bool,
    pub fingerprint: String,
    /// Base64 Ed25519 public key — required for §5 TrustRecord(approved).
    pub public_key_b64: String,
}

/// Result of pre-scan deployment (steps 0–9 + discovery, no registration).
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeploymentPreScanResult {
    pub discovered_workers: Vec<DiscoveredWorkerForCeremony>,
    pub discovery_log: DiscoveryLog,
    /// True when worker_count == 0; blocks progression to TOC.
    pub discovery_failed: bool,
    /// True when deploy used an offline bundle (no PyPI, no LAN discovery).
    #[serde(default)]
    pub offline_mode: bool,
}

/// Worker selection for registration (from frontend).
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkerSelectionForRegistration {
    pub worker_id: String,
    pub host: String,
    pub port: u16,
    pub gpu_info: serde_json::Value,
    /// Base64 Ed25519 public key — required for §5 TrustRecord(approved).
    #[serde(default)]
    pub public_key_b64: String,
}

/// Request payload for complete_deployment_with_selection (camelCase for frontend).
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CompleteDeploymentRequest {
    pub worker_pool: Vec<WorkerSelectionForRegistration>,
    pub run_controller_llm: bool,
}

pub struct GhostDeployer {
    ghost_root: PathBuf,
    engine_source: PathBuf,
    /// When set, scan_lan emits "scan-log" events for in-app display.
    scan_log_emitter: Option<tauri::AppHandle>,
    /// Result of the local worker readiness probe: (attempts, success).
    /// Written by start_local_worker(), read by run_pre_scan_deployment().
    readiness_result: std::sync::Mutex<(u32, bool)>,
    /// When set, deploy uses wheelhouse + bundled engine; skips LAN discovery and remote-only steps.
    offline_bundle_path: Option<PathBuf>,
}

impl GhostDeployer {
    pub fn new(
        ghost_root: &Path,
        engine_source: &Path,
        scan_log_emitter: Option<tauri::AppHandle>,
    ) -> Self {
        Self {
            ghost_root: ghost_root.to_path_buf(),
            engine_source: engine_source.to_path_buf(),
            scan_log_emitter,
            readiness_result: std::sync::Mutex::new((0, false)),
            offline_bundle_path: None,
        }
    }

    /// Attach an offline bundle root (must contain manifest.json, wheelhouse/, engine/, …).
    #[must_use]
    pub fn with_offline_bundle(mut self, path: Option<PathBuf>) -> Self {
        if path.is_some() {
            log::warn!("GHOST OFFLINE MODE ENABLED — using offline bundle (no PyPI / no LAN discovery)");
        }
        self.offline_bundle_path = path;
        self
    }

    fn is_offline(&self) -> bool {
        self.offline_bundle_path.is_some()
    }

    fn emit_scan_log(&self, line: &str) {
        if let Some(ref app) = self.scan_log_emitter {
            let _ = app.emit("scan-log", line);
        }
    }

    /// Read discovery config from ghost_config.json.
    /// Falls back to DEFAULT_DISCOVERY_TOTAL_TIMEOUT_MS and true if unavailable.
    fn read_discovery_config(&self) -> (u64, bool) {
        let config_path = self.ghost_root.join("ghost_config.json");
        let total_timeout_ms = read_nested_config(&config_path, &["discovery", "total_timeout_ms"])
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(DEFAULT_DISCOVERY_TOTAL_TIMEOUT_MS);
        let early_exit = read_nested_config(&config_path, &["discovery", "early_exit_on_first_worker"])
            .and_then(|s| s.parse::<bool>().ok())
            .unwrap_or(true);
        (total_timeout_ms, early_exit)
    }

    fn emit_deploy_progress(&self, step: usize, total: usize, label: &str, fraction: f64) {
        if let Some(ref app) = self.scan_log_emitter {
            let progress = super::ghost_state::DeploymentProgress {
                step,
                total_steps: total,
                label: label.to_string(),
                fraction,
            };
            let _ = app.emit("deploy-progress", &progress);
        }
    }

    pub fn steps() -> Vec<&'static str> {
        vec![
            "Creating GHOST virtual environment",
            "Installing Python runtime",
            "Installing GHOST engine (editable)",
            "Verifying GPU plugins",
            "Installing GHOST service (optional)",
            "Bootstrapping config",          // Step 5 (§8 Step 4.5)
            "Starting GHOST API",
            "Opening ports",
            "Initializing state",
            "Starting local worker",
            "Scanning LAN",
            "Loading execution modes",
        ]
    }

    /// Repo root containing `config/default.yaml` (editable install, installer marker, or dev tree).
    fn ghost_engine_repo_root(&self) -> PathBuf {
        if let Ok(s) = std::env::var("GHOST_ENGINE_ROOT") {
            let p = PathBuf::from(s);
            if p.join("config").join("default.yaml").exists() {
                return p;
            }
        }
        let marker = self.ghost_root.join("engine_root.txt");
        if let Ok(s) = std::fs::read_to_string(&marker) {
            let p = PathBuf::from(s.trim());
            if p.join("config").join("default.yaml").exists() {
                return p;
            }
        }
        if let Some(parent) = self.engine_source.parent() {
            if parent.join("config").join("default.yaml").exists() {
                return parent.to_path_buf();
            }
        }
        let deployed = self.ghost_root.join("engine");
        if deployed.join("config").join("default.yaml").exists() {
            return deployed;
        }
        self.ghost_root.clone()
    }

    pub async fn run_step(&self, index: usize) -> Result<(), String> {
        match index {
            0 => self.create_venv().await,
            1 => self.install_python_deps().await,
            2 => self.install_ghost_core().await,
            3 => self.verify_gpu_plugins().await,
            4 => self.install_service().await,
            5 => self.bootstrap_config().await,  // §8 Step 4.5
            6 => self.start_controller().await,
            7 => self.open_ports().await,
            8 => self.initialize_state().await,
            9 => self.start_local_worker().await,
            10 => self.scan_lan().await,
            11 => self.load_execution_modes().await,
            _ => Err("Unknown deployment step".to_string()),
        }
    }

    async fn create_venv(&self) -> Result<(), String> {
        let venv_path = self.ghost_root.join("venv");
        tokio::fs::create_dir_all(&self.ghost_root)
            .await
            .map_err(|e| format!("Failed to create ghost root: {e}"))?;

        // On Windows the launcher is "python", on Unix "python3"
        #[cfg(target_os = "windows")]
        let py_cmd = "python";
        #[cfg(not(target_os = "windows"))]
        let py_cmd = "python3";

        let mut cmd = Command::new(py_cmd);
        cmd.args(["-m", "venv", &venv_path.to_string_lossy()]);
        hide_child_console(&mut cmd);
        let output = cmd
            .output()
            .await
            .map_err(|e| format!("Failed to create venv: {e}"))?;

        if !output.status.success() {
            return Err(format!(
                "venv creation failed: {}",
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        Ok(())
    }

    async fn install_python_deps(&self) -> Result<(), String> {
        let pip = venv_pip(&self.ghost_root);

        if let Some(ref bundle) = self.offline_bundle_path {
            let wheelhouse = bundle.join("wheelhouse");
            let req = bundle.join("requirements-deploy.txt");
            if !wheelhouse.is_dir() {
                return Err(format!(
                    "Offline bundle missing wheelhouse/: {:?}",
                    wheelhouse
                ));
            }
            if !req.is_file() {
                return Err(format!(
                    "Offline bundle missing requirements-deploy.txt under {:?}",
                    bundle
                ));
            }
            log::info!(
                "Installing Python deps from offline wheelhouse (no network): {:?}",
                wheelhouse
            );
            let find_links = format!("--find-links={}", wheelhouse.to_string_lossy());
            let req_s = req.to_string_lossy().to_string();
            let mut cmd = Command::new(pip.to_string_lossy().as_ref());
            cmd.args([
                "install",
                "--no-index",
                &find_links,
                "-r",
                &req_s,
            ]);
            hide_child_console(&mut cmd);
            let output = cmd
                .output()
                .await
                .map_err(|e| format!("pip install (offline) failed: {e}"))?;

            if !output.status.success() {
                return Err(format!(
                    "pip install (offline) failed: {}",
                    String::from_utf8_lossy(&output.stderr)
                ));
            }
            return Ok(());
        }

        let engine_root = self.ghost_engine_repo_root();
        let req = engine_root.join("requirements.txt");

        if !req.exists() {
            return Err(format!(
                "requirements.txt not found at {:?} (engine root {:?}). \
                 Set GHOST_ENGINE_ROOT to your repo root, or ensure ~/.ghost/engine_root.txt points at the engine.",
                req,
                engine_root
            ));
        }

        let spec = format!("{}[embeddings]", engine_root.to_string_lossy());
        let mut cmd = Command::new(pip.to_string_lossy().as_ref());
        cmd.args(["install", "--no-cache-dir", "-e", &spec])
            .current_dir(&engine_root);
        hide_child_console(&mut cmd);
        let output = cmd
            .output()
            .await
            .map_err(|e| format!("pip install -e ghost failed: {e}"))?;

        if !output.status.success() {
            return Err(format!(
                "pip install -e ghost failed: {}",
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        Ok(())
    }

    async fn install_ghost_core(&self) -> Result<(), String> {
        let repo = self.ghost_engine_repo_root();
        if repo.join("config").join("default.yaml").exists() {
            log::info!(
                "GHOST engine available via editable install at {:?} — skipping engine copy",
                repo
            );
            return Ok(());
        }

        let dest = self.ghost_root.join("engine");

        if dest.join("pyproject.toml").exists() || dest.join("config").join("default.yaml").exists() {
            log::info!("GHOST engine already present at {:?} — skipping copy", dest);
            return Ok(());
        }

        let src: PathBuf = if let Some(ref bundle) = self.offline_bundle_path {
            let be = bundle.join("engine");
            if be.join("pyproject.toml").is_file() {
                log::info!("Using GHOST engine from offline bundle at {:?}", be);
                be
            } else {
                self.engine_source.clone()
            }
        } else {
            self.engine_source.clone()
        };

        if src == dest {
            return Ok(());
        }

        log::info!("Copying GHOST engine from {:?} → {:?}", src, dest);

        copy_dir_all(&src, &dest)
            .await
            .map_err(|e| format!("Failed to install GHOST engine: {e}"))?;

        log::info!("GHOST engine installed successfully");
        Ok(())
    }

    async fn verify_gpu_plugins(&self) -> Result<(), String> {
        #[cfg(target_os = "linux")]
        {
            let gpus = super::linux::gpu_detection::detect_nvidia_gpus().await;
            if gpus.is_empty() {
                log::info!("No NVIDIA GPUs detected — GPU plugins inactive (CPU-only mode)");
            } else {
                log::info!("Detected {} NVIDIA GPU(s): {}", gpus.len(), gpus[0].name);
            }
        }
        #[cfg(target_os = "windows")]
        {
            let gpus = super::windows::gpu_detection::detect_gpus().await;
            if gpus.is_empty() {
                log::info!("No GPUs detected — GPU plugins inactive (CPU-only mode)");
            } else {
                log::info!("Detected {} GPU(s): {}", gpus.len(), gpus[0].name);
            }
        }
        Ok(())
    }

    async fn install_service(&self) -> Result<(), String> {
        let working_dir = self.ghost_engine_repo_root();

        #[cfg(target_os = "linux")]
        {
            let python = venv_python(&self.ghost_root);
            let unit = super::linux::systemd_installer::generate_unit_file(
                &whoami_or_root(),
                &python,
                &working_dir,
            );

            // Try user-level systemd (no root required) first
            let user_systemd = home_dir().join(".config/systemd/user");
            tokio::fs::create_dir_all(&user_systemd)
                .await
                .map_err(|e| format!("Failed to create systemd user dir: {e}"))?;

            let unit_path = user_systemd.join("ghost.service");
            tokio::fs::write(&unit_path, &unit)
                .await
                .map_err(|e| format!("Failed to write unit file: {e}"))?;

            log::info!("Written systemd unit to {:?}", unit_path);

            // daemon-reload for user session
            let reload = Command::new("systemctl")
                .args(["--user", "daemon-reload"])
                .output()
                .await;

            match reload {
                Ok(out) if out.status.success() => {
                    // Enable the user service (don't fail if this errors — not all environments support it)
                    let _ = Command::new("systemctl")
                        .args(["--user", "enable", "ghost"])
                        .output()
                        .await;
                    log::info!("GHOST systemd user service enabled");
                }
                _ => {
                    log::warn!("systemctl --user daemon-reload unavailable; service file written but not enabled");
                }
            }
        }

        #[cfg(target_os = "windows")]
        {
            let python_win = self.ghost_root.join("venv\\Scripts\\python.exe");
            match super::windows::service_installer::install_uvicorn_service(
                "ghost",
                "GHOST API",
                &python_win,
                &working_dir,
                "127.0.0.1",
                8765,
            )
            .await
            {
                Ok(()) => log::info!("GHOST Windows service installed"),
                Err(e) => log::warn!("Windows service install failed (may already exist): {e}"),
            }
        }

        #[cfg(not(any(target_os = "linux", target_os = "windows")))]
        {
            log::info!("Service installation skipped on this platform");
            let _ = &working_dir;
        }

        Ok(())
    }

    /// §8 Step 4.5 — write ghost_config.json atomically before the controller starts.
    ///
    /// Reads ControllerPlacementParams from §1 Pre-0 ceremony (controller_placement.json).
    /// Writes the full corrected schema to ghost_config.json using an atomic tmp → rename.
    /// A timestamped backup of any pre-existing ghost_config.json is preserved.
    ///
    /// This step MUST succeed before `start_controller` (Step 6) runs.
    async fn bootstrap_config(&self) -> Result<(), String> {
        let config_path = self.ghost_root.join("ghost_config.json");
        let placement_path = self.ghost_root.join("controller_placement.json");

        // §1 — ControllerPlacementParams must exist (Pre-0 ceremony completed).
        if !placement_path.exists() {
            return Err(
                "Pre-0 Controller Selection Ceremony required. \
                 Complete the controller placement screen before deploying."
                    .to_string(),
            );
        }

        let placement_raw = tokio::fs::read_to_string(&placement_path)
            .await
            .map_err(|e| format!("Failed to read controller_placement.json: {e}"))?;
        let placement: serde_json::Value =
            serde_json::from_str(&placement_raw).map_err(|e| format!("Invalid controller_placement.json: {e}"))?;
        let host = placement
            .get("host")
            .and_then(|v| v.as_str())
            .unwrap_or("127.0.0.1")
            .to_string();
        let port = placement.get("port").and_then(|v| v.as_u64()).unwrap_or(8765) as u16;
        let identity_fingerprint = placement
            .get("identity_fingerprint")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        // Preserve any existing config as a timestamped backup.
        if config_path.exists() {
            let ts = chrono::Utc::now().format("%Y%m%dT%H%M%SZ").to_string();
            let backup = self.ghost_root.join(format!("ghost_config.json.bak.{ts}"));
            tokio::fs::rename(&config_path, &backup)
                .await
                .map_err(|e| format!("Failed to back up ghost_config.json: {e}"))?;
            log::info!("Backed up ghost_config.json → {}", backup.display());
        }

        let now = chrono::Utc::now().to_rfc3339();
        let config = serde_json::json!({
            "controller": {
                "host": host,
                "port": port,
                "security": "disabled",
                "identity_fingerprint": identity_fingerprint,
                "socket_integrated": false
            },
            "ports": {
                "controller_api": { "port": port, "protocol": "tcp", "required": true  },
                "worker_http":    { "port": 8090, "protocol": "tcp", "required": true  },
                "discovery_udp":  { "port": 8095, "protocol": "udp", "required": true  },
                "socket_infra":   { "port": 8081, "protocol": "tcp", "required": false }
            },
            "worker": {
                "readiness_probe_interval_ms":  500,
                "readiness_max_attempts":       20,
                "readiness_attempt_timeout_ms": 1000
            },
            "discovery": {
                "total_timeout_ms":            10000,
                "early_exit_on_first_worker":  true
            },
            "execution_modes": {
                "default_mode": "manual"
            },
            "wan_mode": false,
            "tls_enabled": false,
            "tls_cert_path": "",
            "tls_key_path": "",
            "config_version":  "1.0",
            "written_at":      now,
            "written_by_step": "4.5"
        });

        let tmp_path = self.ghost_root.join("ghost_config.json.tmp");
        tokio::fs::write(
            &tmp_path,
            serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?,
        )
        .await
        .map_err(|e| format!("Failed to write ghost_config.json.tmp: {e}"))?;

        tokio::fs::rename(&tmp_path, &config_path)
            .await
            .map_err(|e| format!("Failed to rename ghost_config.json.tmp: {e}"))?;

        log::info!("ghost_config.json written at step 4.5 ({})", config_path.display());
        Ok(())
    }

    async fn start_controller(&self) -> Result<(), String> {
        let python = venv_python(&self.ghost_root);
        let working_dir = self.ghost_engine_repo_root();
        if !working_dir.join("config").join("default.yaml").exists() {
            return Err(format!(
                "GHOST engine root missing config/default.yaml: {:?}. \
                 Set GHOST_ENGINE_ROOT, write ~/.ghost/engine_root.txt, or complete pip install -e from the repo.",
                working_dir
            ));
        }

        let config_path = self.ghost_root.join("ghost_config.json");
        if !config_path.exists() {
            return Err(format!(
                "ghost_config.json not found at {:?}. \
                 Step 4.5 (Bootstrap config) must complete successfully before \
                 the GHOST API can start.",
                config_path
            ));
        }

        let host = read_nested_config(&config_path, &["controller", "host"])
            .unwrap_or_else(|| "127.0.0.1".to_string());
        let port = read_nested_config(&config_path, &["controller", "port"])
            .unwrap_or_else(|| "8765".to_string());

        let state_dir = self.ghost_root.join("state");
        tokio::fs::create_dir_all(&state_dir)
            .await
            .map_err(|e| format!("mkdir state: {e}"))?;

        log::info!(
            "Starting GHOST API (uvicorn) — host={} port={} cwd={:?}",
            host,
            port,
            working_dir
        );

        let mut cmd = Command::new(python.to_string_lossy().as_ref());
        cmd.args([
            "-m",
            "uvicorn",
            "ghost_api.app:app",
            "--host",
            &host,
            "--port",
            &port,
        ])
        .current_dir(&working_dir)
        .env(
            "GHOST_ENGINE_ROOT",
            working_dir.to_string_lossy().as_ref(),
        )
        .env("GHOST_STATE_DIR", state_dir.to_string_lossy().as_ref());
        hide_child_console(&mut cmd);
        cmd.spawn()
            .map_err(|e| format!("Failed to start GHOST API: {e}"))?;

        tokio::time::sleep(std::time::Duration::from_secs(3)).await;
        Ok(())
    }

    async fn open_ports(&self) -> Result<(), String> {
        let cfg_path = self.ghost_root.join("ghost_config.json");
        let api_port = read_nested_config(&cfg_path, &["controller", "port"])
            .unwrap_or_else(|| "8765".to_string());
        let socket_integrated = cfg_path
            .exists()
            .then(|| {
                read_nested_config(&cfg_path, &["controller", "socket_integrated"])
                    .and_then(|s| s.parse::<bool>().ok())
            })
            .flatten()
            .unwrap_or(false);

        #[cfg(target_os = "linux")]
        {
            let mut port_rules: Vec<(String, &'static str)> = vec![
                (api_port.clone(), "tcp"),
                ("8090".to_string(), "tcp"),
                ("8095".to_string(), "udp"),
            ];
            if socket_integrated {
                port_rules.push(("8081".to_string(), "tcp"));
                log::info!("Opening socket port 8081/tcp");
            }

            // Try ufw first (Ubuntu/Debian)
            let ufw_available = {
                let rule = format!("{}/tcp", api_port);
                let ufw = Command::new("ufw")
                    .args(["allow", &rule])
                    .output()
                    .await;
                matches!(ufw, Ok(ref o) if o.status.success())
            };

            if ufw_available {
                for (port, proto) in port_rules.iter().skip(1) {
                    let rule = format!("{}/{}", port, proto);
                    let _ = Command::new("ufw")
                        .args(["allow", &rule])
                        .output()
                        .await;
                }
                let ports_str = port_rules
                    .iter()
                    .map(|(p, pr)| format!("{p}/{pr}"))
                    .collect::<Vec<_>>()
                    .join(", ");
                log::info!("ufw: allowed ports {ports_str}");
                return Ok(());
            }

            log::info!("ufw not available, trying iptables");

            for (port, proto) in &port_rules {
                let ipt = Command::new("iptables")
                    .args(["-C", "INPUT", "-p", proto, "--dport", port.as_str(), "-j", "ACCEPT"])
                    .output()
                    .await;

                let already_open = matches!(ipt, Ok(ref o) if o.status.success());

                if !already_open {
                    let add = Command::new("iptables")
                        .args(["-A", "INPUT", "-p", proto, "--dport", port.as_str(), "-j", "ACCEPT"])
                        .output()
                        .await;

                    match add {
                        Ok(out) if out.status.success() => {
                            log::info!("iptables: opened port {port}/{proto}");
                        }
                        Ok(out) => {
                            log::warn!(
                                "iptables failed for {port}/{proto}: {}",
                                String::from_utf8_lossy(&out.stderr)
                            );
                        }
                        Err(e) => {
                            log::warn!("iptables not available: {e}");
                        }
                    }
                } else {
                    log::info!("Port {port}/{proto} already open in iptables");
                }
            }
        }

        #[cfg(target_os = "windows")]
        {
            let mut rules = vec![
                ("GhostController", "TCP", api_port.as_str()),
                ("GhostWorker", "TCP", "8090"),
                ("GhostDiscovery", "UDP", "8095"),
            ];
            if socket_integrated {
                rules.push(("GhostSocket", "TCP", "8081"));
                log::info!("Opening socket port 8081/tcp");
            }

            for &(name, proto, port) in &rules {
                let mut netsh = Command::new("netsh");
                netsh.args([
                    "advfirewall", "firewall", "add", "rule",
                    &format!("name={name}"),
                    "dir=in",
                    "action=allow",
                    &format!("protocol={proto}"),
                    &format!("localport={port}"),
                ]);
                hide_child_console(&mut netsh);
                let result = netsh.output().await;

                match result {
                    Ok(out) if out.status.success() => {
                        log::info!("Windows firewall: allowed port {port}/{proto} ({name})");
                    }
                    Ok(out) => {
                        log::warn!(
                            "netsh firewall rule failed for {name}: {}",
                            String::from_utf8_lossy(&out.stderr)
                        );
                    }
                    Err(e) => {
                        log::warn!("netsh not available: {e}");
                    }
                }
            }
        }

        Ok(())
    }

    async fn initialize_state(&self) -> Result<(), String> {
        let marker = self.ghost_root.join("deployed.marker");
        tokio::fs::write(&marker, "deployed")
            .await
            .map_err(|e| format!("Failed to write marker: {e}"))?;
        Ok(())
    }

    /// TLS flags for local worker JSON (mirrors ``ghost_config.json`` Phase 4 fields).
    async fn read_ghost_tls_for_local_worker(&self) -> (bool, String) {
        let p = self.ghost_root.join("ghost_config.json");
        let Ok(raw) = tokio::fs::read_to_string(&p).await else {
            return (false, String::new());
        };
        let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) else {
            return (false, String::new());
        };
        let tls_enabled = v
            .get("tls_enabled")
            .and_then(|x| x.as_bool())
            .unwrap_or(false);
        let cert = v
            .get("tls_cert_path")
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .to_string();
        (tls_enabled, cert)
    }

    #[cfg(target_os = "linux")]
    async fn start_local_worker(&self) -> Result<(), String> {
        let engine = self.ghost_root.join("engine");
        let linux_worker_dir = engine.join("linux-worker");
        let main_py = linux_worker_dir.join("linux_worker").join("main.py");
        if !main_py.exists() {
            log::info!("Local worker main.py not found, skipping");
            return Ok(());
        }

        let config_path = self.ghost_root.join("local_worker_config.json");
        let (tls_enabled, tls_controller_cert_path) =
            self.read_ghost_tls_for_local_worker().await;
        let config = serde_json::json!({
            "worker_id": "local-worker",
            "controller_host": "127.0.0.1",
            "controller_port": 8765,
            "worker_port": 8090,
            "tls_enabled": tls_enabled,
            "tls_controller_cert_path": tls_controller_cert_path,
        });
        tokio::fs::write(
            &config_path,
            serde_json::to_string_pretty(&config).unwrap_or_else(|_| "{}".to_string()),
        )
        .await
        .map_err(|e| format!("Failed to write local worker config: {e}"))?;

        let python = venv_python(&self.ghost_root);
        let mut cmd = Command::new(python.to_string_lossy().as_ref());
        cmd.args(["-m", "linux_worker.main", "--config"])
            .arg(config_path.to_string_lossy().as_ref())
            .current_dir(&linux_worker_dir)
            .env("PYTHONPATH", linux_worker_dir.to_string_lossy().as_ref());
        hide_child_console(&mut cmd);

        match cmd.spawn() {
            Ok(_) => log::info!("Local worker started on 0.0.0.0:8090"),
            Err(e) => log::warn!("Failed to start local worker: {e}"),
        }

        self.run_readiness_probe().await;
        Ok(())
    }

    #[cfg(target_os = "windows")]
    async fn start_local_worker(&self) -> Result<(), String> {
        let engine = self.ghost_root.join("engine");
        let windows_worker_dir = engine.join("windows-worker");
        let main_py = windows_worker_dir.join("windows_worker").join("main.py");

        if !main_py.exists() {
            let msg = "Windows worker runtime missing. Expected engine/windows-worker/windows_worker/main.py";
            log::error!("worker_runtime_missing: {msg}");
            return Err(format!(
                "Windows worker runtime missing or failed to start. {}",
                msg
            ));
        }

        let config_path = self.ghost_root.join("local_worker_config.json");
        let (tls_enabled, tls_controller_cert_path) =
            self.read_ghost_tls_for_local_worker().await;
        let config = serde_json::json!({
            "worker_id": "local-worker",
            "controller_host": "127.0.0.1",
            "controller_port": 8765,
            "worker_port": 8090,
            "tls_enabled": tls_enabled,
            "tls_controller_cert_path": tls_controller_cert_path,
        });
        tokio::fs::write(
            &config_path,
            serde_json::to_string_pretty(&config).unwrap_or_else(|_| "{}".to_string()),
        )
        .await
        .map_err(|e| format!("Failed to write local worker config: {e}"))?;

        let python = venv_python(&self.ghost_root);
        let mut cmd = Command::new(python.to_string_lossy().as_ref());
        cmd.args(["-m", "windows_worker.main", "--config"])
            .arg(config_path.to_string_lossy().as_ref())
            .current_dir(&windows_worker_dir)
            .env("PYTHONPATH", windows_worker_dir.to_string_lossy().as_ref());
        hide_child_console(&mut cmd);

        match cmd.spawn() {
            Ok(_) => {
                log::info!("Local Windows worker started on 0.0.0.0:8090");
            }
            Err(e) => {
                let msg = format!("worker_spawn_failed: {e}");
                log::error!("{}", msg);
                return Err(format!(
                    "Windows worker runtime missing or failed to start. {}",
                    msg
                ));
            }
        }

        self.run_readiness_probe().await;
        Ok(())
    }

    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    async fn start_local_worker(&self) -> Result<(), String> {
        log::info!("Local worker step skipped on this platform");
        Ok(())
    }

    /// Poll port 8095 with `GHOST_DISCOVER_WORKERS` UDP probes until the local
    /// worker responds or the maximum attempts (from `ghost_config.json`) are
    /// exhausted.  Stores the probe outcome in `self.readiness_result` so
    /// `run_pre_scan_deployment()` can include it in the discovery log.
    ///
    /// This is non-blocking to the deploy flow — if the probe times out the
    /// worker may still respond during the broadcast scan.
    async fn run_readiness_probe(&self) {
        if self.is_offline() {
            log::info!("Skipping UDP readiness probe (offline mode — local worker assumed reachable)");
            self.emit_scan_log("GHOST OFFLINE MODE — skipping readiness probe; assuming local worker");
            if let Ok(mut r) = self.readiness_result.lock() {
                *r = (0, true);
            }
            return;
        }

        let config_path = self.ghost_root.join("ghost_config.json");
        let probe_interval_ms =
            read_nested_config(&config_path, &["worker", "readiness_probe_interval_ms"])
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(500);
        let max_attempts =
            read_nested_config(&config_path, &["worker", "readiness_max_attempts"])
                .and_then(|s| s.parse::<u32>().ok())
                .unwrap_or(20);
        let attempt_timeout_ms =
            read_nested_config(&config_path, &["worker", "readiness_attempt_timeout_ms"])
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(1000);

        self.emit_scan_log(&format!(
            "Waiting for local worker (up to {} probe attempt(s))…",
            max_attempts
        ));

        let mut probe_success = false;
        let mut attempts = 0u32;

        for i in 0..max_attempts {
            attempts = i + 1;
            self.emit_scan_log(&format!(
                "Readiness probe {}/{}…",
                attempts, max_attempts
            ));

            let ready = tokio::task::spawn_blocking(move || {
                discovery::probe_worker_readiness(attempt_timeout_ms)
            })
            .await
            .unwrap_or(false);

            if ready {
                probe_success = true;
                self.emit_scan_log(&format!(
                    "Local worker ready after {} attempt(s)",
                    attempts
                ));
                log::info!(
                    "Local worker readiness probe succeeded on attempt {}",
                    attempts
                );
                break;
            }

            if i + 1 < max_attempts {
                tokio::time::sleep(std::time::Duration::from_millis(probe_interval_ms)).await;
            }
        }

        if !probe_success {
            log::warn!(
                "Local worker readiness probe timed out after {} attempt(s); proceeding",
                attempts
            );
            self.emit_scan_log(&format!(
                "Readiness probe timed out after {} attempt(s); proceeding to discovery",
                attempts
            ));
        }

        if let Ok(mut r) = self.readiness_result.lock() {
            *r = (attempts, probe_success);
        }
    }

    async fn scan_lan(&self) -> Result<(), String> {
        if self.is_offline() {
            log::info!("Skipping LAN scan and worker registration (offline mode)");
            self.emit_scan_log("GHOST OFFLINE MODE — skipping LAN scan and remote registration");
            return Ok(());
        }

        let base_ips = local_ip_bases();
        let broadcast_addrs: Vec<String> = base_ips
            .iter()
            .filter_map(|b| base_to_broadcast(b))
            .collect();

        self.emit_scan_log(&format!("Subnets to broadcast: {:?}", broadcast_addrs));
        self.emit_scan_log("Broadcasting DISCOVER_WORKERS on 127.0.0.1…");
        for addr in &broadcast_addrs {
            self.emit_scan_log(&format!("Broadcasting DISCOVER_WORKERS on {addr}/24…"));
        }
        self.emit_scan_log("Waiting for worker manifests…");

        let (total_timeout_ms, early_exit) = self.read_discovery_config();
        let addrs = broadcast_addrs.clone();
        let manifests = tokio::task::spawn_blocking(move || {
            discovery::discover_single_window(&addrs, total_timeout_ms, early_exit, None)
        })
        .await
        .map_err(|e| format!("Discovery task panicked: {e}"))?;

        self.emit_scan_log(&format!("Received {} manifest(s)", manifests.len()));

        let controller = GhostApiClient::new("http://127.0.0.1:8765");
        let mut registered = 0usize;

        for m in &manifests {
            let host = m.registration_host();
            self.emit_scan_log(&format!("Received worker manifest from {}:{} (sig={})", host, m.port, m.signature_verified));
            self.emit_scan_log("Validating manifest…");
            let req = RegisterWorkerRequest {
                worker_id: m.manifest.worker_id.clone(),
                host,
                port: m.port,
                gpu_info: m.manifest.capabilities.clone(),
                status: "active".to_string(),
            };
            match controller.register_worker(&req).await {
                Ok(()) => {
                    registered += 1;
                    self.emit_scan_log(&format!("Registering worker {}…", req.worker_id));
                }
                Err(e) => {
                    self.emit_scan_log(&format!("Registration failed: {e}"));
                    log::warn!("Failed to register worker {}: {e}", req.worker_id);
                }
            }
        }

        if !manifests.is_empty() {
            let scan_path = self.ghost_root.join("lan_scan.json");
            let json_manifests: Vec<_> = manifests
                .iter()
                .map(|m| serde_json::json!({"ip": m.registration_host(), "port": m.port, "worker_id": m.worker_id()}))
                .collect();
            let json = serde_json::to_string_pretty(&json_manifests).unwrap_or_else(|_| "[]".to_string());
            tokio::fs::write(&scan_path, json)
                .await
                .map_err(|e| format!("Failed to write discovery results: {e}"))?;
        }

        self.emit_scan_log(&format!("Done: {registered} worker(s) registered"));
        if registered == 0 {
            self.emit_scan_log("No workers found. Possible causes:");
            self.emit_scan_log("  • Worker not running or still initializing");
            self.emit_scan_log("  • Port 8095/udp may be blocked by firewall");
            self.emit_scan_log("  • Worker process failed to start (check worker logs)");
        }
        log::info!("Discovery complete: {registered} worker(s) registered");
        Ok(())
    }

    /// Run steps 0–9 plus discovery (no registration). For deployment ceremony.
    /// Returns discovered workers and structured log; discovery_failed when worker_count == 0.
    pub async fn run_pre_scan_deployment(&self) -> Result<DeploymentPreScanResult, String> {
        const TOTAL_STEPS: usize = 12;

        // Full Deployment Initialization Log — collect entries 1–22
        let mut full_deploy_entries: Vec<FullDeployLogEntry> = Vec::new();
        let mut step_idx = 0u32;

        step_idx += 1;
        full_deploy_entries.push(FullDeployLogEntry {
            timestamp: chrono::Utc::now().to_rfc3339(),
            step_index: step_idx,
            step_name: "deploy_clicked".to_string(),
            success: true,
            duration_ms: 0,
            metadata: None,
            error_message: None,
        });

        for i in 0..=9 {
            let label = Self::steps().get(i).copied().unwrap_or("…");
            self.emit_deploy_progress(i, TOTAL_STEPS, label, (i as f64) / (TOTAL_STEPS as f64));

            let step_name = format!("step_{}_{}", i, match i {
                0 => "create_venv",
                1 => "install_python_deps",
                2 => "install_ghost_core",
                3 => "verify_gpu_plugins",
                4 => "install_service",
                5 => "bootstrap_config",
                6 => "start_controller",
                7 => "open_ports",
                8 => "initialize_state",
                9 => "start_local_worker",
                _ => "unknown",
            });
            let step_start = std::time::Instant::now();
            let result = self.run_step(i).await;
            let duration_ms = step_start.elapsed().as_millis() as u64;

            step_idx += 1;
            full_deploy_entries.push(FullDeployLogEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                step_index: step_idx,
                step_name,
                success: result.is_ok(),
                duration_ms,
                metadata: Some(serde_json::json!({"step": i})),
                error_message: result.as_ref().err().map(|e| e.clone()),
            });

            result?;
        }

        self.emit_deploy_progress(10, TOTAL_STEPS, "Scanning LAN", 10_f64 / TOTAL_STEPS as f64);

        // Dependency Initialization Log — measure each dependency before discovery
        let mut dependency_init_entries = Vec::new();

        let config_start = std::time::Instant::now();
        let (total_timeout_ms, early_exit) = self.read_discovery_config();
        let config_duration = config_start.elapsed().as_millis() as u64;
        dependency_init_entries.push(DependencyInitEntry {
            timestamp: chrono::Utc::now().to_rfc3339(),
            item: "config_load (ghost_config.json discovery section)".to_string(),
            success: true,
            duration_ms: config_duration,
        });
        step_idx += 1;
        full_deploy_entries.push(FullDeployLogEntry {
            timestamp: chrono::Utc::now().to_rfc3339(),
            step_index: step_idx,
            step_name: "config_load_ghost_config".to_string(),
            success: true,
            duration_ms: config_duration,
            metadata: Some(serde_json::json!({"total_timeout_ms": total_timeout_ms, "early_exit": early_exit})),
            error_message: None,
        });

        let broadcast_addrs: Vec<String> = if self.is_offline() {
            if let Some(ref bp) = self.offline_bundle_path {
                log::warn!("Using offline bundle at: {}", bp.display());
            }
            self.emit_scan_log("GHOST OFFLINE MODE — skipping network interface broadcast enumeration");
            dependency_init_entries.push(DependencyInitEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                item: "network_interface_enumeration (skipped offline)".to_string(),
                success: true,
                duration_ms: 0,
            });
            step_idx += 1;
            full_deploy_entries.push(FullDeployLogEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                step_index: step_idx,
                step_name: "network_interface_enumeration".to_string(),
                success: true,
                duration_ms: 0,
                metadata: Some(serde_json::json!({"skipped": "offline"})),
                error_message: None,
            });
            step_idx += 1;
            full_deploy_entries.push(FullDeployLogEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                step_index: step_idx,
                step_name: "broadcast_address_calculation".to_string(),
                success: true,
                duration_ms: 0,
                metadata: Some(serde_json::json!({"skipped": "offline"})),
                error_message: None,
            });
            Vec::new()
        } else {
            let net_start = std::time::Instant::now();
            let base_ips = local_ip_bases();
            let addrs: Vec<String> = base_ips
                .iter()
                .filter_map(|b| base_to_broadcast(b))
                .collect();
            let net_duration = net_start.elapsed().as_millis() as u64;
            dependency_init_entries.push(DependencyInitEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                item: "network_interface_enumeration".to_string(),
                success: !addrs.is_empty(),
                duration_ms: net_duration,
            });
            step_idx += 1;
            full_deploy_entries.push(FullDeployLogEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                step_index: step_idx,
                step_name: "network_interface_enumeration".to_string(),
                success: !addrs.is_empty(),
                duration_ms: net_duration,
                metadata: Some(serde_json::json!({"bases": base_ips, "broadcast_count": addrs.len()})),
                error_message: None,
            });

            step_idx += 1;
            full_deploy_entries.push(FullDeployLogEntry {
                timestamp: chrono::Utc::now().to_rfc3339(),
                step_index: step_idx,
                step_name: "broadcast_address_calculation".to_string(),
                success: !addrs.is_empty(),
                duration_ms: 0,
                metadata: Some(serde_json::json!({"broadcast_addrs": &addrs})),
                error_message: None,
            });
            addrs
        };

        let (probe_attempts, probe_success) = self
            .readiness_result
            .lock()
            .map(|r| *r)
            .unwrap_or((0, false));
        let probe_interval = read_nested_config(&self.ghost_root.join("ghost_config.json"), &["worker", "readiness_probe_interval_ms"])
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(500);
        let probe_timeout = read_nested_config(&self.ghost_root.join("ghost_config.json"), &["worker", "readiness_attempt_timeout_ms"])
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(1000);
        let probe_duration_ms: u64 = if probe_attempts > 0 {
            (probe_attempts as u64 - 1) * probe_interval + probe_timeout
        } else {
            0
        };
        dependency_init_entries.push(DependencyInitEntry {
            timestamp: chrono::Utc::now().to_rfc3339(),
            item: "worker_readiness_probe".to_string(),
            success: probe_success,
            duration_ms: probe_duration_ms,
        });
        step_idx += 1;
        full_deploy_entries.push(FullDeployLogEntry {
            timestamp: chrono::Utc::now().to_rfc3339(),
            step_index: step_idx,
            step_name: "readiness_probe_result".to_string(),
            success: probe_success,
            duration_ms: probe_duration_ms,
            metadata: Some(serde_json::json!({"attempts": probe_attempts})),
            error_message: if probe_success { None } else { Some("readiness probe timed out".to_string()) },
        });

        let (discovered_workers, mut discovery_log) = if self.is_offline() {
            self.emit_scan_log("GHOST OFFLINE MODE — skipping network operations (UDP discovery)");
            let tt = total_timeout_ms;
            let deps = dependency_init_entries.clone();
            let full = full_deploy_entries.clone();
            let (mut dlog, synthetic) = tokio::task::spawn_blocking(move || {
                let mut log = DiscoveryLogBuilder::new(vec!["offline".to_string()], 8095);
                for e in deps {
                    log.add_dependency_init_entry(e);
                }
                log.add_full_deploy_entries(full);
                log.push_raw("GHOST OFFLINE MODE — LAN discovery skipped (synthetic local-worker)");
                let ts = chrono::Utc::now().to_rfc3339();
                log.set_discovery_timing(&ts, &ts, 0, tt, 0);
                let discovery_log = log.build(1);
                let w = DiscoveredWorkerForCeremony {
                    worker_id: "local-worker".to_string(),
                    host: "127.0.0.1".to_string(),
                    port: 8090,
                    gpu_info: serde_json::json!({}),
                    source_ip: "127.0.0.1".to_string(),
                    signature_verified: false,
                    fingerprint: String::new(),
                    public_key_b64: String::new(),
                };
                (discovery_log, w)
            })
            .await
            .map_err(|e| format!("Offline discovery task panicked: {e}"))?;
            dlog.set_readiness_result(probe_attempts, probe_success);
            self.emit_scan_log("Received 1 synthetic manifest (offline local-worker)");
            (vec![synthetic], dlog)
        } else {
            self.emit_scan_log(&format!("Subnets to broadcast: {:?}", broadcast_addrs));
            self.emit_scan_log("Broadcasting DISCOVER_WORKERS on 127.0.0.1…");
            for addr in &broadcast_addrs {
                self.emit_scan_log(&format!("Broadcasting DISCOVER_WORKERS on {addr}/24…"));
            }
            self.emit_scan_log("Waiting for worker manifests…");

            self.emit_scan_log(&format!(
                "Discovery window: {} ms (early_exit={})",
                total_timeout_ms, early_exit
            ));

            let addrs = broadcast_addrs.clone();
            let (manifests, mut discovery_log) = tokio::task::spawn_blocking(move || {
                discover_workers_with_log(
                    &addrs,
                    total_timeout_ms,
                    early_exit,
                    dependency_init_entries,
                    full_deploy_entries,
                )
            })
            .await
            .map_err(|e| format!("Discovery task panicked: {e}"))?;

            discovery_log.set_readiness_result(probe_attempts, probe_success);

            self.emit_scan_log(&format!("Received {} manifest(s)", manifests.len()));

            let discovered_workers: Vec<DiscoveredWorkerForCeremony> = manifests
                .iter()
                .map(|m| DiscoveredWorkerForCeremony {
                    worker_id: m.manifest.worker_id.clone(),
                    host: m.registration_host(),
                    port: m.port,
                    gpu_info: m.manifest.capabilities.clone(),
                    source_ip: m.source_ip.clone(),
                    signature_verified: m.signature_verified,
                    fingerprint: m.fingerprint.clone(),
                    public_key_b64: m.manifest.public_key_b64.clone(),
                })
                .collect();
            (discovered_workers, discovery_log)
        };

        let discovery_failed = discovery_log.worker_count == 0;

        // Add actionable hints when no workers were found.
        if discovery_failed {
            if probe_attempts > 0 && !probe_success {
                discovery_log.add_diagnostic_hint(&format!(
                    "Worker not ready: readiness probe timed out after {} attempt(s)",
                    probe_attempts
                ));
            }
            discovery_log.add_diagnostic_hint("Port 8095/udp may be blocked by firewall");
            discovery_log.add_diagnostic_hint(
                "Worker process may have failed to start (check worker logs)",
            );
            discovery_log.add_diagnostic_hint(
                "Worker still initializing — try running discovery again",
            );
        }

        let offline_mode = self.is_offline();
        if offline_mode {
            self.persist_offline_install_marker().await?;
        }

        Ok(DeploymentPreScanResult {
            discovered_workers,
            discovery_log,
            discovery_failed,
            offline_mode,
        })
    }

    /// Writes ``state/offline_install.json`` so later sessions can skip WAN discovery helpers.
    async fn persist_offline_install_marker(&self) -> Result<(), String> {
        let state_dir = self.ghost_root.join("state");
        tokio::fs::create_dir_all(&state_dir)
            .await
            .map_err(|e| format!("Failed to create state dir: {e}"))?;
        let path = state_dir.join("offline_install.json");
        let payload = serde_json::json!({
            "offline": true,
            "bundle_path": self.offline_bundle_path.as_ref().map(|p| p.to_string_lossy().to_string()),
            "written_at": chrono::Utc::now().to_rfc3339(),
        });
        let body = serde_json::to_string_pretty(&payload).map_err(|e| e.to_string())?;
        tokio::fs::write(&path, body)
            .await
            .map_err(|e| format!("Failed to write offline_install.json: {e}"))?;
        Ok(())
    }

    /// Register selected workers and run step 11 (load execution modes).
    /// Persists controller and LLM config from ceremony choices.
    pub async fn complete_deployment_with_selection(
        &self,
        worker_pool: Vec<WorkerSelectionForRegistration>,
        run_controller_llm: bool,
    ) -> Result<(), String> {
        let controller = GhostApiClient::new("http://127.0.0.1:8765");

        for w in &worker_pool {
            // §5 — Record TrustRecord(approved) before registration.
            if let Err(e) = controller
                .approve_worker(&w.worker_id, &w.public_key_b64)
                .await
            {
                log::warn!("Failed to approve worker {}: {e}", w.worker_id);
                continue;
            }
            let req = RegisterWorkerRequest {
                worker_id: w.worker_id.clone(),
                host: w.host.clone(),
                port: w.port,
                gpu_info: w.gpu_info.clone(),
                status: "active".to_string(),
            };
            if let Err(e) = controller.register_worker(&req).await {
                log::warn!("Failed to register worker {}: {e}", w.worker_id);
            }
        }

        // Ensure llm_config exists (load_execution_modes creates it), then persist run_controller_llm
        self.load_execution_modes().await?;

        let llm_config_path = self.ghost_root.join("llm_config.json");
        if llm_config_path.exists() {
            let content = tokio::fs::read_to_string(&llm_config_path)
                .await
                .map_err(|e| format!("Failed to read llm_config.json: {e}"))?;
            if let Ok(mut cfg) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(obj) = cfg.as_object_mut() {
                    obj.insert(
                        "run_controller_llm".to_string(),
                        serde_json::Value::Bool(run_controller_llm),
                    );
                }
                let tmp = self.ghost_root.join("llm_config.json.tmp");
                tokio::fs::write(
                    &tmp,
                    serde_json::to_string_pretty(&cfg).map_err(|e| e.to_string())?,
                )
                .await
                .map_err(|e| format!("Failed to write llm_config.json.tmp: {e}"))?;
                tokio::fs::rename(&tmp, &llm_config_path)
                    .await
                    .map_err(|e| format!("Failed to update llm_config.json: {e}"))?;
            }
        }

        Ok(())
    }
}

/// Emit a scan log line if the app handle is provided.
fn emit_scan_log_opt(app: &Option<tauri::AppHandle>, line: &str) {
    if let Some(ref a) = app {
        let _ = a.emit("scan-log", line);
    }
}

/// Run broadcast discovery and register workers. Used by deployment step 9 and manual "Scan LAN".
pub async fn scan_and_register_workers(
    ghost_root: &std::path::Path,
    controller_url: &str,
    scan_log_emitter: Option<tauri::AppHandle>,
) -> Result<ScanResult, String> {
    if ghost_root.join("state/offline_install.json").is_file() {
        emit_scan_log_opt(
            &scan_log_emitter,
            "GHOST OFFLINE MODE — scan skipped (no remote LAN discovery)",
        );
        return Ok(ScanResult {
            scanned: 0,
            registered: 0,
            nodes: Vec::new(),
        });
    }

    let base_ips = local_ip_bases();
    let broadcast_addrs: Vec<String> = base_ips
        .iter()
        .filter_map(|b| base_to_broadcast(b))
        .collect();

    emit_scan_log_opt(&scan_log_emitter, &format!("Subnets: {:?}", broadcast_addrs));
    emit_scan_log_opt(&scan_log_emitter, "Broadcasting DISCOVER_WORKERS…");
    emit_scan_log_opt(&scan_log_emitter, "Waiting for worker manifests…");

    let config_path = ghost_root.join("ghost_config.json");
    let total_timeout_ms = read_nested_config(&config_path, &["discovery", "total_timeout_ms"])
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(DEFAULT_DISCOVERY_TOTAL_TIMEOUT_MS);
    let early_exit = read_nested_config(&config_path, &["discovery", "early_exit_on_first_worker"])
        .and_then(|s| s.parse::<bool>().ok())
        .unwrap_or(true);

    let addrs = broadcast_addrs.clone();
    let manifests = tokio::task::spawn_blocking(move || {
        discovery::discover_single_window(&addrs, total_timeout_ms, early_exit, None)
    })
    .await
    .map_err(|e| format!("Discovery task panicked: {e}"))?;

    emit_scan_log_opt(&scan_log_emitter, &format!("Received {} manifest(s)", manifests.len()));

    let controller = GhostApiClient::new(controller_url);
    let mut registered = 0usize;
    for m in &manifests {
        let host = m.registration_host();
        emit_scan_log_opt(&scan_log_emitter, &format!("Received worker manifest from {}:{} (sig={})", host, m.port, m.signature_verified));
        emit_scan_log_opt(&scan_log_emitter, "Validating manifest…");
        let req = RegisterWorkerRequest {
            worker_id: m.manifest.worker_id.clone(),
            host,
            port: m.port,
            gpu_info: m.manifest.capabilities.clone(),
            status: "active".to_string(),
        };
        match controller.register_worker(&req).await {
            Ok(()) => {
                registered += 1;
                emit_scan_log_opt(&scan_log_emitter, &format!("Registering worker {}…", req.worker_id));
            }
            Err(e) => {
                emit_scan_log_opt(&scan_log_emitter, &format!("Registration failed: {e}"));
                log::warn!("Failed to register {}: {e}", m.worker_id());
            }
        }
    }
    emit_scan_log_opt(&scan_log_emitter, &format!("Done: {registered} worker(s) registered"));

    if !manifests.is_empty() {
        let scan_path = ghost_root.join("lan_scan.json");
        let json_manifests: Vec<_> = manifests
            .iter()
            .map(|m| serde_json::json!({"ip": m.registration_host(), "port": m.port, "worker_id": m.worker_id()}))
            .collect();
        let json = serde_json::to_string_pretty(&json_manifests).unwrap_or_else(|_| "[]".to_string());
        let _ = tokio::fs::write(&scan_path, json).await;
    }

    Ok(ScanResult {
        scanned: manifests.len(),
        registered,
        nodes: manifests
            .into_iter()
            .map(|m| (m.registration_host(), m.port))
            .collect(),
    })
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ScanResult {
    pub scanned: usize,
    pub registered: usize,
    pub nodes: Vec<(String, u16)>,
}

impl GhostDeployer {
    async fn load_execution_modes(&self) -> Result<(), String> {
        tokio::fs::create_dir_all(&self.ghost_root)
            .await
            .map_err(|e| format!("Failed to create ghost root: {e}"))?;

        // LLM config (separate from ghost_config.json — governs LLM routing only).
        let llm_config_path = self.ghost_root.join("llm_config.json");
        if !llm_config_path.exists() {
            let default = serde_json::json!({
                "execution_mode": "manual",
                "allow_per_task_override": false,
                "model": "phi-3.5-mini",
                "auto_withdraw_on_human_activity": true,
                "confidence_threshold": 0.85
            });
            tokio::fs::write(
                &llm_config_path,
                serde_json::to_string_pretty(&default).map_err(|e| e.to_string())?,
            )
            .await
            .map_err(|e| format!("Failed to write llm_config.json: {e}"))?;
            log::info!("Default llm_config.json written (execution_mode: manual)");
        }

        // ghost_config.json was written at Step 4.5 (bootstrap_config).
        // This step is idempotent: only add execution_modes.default_mode if
        // absent from the Step 4.5 write.  Never overwrite the full file here.
        let controller_config_path = self.ghost_root.join("ghost_config.json");
        if controller_config_path.exists() {
            let content = tokio::fs::read_to_string(&controller_config_path)
                .await
                .map_err(|e| format!("Failed to read ghost_config.json: {e}"))?;
            if let Ok(mut cfg) = serde_json::from_str::<serde_json::Value>(&content) {
                let needs_update = cfg
                    .get("execution_modes")
                    .and_then(|em| em.get("default_mode"))
                    .is_none();
                if needs_update {
                    if let Some(obj) = cfg.as_object_mut() {
                        obj.entry("execution_modes")
                            .or_insert(serde_json::json!({}))
                            .as_object_mut()
                            .map(|em| em.insert(
                                "default_mode".to_string(),
                                serde_json::json!("manual"),
                            ));
                    }
                    let tmp = self.ghost_root.join("ghost_config.json.tmp");
                    tokio::fs::write(
                        &tmp,
                        serde_json::to_string_pretty(&cfg).map_err(|e| e.to_string())?,
                    )
                    .await
                    .map_err(|e| format!("Failed to write ghost_config.json.tmp: {e}"))?;
                    tokio::fs::rename(&tmp, &controller_config_path)
                        .await
                        .map_err(|e| format!("Failed to update ghost_config.json: {e}"))?;
                    log::info!("ghost_config.json: execution_modes.default_mode added (idempotent step 10)");
                }
            }
        } else {
            log::warn!(
                "ghost_config.json not found at step 10 — Step 4.5 (bootstrap_config) \
                 may not have run. Execution modes will not be persisted."
            );
        }

        Ok(())
    }

    // ── Phase 2: Canonical lifecycle (uninstall / upgrade) ─────────────

    /// Stop GHOST OS services (best effort).
    async fn stop_ghost_services(&self) {
        #[cfg(target_os = "linux")]
        {
            let _ = Command::new("systemctl")
                .args(["--user", "stop", "ghost"])
                .output()
                .await;
            let _ = Command::new("systemctl")
                .args(["--user", "disable", "ghost"])
                .output()
                .await;
            let unit = home_dir()
                .join(".config/systemd/user/ghost.service");
            let _ = tokio::fs::remove_file(&unit).await;
            let _ = Command::new("systemctl")
                .args(["--user", "daemon-reload"])
                .output()
                .await;
            log::info!("Linux user systemd GHOST service stopped and unit removed (if present)");
        }
        #[cfg(target_os = "windows")]
        {
            let mut sc = Command::new("sc");
            sc.args(["stop", "ghost"]);
            hide_child_console(&mut sc);
            let _ = sc.output().await;
            if let Err(e) = super::windows::service_installer::uninstall_service("ghost").await {
                log::warn!("Windows service remove: {e}");
            }
        }
        #[cfg(not(any(target_os = "linux", target_os = "windows")))]
        {
            log::info!("stop_ghost_services: no-op on this platform");
        }
    }

    /// Remove Windows firewall rules created by open_ports (best effort).
    async fn remove_windows_firewall_ghost_rules(&self) {
        #[cfg(target_os = "windows")]
        for name in [
            "GhostController",
            "GhostWorker",
            "GhostDiscovery",
            "GhostSocket",
        ] {
            let mut netsh = Command::new("netsh");
            netsh.args([
                "advfirewall",
                "firewall",
                "delete",
                "rule",
                &format!("name={name}"),
            ]);
            hide_child_console(&mut netsh);
            let _ = netsh.output().await;
        }
    }

    /// Delete all content under `ghost_root` (identity, engine, venv, state, config).
    pub async fn uninstall_deployment(&self) -> Result<serde_json::Value, String> {
        log::info!("Uninstall: stopping services");
        self.stop_ghost_services().await;
        self.remove_windows_firewall_ghost_rules().await;

        let root = &self.ghost_root;
        if !root.exists() {
            return Ok(serde_json::json!({
                "status": "nothing_to_remove",
                "ghost_root": root.to_string_lossy(),
            }));
        }

        log::info!("Uninstall: removing {:?}", root);
        tokio::fs::remove_dir_all(root)
            .await
            .map_err(|e| format!("Failed to remove ghost root {:?}: {e}", root))?;

        Ok(serde_json::json!({
            "status": "removed",
            "ghost_root": root.to_string_lossy(),
        }))
    }

    /// Copy `config/` and `state/` plus key JSON files into `stash` for upgrade restore.
    async fn stash_config_for_upgrade(&self, stash: &Path) -> Result<(), String> {
        tokio::fs::create_dir_all(stash)
            .await
            .map_err(|e| format!("stash mkdir: {e}"))?;
        for name in [
            "ghost_config.json",
            "controller_placement.json",
            "local_worker_config.json",
        ] {
            let p = self.ghost_root.join(name);
            if p.exists() {
                tokio::fs::copy(&p, stash.join(name))
                    .await
                    .map_err(|e| format!("stash copy {name}: {e}"))?;
            }
        }
        for dir in ["config", "state"] {
            let src = self.ghost_root.join(dir);
            if src.is_dir() {
                let dst = stash.join(dir);
                copy_dir_all(&src, &dst)
                    .await
                    .map_err(|e| format!("stash dir {dir}: {e}"))?;
            }
        }
        Ok(())
    }

    async fn restore_stashed_config(&self, stash: &Path) -> Result<(), String> {
        for name in [
            "ghost_config.json",
            "controller_placement.json",
            "local_worker_config.json",
        ] {
            let sf = stash.join(name);
            if sf.exists() {
                let dst = self.ghost_root.join(name);
                tokio::fs::copy(&sf, &dst)
                    .await
                    .map_err(|e| format!("restore {name}: {e}"))?;
            }
        }
        for dir in ["config", "state"] {
            let src = stash.join(dir);
            if src.is_dir() {
                let dst = self.ghost_root.join(dir);
                if dst.exists() {
                    tokio::fs::remove_dir_all(&dst)
                        .await
                        .map_err(|e| format!("restore rm old {dir}: {e}"))?;
                }
                copy_dir_all(&src, &dst)
                    .await
                    .map_err(|e| format!("restore dir {dir}: {e}"))?;
            }
        }
        Ok(())
    }

    /// Replace `engine/` from bundled `engine_source` while preserving config and controller state.
    pub async fn upgrade_engine_preserve_state(&self) -> Result<serde_json::Value, String> {
        let stash = self.ghost_root.join(".upgrade_stash");
        if stash.exists() {
            let _ = tokio::fs::remove_dir_all(&stash).await;
        }

        log::info!("Upgrade: stopping services");
        self.stop_ghost_services().await;

        self.stash_config_for_upgrade(&stash)
            .await
            .map_err(|e| format!("upgrade stash failed: {e}"))?;

        let engine = self.ghost_root.join("engine");
        if engine.exists() {
            tokio::fs::remove_dir_all(&engine)
                .await
                .map_err(|e| format!("remove engine: {e}"))?;
        }

        self.install_ghost_core()
            .await
            .map_err(|e| format!("upgrade copy engine: {e}"))?;

        self.restore_stashed_config(&stash)
            .await
            .map_err(|e| format!("upgrade restore failed: {e}"))?;

        let _ = tokio::fs::remove_dir_all(&stash).await;

        log::info!("Upgrade: restarting controller process");
        self.start_controller()
            .await
            .map_err(|e| format!("upgrade start_controller: {e}"))?;

        self.install_service()
            .await
            .map_err(|e| format!("upgrade service: {e}"))?;

        Ok(serde_json::json!({
            "status": "upgraded",
            "preserved": ["ghost_config.json", "controller_placement.json", "config/", "state/"],
        }))
    }
}

// ── Helpers ─────────────────────────────────────────────────────────

/// Recursively copy a directory tree from `src` to `dst`.
/// Skips `__pycache__`, `.git`, `venv`, and `*.pyc` files.
async fn copy_dir_all(src: &Path, dst: &Path) -> std::io::Result<()> {
    tokio::fs::create_dir_all(dst).await?;

    let mut read_dir = tokio::fs::read_dir(src).await?;
    while let Some(entry) = read_dir.next_entry().await? {
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        // Skip noise
        if matches!(
            name_str.as_ref(),
            "__pycache__" | ".git" | ".github" | "venv" | ".venv" | "node_modules"
        ) || name_str.ends_with(".pyc")
            || name_str.ends_with(".egg-info")
        {
            continue;
        }

        let src_path = entry.path();
        let dst_path = dst.join(&name);
        let file_type = entry.file_type().await?;

        if file_type.is_dir() {
            // Box the future to avoid infinite-size recursion
            Box::pin(copy_dir_all(&src_path, &dst_path)).await?;
        } else {
            tokio::fs::copy(&src_path, &dst_path).await?;
        }
    }
    Ok(())
}

fn home_dir() -> PathBuf {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

#[allow(dead_code)]
fn whoami_or_root() -> String {
    std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "root".to_string())
}

/// Return the correct Python executable path inside the venv.
/// Windows:  .ghost\venv\Scripts\python.exe
/// Unix:     .ghost/venv/bin/python3
fn venv_python(ghost_root: &PathBuf) -> PathBuf {
    #[cfg(target_os = "windows")]
    return ghost_root.join("venv\\Scripts\\python.exe");
    #[cfg(not(target_os = "windows"))]
    return ghost_root.join("venv/bin/python3");
}

/// Return the correct pip executable path inside the venv.
/// Windows:  .ghost\venv\Scripts\pip.exe
/// Unix:     .ghost/venv/bin/pip
fn venv_pip(ghost_root: &PathBuf) -> PathBuf {
    #[cfg(target_os = "windows")]
    return ghost_root.join("venv\\Scripts\\pip.exe");
    #[cfg(not(target_os = "windows"))]
    return ghost_root.join("venv/bin/pip");
}

/// Read a string field from a flat `ghost_config.json` (legacy flat schema).
/// Returns `None` if the file doesn't exist or the field is missing.
#[allow(dead_code)]
fn read_controller_config(ghost_root: &PathBuf, key: &str) -> Option<String> {
    let path = ghost_root.join("ghost_config.json");
    let content = std::fs::read_to_string(&path).ok()?;
    let json: serde_json::Value = serde_json::from_str(&content).ok()?;
    json.get(key)?.as_str().map(|s| s.to_string())
}

/// Read a string (or number coerced to string) from a **nested** path inside
/// `ghost_config.json`.  `keys` is a path of 1–N string segments, e.g.
/// `&["controller", "security"]`.  Returns `None` if the file, the path, or
/// the value is absent.
fn read_nested_config(path: &std::path::Path, keys: &[&str]) -> Option<String> {
    let content = std::fs::read_to_string(path).ok()?;
    let mut node: serde_json::Value = serde_json::from_str(&content).ok()?;
    for key in keys {
        node = node.get(key)?.clone();
    }
    match &node {
        serde_json::Value::String(s) => Some(s.clone()),
        serde_json::Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

/// Derive /24 base (e.g. "192.168.1.1") from an IPv4 address string.
fn ip_to_base(ip: &str) -> Option<String> {
    let parts: Vec<&str> = ip.rsplitn(2, '.').collect();
    if parts.len() == 2 {
        Some(format!("{}.1", parts[1]))
    } else {
        None
    }
}

/// Check if an IPv4 address is in a private range (RFC 1918 + common LAN ranges).
fn is_private_ipv4(ip: &str) -> bool {
    if let Ok(addr) = ip.parse::<std::net::Ipv4Addr>() {
        let octets = addr.octets();
        // 10.0.0.0/8
        if octets[0] == 10 {
            return true;
        }
        // 172.16.0.0/12
        if octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31 {
            return true;
        }
        // 192.168.0.0/16
        if octets[0] == 192 && octets[1] == 168 {
            return true;
        }
    }
    false
}

/// Return candidate /24 base IPs for LAN scanning. Uses local-ip-address to
/// enumerate all network interfaces; also includes UDP probe and comprehensive
/// fallbacks so it works regardless of LAN setup (10.x, 172.16–31.x, 192.168.x,
/// VPN, multi-NIC, offline).
fn local_ip_bases() -> Vec<String> {
    use std::collections::HashSet;
    let mut bases = HashSet::new();

    // 1. Enumerate all network interfaces (handles multi-NIC, VPN, etc.)
    if let Ok(ifaces) = local_ip_address::list_afinet_netifas() {
        for (_name, ip) in ifaces {
            let ip_str = ip.to_string();
            if is_private_ipv4(&ip_str) {
                if let Some(base) = ip_to_base(&ip_str) {
                    bases.insert(base);
                }
            }
        }
    }

    // 2. UDP probe trick for primary outbound interface (when interfaces don't yield private IPs)
    if bases.is_empty() {
        if let Ok(sock) = std::net::UdpSocket::bind("0.0.0.0:0") {
            let _ = sock.connect("8.8.8.8:80");
            if let Ok(addr) = sock.local_addr() {
                let ip = addr.ip().to_string();
                if is_private_ipv4(&ip) {
                    if let Some(base) = ip_to_base(&ip) {
                        bases.insert(base);
                    }
                }
            }
        }
    }

    // 3. Fallbacks only when interface enumeration and UDP gave no private bases
    if bases.is_empty() {
        log::info!("No subnet from interfaces; using fallback subnets for common home/office LANs");
        for fb in ["192.168.1.1", "192.168.0.1", "10.0.0.1", "172.16.0.1"] {
            bases.insert(fb.to_string());
        }
    }

    let mut result: Vec<String> = bases.into_iter().collect();
    result.sort();
    result
}
