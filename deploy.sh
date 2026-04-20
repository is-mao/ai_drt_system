#!/usr/bin/env bash
# ============================================================
# AI DRT System — Linux One-Click Deploy Script
# Usage: sudo ./deploy.sh
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=5001
SERVICE_NAME="drt"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON=""

echo "============================================"
echo "  AI DRT System — Deploy"
echo "============================================"
echo "App directory: ${APP_DIR}"
echo ""

# --- Must run as root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] Please run with sudo:  sudo ./deploy.sh"
    exit 1
fi

# --- Detect package manager ---
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
elif command -v yum &>/dev/null; then
    PKG_MGR="yum"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
else
    echo "[ERROR] Unsupported package manager. Install Python 3.10+ manually."
    exit 1
fi

# --- Install Python ---
echo "[1/6] Installing system dependencies..."
if [ "$PKG_MGR" = "apt" ]; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
elif [ "$PKG_MGR" = "yum" ] || [ "$PKG_MGR" = "dnf" ]; then
    $PKG_MGR install -y -q python3 python3-pip >/dev/null
fi

# --- Find Python >=3.10 ---
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3 not found."
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "  Python: ${PY_VERSION}"

# --- Create venv & install dependencies ---
echo "[2/6] Setting up virtual environment..."
if [ ! -d "${APP_DIR}/.venv" ]; then
    $PYTHON -m venv "${APP_DIR}/.venv"
fi
source "${APP_DIR}/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${APP_DIR}/requirements.txt" gunicorn
echo "  Dependencies installed."

# --- Generate DRT_SECRET_KEY if needed ---
echo "[3/6] Checking .env configuration..."
if [ ! -f "${APP_DIR}/.env" ]; then
    if [ -f "${APP_DIR}/.env.example" ]; then
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
        echo "  Created .env from .env.example"
    else
        touch "${APP_DIR}/.env"
        echo "  Created empty .env"
    fi
fi

# Auto-generate secret key if placeholder or missing
if grep -q "CHANGE_ME_TO_RANDOM_STRING" "${APP_DIR}/.env" 2>/dev/null; then
    NEW_KEY=$($PYTHON -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE_ME_TO_RANDOM_STRING/${NEW_KEY}/" "${APP_DIR}/.env"
    echo "  Generated DRT_SECRET_KEY."
elif ! grep -q "DRT_SECRET_KEY" "${APP_DIR}/.env" 2>/dev/null; then
    NEW_KEY=$($PYTHON -c "import secrets; print(secrets.token_hex(32))")
    echo "DRT_SECRET_KEY=${NEW_KEY}" >> "${APP_DIR}/.env"
    echo "  Added DRT_SECRET_KEY."
else
    echo "  DRT_SECRET_KEY already set."
fi

# --- Create logs directory ---
echo "[4/6] Creating directories..."
mkdir -p "${APP_DIR}/logs"

# --- Set ownership ---
# Determine the run user (prefer www-data, fallback to nobody)
RUN_USER="www-data"
if ! id "$RUN_USER" &>/dev/null; then
    RUN_USER="nobody"
fi
chown -R "${RUN_USER}:${RUN_USER}" "${APP_DIR}"
echo "  Owner set to ${RUN_USER}."

# --- Create systemd service ---
echo "[5/6] Creating systemd service..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=AI DRT System
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
echo "  Service '${SERVICE_NAME}' started on port ${PORT}."

# --- Open firewall port (best-effort) ---
echo "[6/6] Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow "${PORT}/tcp" >/dev/null 2>&1 && echo "  ufw: port ${PORT} opened." || true
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="${PORT}/tcp" >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    echo "  firewalld: port ${PORT} opened."
else
    echo "  No firewall detected. Ensure port ${PORT} is accessible."
fi

# --- Done ---
echo ""
echo "============================================"
echo "  Deploy complete!"
echo "============================================"
echo ""
echo "  URL:     http://$(hostname -I | awk '{print $1}'):${PORT}"
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
echo ""
