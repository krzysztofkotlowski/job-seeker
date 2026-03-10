#!/usr/bin/env bash
# Prepare Ubuntu Server for Job Seeker Tracker deployment
#
# Run on a fresh Ubuntu Server (22.04 LTS or 24.04 LTS) to install:
#   - Docker Engine & Docker Compose
#   - Git
#   - UFW firewall (SSH, HTTP, HTTPS)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/.../prepare-ubuntu-server.sh | bash
#   # or copy to server and run:
#   sudo bash prepare-ubuntu-server.sh
#
# Requires: sudo

set -euo pipefail

readonly SCRIPT_NAME="prepare-ubuntu-server"
readonly LOG_PREFIX="[${SCRIPT_NAME}]"

log() { echo "${LOG_PREFIX}" "$@"; }
log_err() { echo "${LOG_PREFIX} ERROR:" "$@" >&2; }

# --- Preflight ---
if [[ $EUID -ne 0 ]]; then
  log_err "This script must be run as root (use sudo)"
  exit 1
fi

if ! command -v apt-get &>/dev/null; then
  log_err "apt-get not found. This script targets Debian/Ubuntu."
  exit 1
fi

log "Starting Ubuntu Server preparation..."

# --- System update ---
log "Updating package index and upgrading packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# --- Essential packages ---
log "Installing essential packages..."
apt-get install -y -qq \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  unzip \
  htop

# --- Docker ---
if command -v docker &>/dev/null; then
  log "Docker already installed: $(docker --version)"
else
  log "Installing Docker Engine..."

  # Add Docker's official GPG key
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  # Add repository
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME:-jammy}") stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  systemctl enable docker
  systemctl start docker
  log "Docker installed: $(docker --version)"
fi

# --- Add current user to docker group ---
SUDO_USER="${SUDO_USER:-}"
if [[ -n "${SUDO_USER}" ]]; then
  if ! getent group docker | grep -q "\b${SUDO_USER}\b"; then
    usermod -aG docker "${SUDO_USER}"
    log "Added ${SUDO_USER} to docker group. Log out and back in for it to take effect."
  fi
fi

# --- UFW firewall ---
if command -v ufw &>/dev/null; then
  log "Configuring UFW firewall..."
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp   # SSH
  ufw allow 80/tcp   # HTTP
  ufw allow 443/tcp  # HTTPS
  ufw --force enable 2>/dev/null || true
  log "UFW rules: $(ufw status numbered 2>/dev/null | head -20 || true)"
else
  log "UFW not found; skipping firewall configuration."
fi

# --- App directory ---
APP_DIR="${APP_DIR:-/opt/jobseeker}"
log "Ensuring app directory: ${APP_DIR}"
mkdir -p "${APP_DIR}"
if [[ -n "${SUDO_USER}" ]]; then
  chown "${SUDO_USER}:${SUDO_USER}" "${APP_DIR}" 2>/dev/null || true
fi

# --- Summary ---
log "Preparation complete."
log ""
log "Next steps (from your workstation):"
log "  1. Run: ./deploy/scripts/deploy.sh kkotlowski@hp-homeserver"
log "  2. The deploy script will sync the project and create .env if needed"
log "  3. Edit .env on the server to set POSTGRES_PASSWORD, then redeploy"
log ""
log "Or deploy manually: rsync the project to ${APP_DIR}, then:"
log "  cd ${APP_DIR} && cp deploy/env.example.prod .env && docker compose -f deploy/docker-compose.prod.yml up -d"
