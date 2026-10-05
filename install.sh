#!/usr/bin/env bash
# ThemisForge installer for a fresh Debian/Ubuntu VM (re-runnable: it updates what it finds).
#
#   ./install.sh [options]
#
# Installs Docker, uv and Node when missing, builds the app, writes backend/.env with a real
# secret key and registers a systemd service so ThemisForge runs 24/7 and starts on boot.
#
#   --host ADDR     address to listen on (default 127.0.0.1; use 0.0.0.0 to reach it from your network)
#   --port N        port to listen on (default 8000)
#   --https         the site is served over HTTPS (sets secure session cookies)
#   --skip-docker   do not install Docker (use an existing one or a remote Docker host)
#   --no-service    build and configure only, do not create the systemd service
#   --dry-run       print what would happen without changing anything
#   -h, --help      show this help
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST=127.0.0.1
PORT=8000
HTTPS=0
SKIP_DOCKER=0
NO_SERVICE=0
DRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:?--host needs a value}"; shift 2 ;;
    --port) PORT="${2:?--port needs a value}"; shift 2 ;;
    --https) HTTPS=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --no-service) NO_SERVICE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h | --help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

say() { printf '\n\033[1;33m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

run() { # print the command, run it unless --dry-run
  info "\$ $*"
  [[ $DRY -eq 1 ]] || "$@"
}

[[ "$(uname -s)" == Linux ]] || die "This installer supports Linux only."
[[ $EUID -ne 0 ]] || die "Run this as your normal user, not root. It uses sudo only where needed."
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port must be a number."

SUDO="sudo"
[[ $DRY -eq 1 ]] || command -v sudo >/dev/null || die "sudo is required."

APT=0
command -v apt-get >/dev/null && APT=1

# ---------------------------------------------------------------- Docker
say "Docker"
if [[ $SKIP_DOCKER -eq 1 ]]; then
  info "skipped (--skip-docker)"
elif command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  info "already installed and reachable: $(docker --version)"
elif command -v docker >/dev/null; then
  info "installed, but this user cannot reach it. It will be added to the docker group below."
elif [[ $APT -eq 1 ]]; then
  info "installing Docker Engine with the official convenience script (https://get.docker.com)"
  if [[ $DRY -eq 1 ]]; then
    info "\$ curl -fsSL https://get.docker.com | sudo sh"
  else
    curl -fsSL https://get.docker.com | $SUDO sh
  fi
  run $SUDO systemctl enable --now docker
else
  die "No apt-get found. Install Docker Engine yourself (https://docs.docker.com/engine/install/), then re-run with --skip-docker."
fi
if [[ $SKIP_DOCKER -eq 0 ]] && { command -v docker >/dev/null || [[ $DRY -eq 1 ]]; }; then
  if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
    info "adding $USER to the docker group (members can control Docker, which is root-equivalent on this machine)"
    run $SUDO usermod -aG docker "$USER"
    info "note: this shell only sees the new group after you log out and in again; the service gets it automatically"
  fi
fi

# ---------------------------------------------------------------- uv
say "uv (Python tooling)"
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null; then
  info "already installed: $(uv --version)"
else
  info "installing uv from astral.sh"
  if [[ $DRY -eq 1 ]]; then info "\$ curl -LsSf https://astral.sh/uv/install.sh | sh"; else curl -LsSf https://astral.sh/uv/install.sh | sh; fi
fi

# ---------------------------------------------------------------- Node
say "Node.js (to build the web interface)"
node_ok() { command -v node >/dev/null && [[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ]]; }
if [[ -f "$ROOT/frontend/dist/index.html" && ! -d "$ROOT/frontend/src" ]]; then
  info "prebuilt frontend found, Node is not needed"
elif node_ok; then
  info "already installed: $(node --version)"
elif [[ $APT -eq 1 ]]; then
  info "installing Node.js LTS from NodeSource"
  if [[ $DRY -eq 1 ]]; then
    info "\$ curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -"
  else
    curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO -E bash -
  fi
  run $SUDO apt-get install -y nodejs
else
  die "Node.js 20+ is required to build the web interface. Install it, then re-run."
fi

# ---------------------------------------------------------------- build
say "Building ThemisForge"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
run bash -c "cd '$ROOT/backend' && '$UV' sync --no-dev"
run bash -c "cd '$ROOT/frontend' && npm ci --no-audit --no-fund && npm run build"

# ---------------------------------------------------------------- config
say "Configuration (backend/.env)"
ENV_FILE="$ROOT/backend/.env"
if [[ -f "$ENV_FILE" ]] && grep -q '^THEMIS_SECRET_KEY=' "$ENV_FILE" && ! grep -q 'change-me' "$ENV_FILE"; then
  info "keeping your existing $ENV_FILE"
elif [[ $DRY -eq 1 ]]; then
  info "would write $ENV_FILE with a newly generated secret key"
else
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  {
    echo "# Written by install.sh. Keep this file private: the secret key protects sessions and stored keys."
    echo "THEMIS_SECRET_KEY=$SECRET"
    [[ $HTTPS -eq 1 ]] && echo "THEMIS_COOKIE_SECURE=true"
  } >"$ENV_FILE"
  chmod 600 "$ENV_FILE"
  info "wrote $ENV_FILE with a new secret key"
fi

# ---------------------------------------------------------------- service
if [[ $NO_SERVICE -eq 1 ]]; then
  say "Service"
  info "skipped (--no-service). Start it by hand: cd backend && uv run uvicorn app.main:app --host $HOST --port $PORT"
else
  say "systemd service"
  UNIT=/etc/systemd/system/themisforge.service
  UNIT_BODY="[Unit]
Description=ThemisForge
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
User=$USER
SupplementaryGroups=docker
WorkingDirectory=$ROOT/backend
ExecStart=$ROOT/backend/.venv/bin/uvicorn app.main:app --host $HOST --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target"
  if [[ $DRY -eq 1 ]]; then
    info "would write $UNIT:"
    printf '%s\n' "$UNIT_BODY" | sed 's/^/      /'
  else
    printf '%s\n' "$UNIT_BODY" | $SUDO tee "$UNIT" >/dev/null
  fi
  run $SUDO systemctl daemon-reload
  run $SUDO systemctl enable themisforge
  run $SUDO systemctl restart themisforge

  if [[ $DRY -eq 0 ]]; then
    info "waiting for ThemisForge to come up..."
    for _ in $(seq 1 30); do
      if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then UP=1; break; fi
      sleep 1
    done
    [[ "${UP:-0}" -eq 1 ]] || die "ThemisForge did not start. See: journalctl -u themisforge -n 50"
  fi
fi

# ---------------------------------------------------------------- check
say "Checking the installation"
if [[ $DRY -eq 1 ]]; then
  info "\$ ./themis doctor"
else
  # a fresh docker group membership is not active in this shell yet, so run the check inside the group
  DOCTOR="cd '$ROOT/backend' && .venv/bin/python -m app.doctor"
  if id -nG | tr ' ' '\n' | grep -qx docker || ! getent group docker >/dev/null; then
    bash -c "$DOCTOR" || true
  else
    sg docker -c "$DOCTOR" || true
  fi
fi

say "Done"
SHOWN_HOST="$HOST"
if [[ "$HOST" == 0.0.0.0 ]]; then SHOWN_HOST="$( (hostname -I 2>/dev/null || hostname 2>/dev/null) | awk '{print $1}')"; fi
info "Open http://$SHOWN_HOST:$PORT and create your account. The first account is the administrator."
if [[ "$HOST" == 127.0.0.1 ]]; then info "It only listens on this machine. For access from elsewhere: put a reverse proxy with HTTPS in front, or re-run with --host 0.0.0.0 on a trusted network."; fi
info "Manage it with: ./themis service status | logs | restart     Health check: ./themis doctor"
