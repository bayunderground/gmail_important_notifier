#!/bin/bash
# Deploy GmailImportantNotifier on a VPS: venv + deps + systemd service + renew timer.
# Run ON the VPS from the project directory (or pass PROJECT_DIR).
#
#   bash deploy_vps.sh
#   PROJECT_DIR=/opt/gmail_important_notifier bash deploy_vps.sh
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-gmail-important-notifier}"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
APP_USER="${APP_USER:-$(id -un)}"
APP_PORT="${APP_PORT:-8080}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
UNIT_DIR="/etc/systemd/system"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -f "$PROJECT_DIR/main.py" ] || die "main.py not found in $PROJECT_DIR"
[ -f "$PROJECT_DIR/.env" ] || die ".env missing in $PROJECT_DIR — copy .env.example and fill it in"
[ -f "$PROJECT_DIR/requirements.txt" ] || die "requirements.txt missing in $PROJECT_DIR"

run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        die "need root (or sudo) for: $*"
    fi
}

log "Installing system packages (python3, venv)…"
if command -v apt-get >/dev/null 2>&1; then
    run_root apt-get update -qq
    run_root apt-get install -y -qq python3 python3-venv python3-pip curl
elif command -v dnf >/dev/null 2>&1; then
    run_root dnf install -y python3 python3-pip curl
elif command -v yum >/dev/null 2>&1; then
    run_root yum install -y python3 python3-pip curl
else
    log "Unknown package manager — ensure python3 + venv are installed"
fi

log "Creating venv and installing requirements…"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q

log "Writing systemd unit: $SERVICE_NAME.service"
run_root tee "$UNIT_DIR/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=GmailImportantNotifier (Flask + gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$PROJECT_DIR
# python-dotenv loads .env from WorkingDirectory
ExecStart=$VENV_DIR/bin/gunicorn -b 0.0.0.0:$APP_PORT -w 2 --timeout 60 main:app
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

log "Writing systemd timer: $SERVICE_NAME-renew.timer (every 6h → /tasks/renew)"
run_root tee "$UNIT_DIR/$SERVICE_NAME-renew.service" >/dev/null <<EOF
[Unit]
Description=Trigger GmailImportantNotifier renew sweep

[Service]
Type=oneshot
User=$APP_USER
ExecStart=/usr/bin/curl -fsS -m 60 http://127.0.0.1:$APP_PORT/tasks/renew
EOF

run_root tee "$UNIT_DIR/$SERVICE_NAME-renew.timer" >/dev/null <<EOF
[Unit]
Description=Run GmailImportantNotifier renew every 6 hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

log "Reloading systemd, enabling + starting service…"
run_root systemctl daemon-reload
run_root systemctl enable --now "$SERVICE_NAME.service"
run_root systemctl restart "$SERVICE_NAME.service"
run_root systemctl enable --now "$SERVICE_NAME-renew.timer"
run_root systemctl restart "$SERVICE_NAME-renew.timer"

log "Waiting for health check on :$APP_PORT…"
sleep 2
if curl -fsS -m 10 "http://127.0.0.1:$APP_PORT/" >/dev/null; then
    log "Health check OK"
else
    run_root systemctl status "$SERVICE_NAME.service" --no-pager -l || true
    run_root journalctl -u "$SERVICE_NAME.service" -n 40 --no-pager || true
    die "service did not become healthy"
fi

log "Done."
cat <<EOF

Service:   $SERVICE_NAME.service  (enabled, running)
Timer:     $SERVICE_NAME-renew.timer  (every 6h)
Port:      0.0.0.0:$APP_PORT
Project:   $PROJECT_DIR
User:      $APP_USER

Useful commands:
  systemctl status  $SERVICE_NAME
  journalctl -u $SERVICE_NAME -f
  systemctl list-timers $SERVICE_NAME-renew

After this is up, point the Gmail Pub/Sub push subscription at:
  http://<VPS_IP_OR_DOMAIN>:$APP_PORT/tasks/gmail-push
and update PUBSUB_PUSH_AUDIENCE in .env to match, then restart the service.
Then run ./disable_gae.sh to stop the App Engine copy.
EOF
