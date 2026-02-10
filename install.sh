#!/usr/bin/env bash
set -euo pipefail

APP_NAME="cloudflarenotifier"
SERVICE_NAME="${APP_NAME}.service"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/venv"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installer must be run as root (use sudo)."
  exit 1
fi

SERVICE_USER="${SUDO_USER:-root}"
SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"

echo "Installing ${APP_NAME} for user: ${SERVICE_USER}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "${VENV_DIR}"
fi

echo "Installing dependencies..."
${VENV_DIR}/bin/pip install --upgrade pip
${VENV_DIR}/bin/pip install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${APP_DIR}/.env" && -f "${APP_DIR}/.env.example" ]]; then
  echo "Creating .env from .env.example"
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chown "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}/.env"
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=CloudFlareNotifier Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/src/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installed and started ${SERVICE_NAME}."
echo "Check status: systemctl status ${SERVICE_NAME}"
echo "Logs: journalctl -u ${SERVICE_NAME} -f"
