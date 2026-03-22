use std::path::Path;
use tokio::process::Command;

/// Register a Windows service that runs the GHOST FastAPI stack via uvicorn (venv Python).
pub async fn install_uvicorn_service(
    service_name: &str,
    display_name: &str,
    python_path: &Path,
    working_dir: &Path,
    host: &str,
    port: u16,
) -> Result<(), String> {
    let py = python_path.to_string_lossy();
    let wd = working_dir.to_string_lossy();
    let bin_path = format!(
        "cmd.exe /c cd /d \"{wd}\" && \"{py}\" -m uvicorn ghost_api.app:app --host {host} --port {port}"
    );

    let output = Command::new("sc")
        .args([
            "create",
            service_name,
            &format!("binPath={bin_path}"),
            &format!("DisplayName={display_name}"),
            "start=demand",
        ])
        .output()
        .await
        .map_err(|e| format!("sc create failed: {e}"))?;

    if !output.status.success() {
        return Err(format!(
            "sc create failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    Ok(())
}

pub async fn uninstall_service(service_name: &str) -> Result<(), String> {
    let output = Command::new("sc")
        .args(["delete", service_name])
        .output()
        .await
        .map_err(|e| format!("sc delete failed: {e}"))?;

    if !output.status.success() {
        return Err(format!(
            "sc delete failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    Ok(())
}
