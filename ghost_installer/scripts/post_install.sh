#!/bin/bash
# GHOST Post-Installation Script
# Linux/Mac

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 GHOST Post-Installation Setup"
echo "==================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to set permissions
set_permissions() {
    echo "Setting file permissions..."
    
    # Make scripts executable
    find "$INSTALL_DIR" -name "*.sh" -type f -exec chmod +x {} \;
    
    # Set directory permissions
    chmod -R 755 "$INSTALL_DIR/config"
    chmod -R 755 "$INSTALL_DIR/logs"
    chmod -R 755 "$INSTALL_DIR/data"
    
    print_success "Permissions set"
}

# Function to create systemd service
create_systemd_service() {
    echo "Creating systemd service..."
    
    # Create PID directory
    PID_DIR="$INSTALL_DIR/run"
    mkdir -p "$PID_DIR"
    
    # Service file location (temporary, will be copied with sudo)
    SERVICE_FILE="$INSTALL_DIR/ghost.service"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=GHOST Distributed Compute Controller
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venvs/ghost/bin/python $INSTALL_DIR/run_integrated_ghost.py
ExecStop=/bin/kill \$MAINPID
PIDFile=$PID_DIR/ghost.pid
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Systemd service file created at $SERVICE_FILE"
    echo ""
    echo "  To install the service, run these commands:"
    echo "    sudo cp $SERVICE_FILE /etc/systemd/system/ghost.service"
    echo "    sudo systemctl daemon-reload"
    echo "    sudo systemctl enable ghost.service"
    echo "    sudo systemctl start ghost.service"
}

# Function to create convenience scripts
create_convenience_scripts() {
    echo "Creating convenience scripts..."
    
    # Start script
    cat > "$INSTALL_DIR/start_ghost.sh" << 'EOF'
#!/bin/bash
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$INSTALL_DIR/venvs/ghost/bin/activate"
cd "$INSTALL_DIR"
python run_integrated_ghost.py
EOF
    chmod +x "$INSTALL_DIR/start_ghost.sh"
    
    # Stop script (using PID file for safe process termination)
    cat > "$INSTALL_DIR/stop_ghost.sh" << 'EOF'
#!/bin/bash
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$INSTALL_DIR/run/ghost.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping GHOST (PID: $PID)..."
        kill "$PID"
        sleep 2
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force stopping..."
            kill -9 "$PID"
        fi
        rm -f "$PID_FILE"
        echo "✅ GHOST stopped"
    else
        echo "⚠️  PID file exists but process not running"
        rm -f "$PID_FILE"
    fi
else
    echo "❌ GHOST not running (no PID file)"
fi
EOF
    chmod +x "$INSTALL_DIR/stop_ghost.sh"
    
    # Status script
    cat > "$INSTALL_DIR/status_ghost.sh" << 'EOF'
#!/bin/bash
if pgrep -f "run_integrated_ghost.py" > /dev/null; then
    echo "✅ GHOST is running"
    curl -s http://localhost:8765/health || echo "  ⚠️ Health check failed"
else
    echo "❌ GHOST is not running"
fi
EOF
    chmod +x "$INSTALL_DIR/status_ghost.sh"
    
    print_success "Convenience scripts created"
}

# Main execution
echo "Install directory: $INSTALL_DIR"
echo ""

set_permissions
create_systemd_service
create_convenience_scripts

echo ""
echo "==================================="
print_success "Post-installation complete!"
echo "==================================="
echo ""
echo "📋 Next steps:"
echo "  1. Install systemd service (optional, requires sudo)"
echo "  2. Install Python dependencies:"
echo "     $INSTALL_DIR/venvs/ghost/bin/pip install -r requirements.txt"
echo "  3. Start GHOST:"
echo "     $INSTALL_DIR/start_ghost.sh"
echo ""
