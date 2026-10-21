#!/bin/bash
set -e

APP_DIR="/home/ubuntu/TelegramDealAutoPoster"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="telegram-deal-poster"

echo "==> Creating app directory..."
mkdir -p "$APP_DIR"

echo "==> Creating Python venv..."
python3 -m venv "$VENV_DIR"

echo "==> Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> Writing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Telegram Deal Auto Poster Bot
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "===== Deploy complete! ====="
echo "Web Monitor: http://13.201.98.82:8000"
echo "Logs: sudo journalctl -u $SERVICE_NAME -f"
sudo systemctl status "$SERVICE_NAME" --no-pager
