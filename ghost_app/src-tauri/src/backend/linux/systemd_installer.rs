use std::path::Path;

const UNIT_TEMPLATE: &str = r#"[Unit]
Description=GHOST API (uvicorn)
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={working_dir}
ExecStart={python} -m uvicorn ghost_api.app:app --host 127.0.0.1 --port 8765
Environment=GHOST_ENGINE_ROOT={working_dir}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"#;

pub fn generate_unit_file(user: &str, python_path: &Path, working_dir: &Path) -> String {
    UNIT_TEMPLATE
        .replace("{user}", user)
        .replace("{python}", &python_path.to_string_lossy())
        .replace("{working_dir}", &working_dir.to_string_lossy())
}
