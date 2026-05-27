#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Netflixxp/entry-panel.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/entry-panel}"
PANEL_PORT="${PANEL_PORT:-8000}"
TZ_VALUE="${TZ:-Asia/Shanghai}"

info() {
  printf '\033[1;34m[entry-panel]\033[0m %s\n' "$1"
}

fail() {
  printf '\033[1;31m[entry-panel]\033[0m %s\n' "$1" >&2
  exit 1
}

need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    fail "Please run as root: sudo bash install.sh"
  fi
}

detect_os() {
  if [ ! -r /etc/os-release ]; then
    fail "Cannot detect OS. This installer supports Debian/Ubuntu only."
  fi
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_CODENAME="${VERSION_CODENAME:-}"
  if [ "$OS_ID" != "debian" ] && [ "$OS_ID" != "ubuntu" ]; then
    fail "Unsupported OS: ${OS_ID}. This installer supports Debian/Ubuntu only."
  fi
  if [ -z "$OS_CODENAME" ]; then
    fail "Cannot detect OS codename."
  fi
}

install_base_packages() {
  info "Installing base packages"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gnupg git
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    info "Docker and Docker Compose are already installed"
    return
  fi

  info "Installing Docker Engine and Compose plugin"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  cat >/etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${OS_ID} ${OS_CODENAME} stable
EOF

  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_panel() {
  info "Installing entry-panel to ${INSTALL_DIR}"
  if [ -d "${INSTALL_DIR}/.git" ]; then
    git -C "$INSTALL_DIR" pull
  else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi

  cd "$INSTALL_DIR"
  mkdir -p data ssh

  if [ ! -f .env ]; then
    cp .env.example .env
  fi

  if grep -q '^PANEL_PORT=' .env; then
    sed -i "s/^PANEL_PORT=.*/PANEL_PORT=${PANEL_PORT}/" .env
  else
    printf 'PANEL_PORT=%s\n' "$PANEL_PORT" >>.env
  fi

  if grep -q '^TZ=' .env; then
    sed -i "s#^TZ=.*#TZ=${TZ_VALUE}#" .env
  else
    printf 'TZ=%s\n' "$TZ_VALUE" >>.env
  fi

  info "Building and starting Docker Compose service"
  docker compose up -d --build
}

print_result() {
  SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [ -z "${SERVER_IP:-}" ]; then
    SERVER_IP="SERVER_IP"
  fi
  cat <<EOF

Install completed.

Panel URL:
  http://${SERVER_IP}:${PANEL_PORT}

Default login:
  admin / admin123

Change the password immediately after first login.

SSH key directory:
  ${INSTALL_DIR}/ssh

SSH key path inside panel:
  /ssh/id_ed25519

Update commands:
  cd ${INSTALL_DIR}
  git pull
  docker compose up -d --build

View logs:
  cd ${INSTALL_DIR}
  docker compose logs -f

EOF
}

need_root
detect_os
install_base_packages
install_docker
install_panel
print_result
