#!/bin/bash
# One-time installation of the Ouroboros Startup Verifier.
# Must be run as root on the server.
#
# Usage: sudo bash install.sh

set -euo pipefail

INSTALL_DIR="/opt/ouroboros-verifier"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Ouroboros Verifier Installation ==="

# Check root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root (sudo bash install.sh)"
    exit 1
fi

# Create install directory
echo "[1/5] Creating $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Copy files
echo "[2/5] Installing verifier scripts..."
cp "$SCRIPT_DIR/verify.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/rollback.sh" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/config.json" "$INSTALL_DIR/"

# Set permissions — root-owned, readable by all, writable only by root
chown -R root:root "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR/verify.py"
chmod 755 "$INSTALL_DIR/rollback.sh"
chmod 644 "$INSTALL_DIR/config.json"

# Initialize state files
echo "[3/5] Initializing state..."
if [ ! -f "$INSTALL_DIR/known_good.json" ]; then
    # Get current SHA as initial known-good
    CURRENT_SHA=$(cd /home/a/ouroboros_repo && git rev-parse HEAD 2>/dev/null || echo "unknown")
    cat > "$INSTALL_DIR/known_good.json" <<EOF
{
  "sha": "$CURRENT_SHA",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "branch": "main"
}
EOF
    echo "  Initial known-good SHA: $CURRENT_SHA"
fi
echo "0" > "$INSTALL_DIR/retry_count.txt"

# Install systemd service
echo "[4/5] Installing systemd service..."
cp "$SCRIPT_DIR/ouroboros-verifier.service" "$SYSTEMD_DIR/"

# Add Wants= to ouroboros.service if not already present
if [ -f "$SYSTEMD_DIR/ouroboros.service" ]; then
    if ! grep -q "ouroboros-verifier.service" "$SYSTEMD_DIR/ouroboros.service"; then
        # Add Wants= after [Unit] section
        sed -i '/^\[Unit\]/a Wants=ouroboros-verifier.service' "$SYSTEMD_DIR/ouroboros.service"
        echo "  Added Wants=ouroboros-verifier.service to ouroboros.service"
    else
        echo "  ouroboros.service already references verifier"
    fi
else
    echo "  WARNING: ouroboros.service not found at $SYSTEMD_DIR"
fi

# Reload and enable
echo "[5/5] Enabling systemd services..."
systemctl daemon-reload
systemctl enable ouroboros-verifier.service

echo ""
echo "=== Installation complete ==="
echo "  Verifier installed at: $INSTALL_DIR"
echo "  Systemd service: ouroboros-verifier.service"
echo ""
echo "  The verifier will run automatically after each ouroboros.service restart."
echo "  To test manually: /opt/ouroboros-verifier/verify.py"
echo ""
echo "  To update config: edit $INSTALL_DIR/config.json (as root)"
echo "  To update BIBLE hash: sha256sum /home/a/ouroboros/BIBLE.md"
