#!/usr/bin/env bash
set -euo pipefail

# Idempotent deploy script for SC2GG Bot on Linux VPS (systemd + uv, no Docker).
# Touches ONLY:
#   - system user: sc2gg
#   - /opt/sc2gg_bot
#   - /var/lib/sc2gg_bot
#   - /etc/systemd/system/sc2gg-bot.service
# Does NOT modify firewall, ports, nginx, xray/sing-box, or any other services.

APP_DIR="${APP_DIR:-/opt/sc2gg_bot}"
DATA_DIR="${DATA_DIR:-/var/lib/sc2gg_bot}"
SERVICE_NAME="sc2gg-bot"
SERVICE_USER="sc2gg"
BRANCH="${BRANCH:-master}"
REPO_URL="${REPO_URL:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: Please run as root (e.g. sudo bash deploy.sh)" >&2
  exit 1
fi

echo "==> [1/6] Checking system user '${SERVICE_USER}'..."
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "==> [2/6] Checking git & uv..."
if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq git curl
fi

export PATH="/root/.local/bin:/usr/local/bin:${PATH}"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="/root/.local/bin:${PATH}"
fi

echo "==> [3/6] Updating repository in ${APP_DIR}..."
mkdir -p "${APP_DIR}" "${DATA_DIR}"
if [[ -d "${APP_DIR}/.git" ]]; then
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" fetch origin "${BRANCH}"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" checkout "${BRANCH}"
  git -c safe.directory="${APP_DIR}" -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
else
  if [[ -z "${REPO_URL}" ]]; then
    echo "ERROR: ${APP_DIR} is not a git repo and REPO_URL is not set." >&2
    echo "Run: REPO_URL=<git-url> bash $0" >&2
    exit 1
  fi
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

echo "==> [4/6] Installing Python 3.12 & dependencies via uv..."
cd "${APP_DIR}"
if [[ ! -d "${APP_DIR}/.venv" ]]; then
  uv venv --python 3.12 "${APP_DIR}/.venv"
fi
uv pip install --python "${APP_DIR}/.venv/bin/python" -e "${APP_DIR}"

echo "==> [5/6] Configuring systemd unit (${SERVICE_NAME})..."
cp "${APP_DIR}/deploy/sc2gg-bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" "${DATA_DIR}"
chmod 750 "${DATA_DIR}"
systemctl daemon-reload

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  sed -i "s|^DATA_DIR=.*|DATA_DIR=${DATA_DIR}|" "${APP_DIR}/.env"
  chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo ""
  echo "=================================================================="
  echo "FIRST-TIME SETUP: Created ${APP_DIR}/.env from .env.example"
  echo "Fill BOT_TOKEN, MINI_APP_URL, MINI_APP_SHORT_NAME, GITHUB_TOKEN, GITHUB_REPO,"
  echo "then re-run: bash ${APP_DIR}/deploy/deploy.sh"
  echo "=================================================================="
  exit 0
fi

if grep -q "^BOT_TOKEN=your_telegram_bot_token" "${APP_DIR}/.env" || ! grep -q "^BOT_TOKEN=." "${APP_DIR}/.env"; then
  echo "ERROR: BOT_TOKEN is not configured in ${APP_DIR}/.env" >&2
  exit 1
fi

echo "==> [6/6] Restarting ${SERVICE_NAME}..."
systemctl enable "${SERVICE_NAME}" >/dev/null
systemctl restart "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager -l
