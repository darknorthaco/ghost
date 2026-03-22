# GHOST Unified Installation Wizard

> **Canonical install path:** Use the **Tauri desktop app** (`ghost_app/`). See **[INSTALL.md](../INSTALL.md)** in the repository root.  
> This Python/shell tree is **deprecated** for end users. Entry points exit unless **`GHOST_ALLOW_LEGACY_INSTALLER=1`**. Policy: [CANONICAL_INSTALL_TAURI.md](CANONICAL_INSTALL_TAURI.md).

### Offline bundle (Phase 3, maintainer / air-gap)

- **Generator:** [`offline_bundle.py`](offline_bundle.py) — `generate` / `verify` subcommands; produces `wheelhouse/`, `engine/`, `models/model_catalogue.json`, `manifest.json` (SHA-256 for all files).  
- **Verification helpers:** [`offline_bundle_lib.py`](offline_bundle_lib.py) — shared with tests.  
- **Pip helper:** [`offline_install_helper.py`](offline_install_helper.py) — `--no-index` install from a bundle.  
- **Deploy requirements pin:** [`requirements-deploy.txt`](requirements-deploy.txt) — must match Tauri `install_python_deps`.  
- **Documentation:** [../docs/offline_install.md](../docs/offline_install.md)

## Overview

The GHOST Unified Installation Wizard is a modular, cross-platform installer that enables both Linux and Windows users to install the complete GHOST ecosystem with a single execution flow.

**NEW:** GHOST now includes a comprehensive uninstaller for safe and complete removal. See [UNINSTALLER.md](UNINSTALLER.md) for details.

## Features

- **Unified Entry Point**: Single wizard for the entire GHOST ecosystem
- **Cross-Platform**: Supports Linux, macOS, and Windows
- **Modular Design**: Toggle components independently
- **Worker Discovery**: Manual and comprehensive auto-detection modes
- **Virtual Environment Management**: Isolated Python environment setup
- **Optional UI Integration**: RedBlue UI can be added or removed
- **Interactive CLI**: User-friendly command-line interface
- **Installation Manifest**: Tracks all installed files for safe uninstallation

> **UI Source:** RedBlue UI lives in the private repository:
> https://github.com/darknorthaco/redblue-private

## Components

The installer can set up the following components:

1. **GHOST Core** (Required) - Distributed compute fabric
2. **LLM Task Master** (Optional) - Mode-aware task routing
3. **Linux Workers** (Optional) - Linux worker nodes with GPU support
4. **Windows Workers** (Optional) - Windows worker nodes with GPU support
5. **Security Framework** (Optional) - Multi-level security
6. **Socket Infrastructure** (Optional) - Real-time WebSocket communication
7. **RedBlue UI** (Optional) - Web-based monitoring and control (from `darknorthaco/redblue-private`)

## Quick Start

### Linux/Mac

```bash
cd installer
./ghost_installer.sh
```

### Windows

```powershell
cd installer
.\ghost_installer.ps1
```

## Installation Options

### Interactive Mode (Default)

```bash
./ghost_installer.sh
```

The wizard will guide you through:
1. System requirements check
2. Installation directory selection
3. Component selection
4. Network configuration
5. Worker discovery
6. Socket infrastructure setup
7. UI integration
8. Security configuration
9. Installation execution

### Command-Line Options

```bash
# Preview installation without making changes
./ghost_installer.sh --dry-run

# Skip virtual environment creation
./ghost_installer.sh --skip-venv

# Specify installation directory
./ghost_installer.sh --install-dir /opt/ghost
```

## Command-Line Reference

### Flags

| Flag | Description |
|------|-------------|
| `--silent` | No prompts; uses defaults for all steps |
| `--type=<all\|controller\|worker>` | Pre-select component set (default: `all`) |
| `--force` | Skip all confirmation prompts |
| `--dry-run` | Preview installation without making changes |
| `--install-dir <path>` | Override installation directory |
| `--log-file <path>` | Write timestamped log output to file |
| `--skip-venv` | Skip virtual environment creation |

### Installation Types

| Type | Components installed |
|------|---------------------|
| `all` (default) | All optional components |
| `controller` | `ghost_core` + LLM Task Master + Security Framework + Socket Infrastructure |
| `worker` | `ghost_core` + Linux/Windows Workers (OS-appropriate) + Security Framework |

### Examples

**Linux/Mac:**
```bash
# Interactive (default)
./ghost_installer.sh

# Silent full install to /opt/ghost, log to file
./ghost_installer.sh --silent --install-dir /opt/ghost --log-file /var/log/ghost_install.log

# Silent controller-only install
./ghost_installer.sh --silent --type=controller

# Silent worker install, force through system check failures
./ghost_installer.sh --silent --type=worker --force

# Dry-run preview
./ghost_installer.sh --dry-run
```

**Windows (PowerShell):**
```powershell
# Interactive (default)
.\ghost_installer.ps1

# Silent install with defaults
.\ghost_installer.ps1 -Silent

# Silent worker install with log file
.\ghost_installer.ps1 -Silent -Type worker -LogFile C:\Logs\ghost_install.log

# Dry-run preview
.\ghost_installer.ps1 -DryRun

# Show help
.\ghost_installer.ps1 -Help
```

## Worker Discovery

### Manual Mode
- Performs basic LAN ping scan
- User selects workers from discovered devices
- Quick and simple

### Comprehensive Mode
- Auto-detects workers with GHOST capability
- Queries worker information (GPU, etc.)
- Allows accept/deselect/continue flow

### Skip Mode
- Configure workers later
- Useful for single-node installations

## Directory Structure

After installation, you'll have:

```
/opt/ghost/  (or your chosen directory)
├── config/                    # Configuration files
│   ├── ghost_config.yaml   # Main config
│   ├── worker_*_config.json  # Worker configs
│   └── ...
├── logs/                      # Log files
├── data/                      # Data storage
├── venvs/                     # Virtual environments
│   └── ghost/              # Main venv
├── activate_ghost.sh        # Convenience activation script
├── environment.sh             # Environment setup
├── start_ghost.sh           # Start script
├── stop_ghost.sh            # Stop script
└── status_ghost.sh          # Status check script
```

## Post-Installation

### 1. Activate Virtual Environment

**Linux/Mac:**
```bash
source /opt/ghost/activate_ghost.sh
```

**Windows:**
```powershell
.\activate_ghost.bat
```

### 2. Verify Installation

```bash
python installer/scripts/health_check.py /opt/ghost
```

### 3. Start GHOST

```bash
/opt/ghost/start_ghost.sh
```

### 4. Check Status

```bash
/opt/ghost/status_ghost.sh
```

Or check directly:
```bash
curl http://localhost:8765/health
```

## Configuration

### Main Configuration

Edit `config/ghost_config.yaml` to customize:
- Controller settings (host, port)
- Security level
- Socket infrastructure
- UI integration
- Logging preferences

### Worker Configuration

Edit `config/worker_*_config.json` for each worker:
- Worker ID
- Controller connection
- GPU settings
- Performance tuning

## Systemd Service (Linux)

To run GHOST as a systemd service:

```bash
# Copy service file
sudo cp /tmp/ghost.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable ghost.service

# Start service
sudo systemctl start ghost.service

# Check status
sudo systemctl status ghost.service
```

## Windows Service

To run GHOST as a Windows service:

```powershell
# Run as Administrator
cd C:\Program Files\GHOST
.\install_service.ps1

# Start service
Start-Service GHOSTController

# Check status
Get-Service GHOSTController
```

## Troubleshooting

### Python Not Found

**Linux/Mac:**
```bash
# Install Python 3.8+
sudo apt-get install python3 python3-pip  # Debian/Ubuntu
brew install python3                       # macOS
```

**Windows:**
- Download from https://python.org
- Check "Add Python to PATH" during installation

### Permission Denied

**Linux/Mac:**
```bash
chmod +x ghost_installer.sh
```

### Port Already in Use

Check which process is using the port:

**Linux/Mac:**
```bash
lsof -i :8765
```

**Windows:**
```powershell
netstat -ano | findstr :8765
```

### Virtual Environment Issues

If venv creation fails, ensure `python3-venv` is installed:

```bash
sudo apt-get install python3-venv  # Debian/Ubuntu
```

## Advanced Usage

### Dry Run

Preview what will be installed without making changes:

```bash
./ghost_installer.sh --dry-run
```

### Custom Installation Directory

```bash
./ghost_installer.sh --install-dir ~/my-ghost
```

### Skip Virtual Environment

If you want to manage the virtual environment separately:

```bash
./ghost_installer.sh --skip-venv
```

## Uninstallation

To remove GHOST:

1. Stop services:
   ```bash
   /opt/ghost/stop_ghost.sh
   ```

2. Remove systemd service (if installed):
   ```bash
   sudo systemctl stop ghost.service
   sudo systemctl disable ghost.service
   sudo rm /etc/systemd/system/ghost.service
   sudo systemctl daemon-reload
   ```

3. Remove installation directory:
   ```bash
   rm -rf /opt/ghost
   ```

## Support

For issues or questions:
- Check documentation: `README.md`, `DEPLOYMENT_GUIDE.md`
- Review logs: `logs/ghost.log`
- Run health check: `python installer/scripts/health_check.py`

## Development

### Module Structure

```
installer/
├── ghost_installer.py          # Main orchestrator
├── ghost_installer.sh           # Linux/Mac entry
├── ghost_installer.ps1          # Windows entry
├── ghost_installer_windows.py   # Windows-specific logic
├── modules/                       # Core modules
│   ├── system_check.py
│   ├── component_manager.py
│   ├── worker_discovery.py
│   ├── socket_manager.py
│   ├── venv_setup.py
│   ├── ui_integration.py
│   └── config_generator.py
├── ui/                            # UI components
│   ├── cli_wizard.py
│   ├── progress_display.py
│   └── prompts.py
├── config/                        # Templates
├── scripts/                       # Post-install scripts
└── README.md                      # This file
```

### Testing

Run installer in dry-run mode to test:

```bash
./ghost_installer.sh --dry-run
```

## Uninstalling GHOST

GHOST includes a comprehensive uninstaller with two modes:

### Safe Mode (Default)
Stops services and removes runtime files, but preserves your installation and configurations:

```bash
# Linux/Mac
./ghost_uninstaller.sh

# Windows
.\ghost_uninstaller.ps1
```

### Full Mode
Completely removes GHOST, including all files and configurations (with optional backup):

```bash
# Linux/Mac
./ghost_uninstaller.sh --mode full

# Windows
.\ghost_uninstaller.ps1 -Mode full
```

For detailed uninstallation documentation, see [UNINSTALLER.md](UNINSTALLER.md).

## Installation Manifest

The installer creates an installation manifest (`.ghost_install_manifest.json`) that tracks:
- Installed components
- Created files and directories
- Service definitions
- Configuration files
- PID files and log files
- Virtual environment path

This manifest enables safe, complete uninstallation and helps track what was installed.

## License

Dual-licensed: MIT (open-source) and Commercial. See LICENSE and LICENSE-COMMERCIAL.md for details.
