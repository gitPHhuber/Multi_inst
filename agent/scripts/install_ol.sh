#!/usr/bin/env bash
set -euo pipefail

dnf install -y python3 python3-pip python3-venv nodejs git
usermod -aG dialout "$USER" || true
cp "$(dirname "$0")/udev/99-fc.rules" /etc/udev/rules.d/99-fc.rules
udevadm control --reload-rules
udevadm trigger

cat <<'UNIT' > /etc/systemd/system/multi-inst-agent.service
[Unit]
Description=Multi Inst Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/env uvicorn multi_inst_agent.api.app:app --host 127.0.0.1 --port 8765
WorkingDirectory=/opt/multi-inst-agent
Restart=on-failure
User=$USER

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable multi-inst-agent.service
