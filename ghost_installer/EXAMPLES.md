# Installer Usage Examples

## Basic Interactive Installation

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

## Demonstration Mode

Run a non-interactive demo to see installer features:

```bash
cd installer
python3 demo_installer.py
```

Example output:
```
======================================================================
    🚀 GHOST DISTRIBUTED COMPUTE FABRIC
    Unified Installation Wizard
======================================================================

DEMO: System Requirements Check
============================================================
✅ PASSED:
  • Python 3.12.3 (>= 3.8)
  • Operating System: Linux
  • Disk space: 91.02 GB available (>= 5.0 GB)
  • Virtual environment support: Available
  • Network connectivity: OK
  • Git: git version 2.52.0
============================================================

DEMO: Component Selection
======================================================================
Available Components:
  [✓ Required] GHOST Core
  [  Optional] LLM Task Master
  [  Optional] Socket Infrastructure
  [  Optional] RedBlue UI
  ...
```

## Installation with Custom Directory

```bash
./ghost_installer.sh --install-dir ~/my-ghost
```

## Dry Run (Preview Only)

Preview what will be installed without making changes:

```bash
./ghost_installer.sh --dry-run
```

## Skip Virtual Environment

Install without creating a virtual environment:

```bash
./ghost_installer.sh --skip-venv
```

## Health Check After Installation

Verify installation:

```bash
python3 scripts/health_check.py /opt/ghost
```

Output example:
```
============================================================
HEALTH CHECK REPORT
============================================================

✅ PASSED:
  • Directory exists: config/
  • Directory exists: logs/
  • Directory exists: data/
  • Config file exists: ghost_config.yaml
  • Virtual environment exists
  • Python executable found in venv
============================================================
✅ Installation health check passed!
============================================================
```

## Post-Installation Scripts

### Linux/Mac

Run post-installation setup:
```bash
cd /opt/ghost
./scripts/post_install.sh
```

This creates:
- Systemd service configuration
- Convenience scripts (start_ghost.sh, stop_ghost.sh, status_ghost.sh)
- File permissions setup

### Windows

Run post-installation setup:
```powershell
cd C:\Program Files\GHOST
.\scripts\post_install.ps1
```

This creates:
- Windows service configuration
- Convenience scripts (start_ghost.ps1, stop_ghost.ps1, status_ghost.ps1)

## Start GHOST After Installation

### Linux/Mac
```bash
# Activate virtual environment
source /opt/ghost/activate_ghost.sh

# Start GHOST
/opt/ghost/start_ghost.sh

# Check status
/opt/ghost/status_ghost.sh
```

### Windows
```powershell
# Activate virtual environment
.\activate_ghost.bat

# Start GHOST
.\start_ghost.ps1

# Check status
.\status_ghost.ps1
```

## Worker Discovery Examples

### Manual Discovery Mode
```
Select worker discovery mode:
  [1] Manual selection (basic ping scan)
  [2] Comprehensive auto-detection
  [3] Skip (configure workers later)

Selection: 1

🔍 Scanning network 192.168.1.0/24...
  Found: 192.168.1.102
  Found: 192.168.1.103
  Found: 192.168.1.104

Discovered workers:
  ✓ [1] 192.168.1.102 - Worker1
  ✓ [2] 192.168.1.103 - Worker2
  ✓ [3] 192.168.1.104 - Worker3

Select workers to configure [enter space-separated numbers]: 1 2
```

### Comprehensive Discovery Mode
```
Select worker discovery mode:
  [1] Manual selection (basic ping scan)
  [2] Comprehensive auto-detection
  [3] Skip (configure workers later)

Selection: 2

🔍 Auto-discovering GHOST workers on 192.168.1.0/24...
  ✓ Found: 192.168.1.102:8090 - Worker1
  ✓ Found: 192.168.1.103:8091 - Worker2

Discovered workers:
  ✓ [1] 192.168.1.102 - Worker1 (GPU: RTX 3080)
  ✓ [2] 192.168.1.103 - Worker2 (GPU: RTX 4090)

Select workers to configure? [Y/n]: Y
```

## Component Selection Examples

### Install All Components
```
Select components to install:
(Required components will be installed automatically)

  [✓ Required] GHOST Core
      Core distributed compute fabric
  [  Optional] LLM Task Master
      Mode-aware intelligent task routing
  [  Optional] Linux Workers
      Linux worker nodes with GPU support
  [  Optional] Security Framework
      Multi-level security with authentication
  [  Optional] Socket Infrastructure
      WebSocket-based real-time communication
  [  Optional] RedBlue UI
      Web-based monitoring and control UI

Install all optional components? [Y/n]: Y
```

### Selective Installation
```
Install all optional components? [Y/n]: n

Select optional components to install:
  [1] LLM Task Master
  [2] Linux Workers
  [3] Security Framework
  [4] Socket Infrastructure
  [5] RedBlue UI

Enter space-separated numbers (e.g., '1 3 5') or 'all' for all options
Selection: 1 4 5

Selected Components:
  • GHOST Core
  • LLM Task Master
  • Socket Infrastructure
  • RedBlue UI
```

## Security Configuration Examples

```
Select security level:
  [1] Disabled
  [2] Development
  [3] Production

Select option [1-3] (default: 1): 2

✅ Security level set to: development
```

## Network Configuration Examples

```
Controller host address [localhost]: 192.168.1.103
Controller port [8080]: 8080
Socket port [8081]: 8081
UI port [3000]: 3000
```

## Full Installation Summary

```
====================================
Installation Summary
====================================
Installation Directory: /opt/ghost
Controller: 192.168.1.103:8080
Security Level: development
Socket Infrastructure: Enabled
RedBlue UI: Enabled

Selected Components:
  • GHOST Core
  • LLM Task Master
  • Socket Infrastructure
  • Security Framework
  • RedBlue UI

Configured Workers: 2
  • 192.168.1.102 - Worker1
  • 192.168.1.103 - Worker2

Proceed with installation? [Y/n]: Y
```
