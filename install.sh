#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
readonly SCRIPT_VERSION="2026-10-18.1"
# Add a real installer adapter here to extend the numbered menu.
readonly -a PROTOCOLS=(trojan hysteria2)
declare -Ar REPOSITORIES=([trojan]=trojan-installer [hysteria2]=hysteria2-installer)
declare -Ar REVISIONS=([trojan]=4ee3336406f7e00b48ab5c06b12a3db3a7315ae9 [hysteria2]=12d4cfe1943b9b405a5cd92fad1dd9705eac4f9e)
declare -Ar CHECKSUMS=([trojan]=48f9625372dee94b90ef157ce3116f67b1ec3c65b444b0b3a5f8c94507fb6914 [hysteria2]=aefcd525e6ae5b243b7de641ea0158f1a4740f37ade1e3fcf8ee43adf9332c5d)
declare -Ar CONFIGS=([trojan]=/etc/trojan/server.json [hysteria2]=/etc/hysteria/config.yaml)
TARGET=""
DOMAIN=""
EMAIL=""
SINGLE_PORT=""
SINGLE_PASSWORD_FILE=""
PASSWORD_STDIN=0
REINSTALL=0
YES=0
DRY_RUN=0
NO_BBR=0
NO_MASQUERADE=0
HTTPS_PORT=0
WORK_DIR=""
STDIN_PASSWORD=""
declare -A DOMAINS=([trojan]="" [hysteria2]="")
declare -A PORTS=([trojan]=443 [hysteria2]=443)
declare -A VERSIONS=([trojan]=latest [hysteria2]="")
declare -A PASSWORD_FILES=([trojan]="" [hysteria2]="")
declare -a SELECTED=() PENDING=()

die() { printf 'mofatizi-installer: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }
usage() {
  cat <<EOF
mofatizi-installer ${SCRIPT_VERSION}
Usage: install.sh [install] [all|trojan|hysteria2] [options]
No selection: show 1) all, 2) trojan, 3) hysteria2.

  --protocol NAME             all, trojan, hysteria2 (hy2 alias)
  --domain DOMAIN             Default domain for selected protocols
  --trojan-domain DOMAIN      Override Trojan domain
  --hysteria2-domain DOMAIN   Override Hysteria domain
  --email EMAIL               Certificate account email
  --port PORT                 Port for a single selected protocol
  --trojan-port PORT          TCP port, default 443
  --hysteria2-port PORT       UDP port, default 443
  --hysteria2-https-port PORT Optional TCP HTTPS page, default disabled
  --password-stdin           Original password for a single protocol
  --password-file PATH       Password file for a single protocol
  --trojan-password-file PATH / --hysteria2-password-file PATH
  --trojan-version VERSION   Default latest stable Trojan-GFW
  --hysteria2-version VERSION  Default official Hysteria version
  --no-bbr                   Skip Trojan kernel TCP BBR setup
  --no-masquerade            Omit Hysteria HTTP/3/HTTPS page
  --reinstall                Replace selected existing installs (backs up config)
  --yes                      Skip child overwrite confirmation; requires --reinstall
  --dry-run                  Show plan; no downloads or installation
  -h, --help                 Show help

Existing configurations are preserved/skipped unless --reinstall is supplied.
TCP 80 is needed for certificates. Allow selected TCP/UDP proxy ports too.
EOF
}
set_target() {
  local value="$1"
  [[ "$value" != hy2 ]] || value=hysteria2
  [[ -z "$TARGET" || "$TARGET" == "$value" ]] || die "Conflicting protocol selections."
  case "$value" in all|trojan|hysteria2) TARGET="$value" ;; *) die "Unknown protocol: $value" ;; esac
}
parse_args() {
  local key value
  while (($#)); do
    key="$1"
    case "$key" in
      install) shift; continue ;;
      all|trojan|hysteria2|hy2) set_target "$key"; shift; continue ;;
      --password-stdin) PASSWORD_STDIN=1; shift; continue ;;
      --reinstall) REINSTALL=1; shift; continue ;;
      --yes|-y) YES=1; shift; continue ;;
      --dry-run) DRY_RUN=1; shift; continue ;;
      --no-bbr) NO_BBR=1; shift; continue ;;
      --no-masquerade) NO_MASQUERADE=1; shift; continue ;;
      --help|-h) usage; exit 0 ;;
      --protocol|--domain|--email|--port|--password-file|--trojan-domain|--hysteria2-domain|--trojan-port|--hysteria2-port|--hysteria2-https-port|--trojan-password-file|--hysteria2-password-file|--trojan-version|--hysteria2-version)
        (($# >= 2)) || die "Missing value for $key"
        value="$2"
        [[ -n "$value" ]] || die "Empty value for $key"
        ;;
      *) die "Unknown argument: $key" ;;
    esac
    case "$key" in
      --protocol) set_target "$value" ;;
      --domain) DOMAIN="${value,,}" ;;
      --email) EMAIL="$value" ;;
      --port) SINGLE_PORT="$value" ;;
      --password-file) SINGLE_PASSWORD_FILE="$value" ;;
      --trojan-domain) DOMAINS[trojan]="${value,,}" ;;
      --hysteria2-domain) DOMAINS[hysteria2]="${value,,}" ;;
      --trojan-port) PORTS[trojan]="$value" ;;
      --hysteria2-port) PORTS[hysteria2]="$value" ;;
      --hysteria2-https-port) HTTPS_PORT="$value" ;;
      --trojan-password-file) PASSWORD_FILES[trojan]="$value" ;;
      --hysteria2-password-file) PASSWORD_FILES[hysteria2]="$value" ;;
      --trojan-version) VERSIONS[trojan]="$value" ;;
      --hysteria2-version) VERSIONS[hysteria2]="$value" ;;
    esac
    shift 2
  done
}
prompt() {
  local destination="$1" message="$2" fd
  if [[ -t 0 ]] && (( ! PASSWORD_STDIN )); then
    exec {fd}<&0
  elif ! { exec {fd}</dev/tty; } 2>/dev/null; then
    die "No terminal; specify protocol, domain and email as arguments."
  fi
  IFS= read -r -u "$fd" -p "$message" "$destination" || die "Input cancelled."
  exec {fd}<&-
}
choose_protocol() {
  [[ -z "$TARGET" ]] || return 0
  local choice i
  info '1: all'
  for i in "${!PROTOCOLS[@]}"; do printf '%s: %s\n' "$((i+2))" "${PROTOCOLS[i]}"; done
  prompt choice 'Select: '
  case "$choice" in
    1|all) TARGET=all ;;
    *)
      for i in "${!PROTOCOLS[@]}"; do
        if [[ "$choice" == "$((i+2))" || "$choice" == "${PROTOCOLS[i]}" ]]; then
          TARGET="${PROTOCOLS[i]}"; return 0
        fi
      done
      die "Invalid selection: $choice"
      ;;
  esac
}
valid_domain() {
  local name="$1" label
  local -a labels
  [[ "$name" != .* && "$name" != *. && "$name" != *..* && ${#name} -le 220 ]] || return 1
  IFS=. read -r -a labels <<<"$name"
  ((${#labels[@]} >= 2)) || return 1
  for label in "${labels[@]}"; do
    [[ "$label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]] || return 1
  done
}
validate_port() {
  [[ "$1" =~ ^[0-9]{1,5}$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535))
}
read_password_file() {
  local path="$1" password=""
  [[ -f "$path" && -r "$path" ]] || die "Cannot read password file: $path"
  IFS= read -r password <"$path" || [[ -n "$password" ]] || die "Empty password file: $path"
  [[ "$password" =~ ^[A-Za-z0-9._-]{12,128}$ ]] || die "Password requires 12-128 letters, digits, '.', '_' or '-'."
  printf '%s' "$password"
}
prepare_plan() {
  local protocol port
  if [[ "$TARGET" == all ]]; then
    SELECTED=("${PROTOCOLS[@]}")
    [[ -z "$SINGLE_PORT" && -z "$SINGLE_PASSWORD_FILE" && "$PASSWORD_STDIN" == 0 ]] ||
      die "For all, use protocol-specific ports and password files."
  else
    SELECTED=("$TARGET")
    [[ -z "$SINGLE_PORT" ]] || PORTS[$TARGET]="$SINGLE_PORT"
    [[ -z "$SINGLE_PASSWORD_FILE" ]] || PASSWORD_FILES[$TARGET]="$SINGLE_PASSWORD_FILE"
    (( ! PASSWORD_STDIN )) || [[ -z "${PASSWORD_FILES[$TARGET]}" ]] || die "Choose stdin or a password file."
  fi
  for protocol in "${SELECTED[@]}"; do
    if [[ -e "${CONFIGS[$protocol]}" ]] && (( ! REINSTALL )); then
      info "SKIP $protocol: existing configuration preserved (${CONFIGS[$protocol]})."
      continue
    fi
    PENDING+=("$protocol")
    port="${PORTS[$protocol]}"
    validate_port "$port" || die "Invalid $protocol port."
    PORTS[$protocol]=$((10#$port))
    if [[ "$protocol" == trojan ]]; then
      ((PORTS[$protocol] != 80 && PORTS[$protocol] != 18080)) || die "Trojan TCP 80/18080 are reserved."
      [[ "${VERSIONS[$protocol]}" == latest || "${VERSIONS[$protocol]}" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Invalid Trojan version."
    else
      [[ -z "${VERSIONS[$protocol]}" || "${VERSIONS[$protocol]}" =~ ^v?2\.[0-9]+\.[0-9]+$ ]] || die "Invalid Hysteria version."
      [[ "$HTTPS_PORT" =~ ^[0-9]{1,5}$ ]] || die "Invalid HTTPS port."
      HTTPS_PORT=$((10#$HTTPS_PORT))
      ((HTTPS_PORT == 0)) || { validate_port "$HTTPS_PORT" && ((HTTPS_PORT != 80)); } || die "Invalid HTTPS port."
      (( ! NO_MASQUERADE || HTTPS_PORT == 0 )) || die "HTTPS page cannot be enabled with --no-masquerade."
    fi
    [[ -n "${DOMAINS[$protocol]}" ]] || DOMAINS[$protocol]="$DOMAIN"
    if [[ -z "${DOMAINS[$protocol]}" ]]; then
      local value
      prompt value "$protocol domain: "
      DOMAINS[$protocol]="${value,,}"
    fi
    valid_domain "${DOMAINS[$protocol]}" || die "Invalid $protocol domain."
    if [[ -n "${PASSWORD_FILES[$protocol]}" ]]; then
      read_password_file "${PASSWORD_FILES[$protocol]}" >/dev/null
    fi
  done
  ((${#PENDING[@]})) || return 0
  [[ -n "$EMAIL" ]] || prompt EMAIL 'Certificate email: '
  [[ "$EMAIL" =~ ^[A-Za-z0-9.!_%+\-]+@[A-Za-z0-9.-]+$ ]] && valid_domain "${EMAIL#*@}" || die "Invalid email."
  local localpart="${EMAIL%@*}"
  [[ "$localpart" != .* && "$localpart" != *. && "$localpart" != *..* ]] || die "Invalid email."
  if [[ " ${PENDING[*]} " == *' trojan '* && " ${PENDING[*]} " == *' hysteria2 '* ]] && ((HTTPS_PORT == PORTS[trojan])); then
    die "Hysteria TCP HTTPS page conflicts with Trojan TCP port. Change --hysteria2-https-port or leave it disabled."
  fi
  if ((PASSWORD_STDIN && ! DRY_RUN)); then
    IFS= read -r STDIN_PASSWORD || [[ -n "$STDIN_PASSWORD" ]] || die "No password on stdin."
    [[ "$STDIN_PASSWORD" =~ ^[A-Za-z0-9._-]{12,128}$ ]] || die "Invalid password; refusing to replace it with a random one."
  fi
}
download_installer() {
  local protocol="$1" destination="$2"
  local revision="${REVISIONS[$protocol]}" digest="${CHECKSUMS[$protocol]}"
  [[ "$revision" =~ ^[0-9a-f]{40}$ && "$digest" =~ ^[0-9a-f]{64}$ ]] || die "Installer manifest is incomplete."
  curl -q -fL --proto '=https' --tlsv1.2 --retry 2 --connect-timeout 15 --max-time 120 \
    "https://raw.githubusercontent.com/sxmad/${REPOSITORIES[$protocol]}/${revision}/install.sh" -o "$destination" || die "Download failed: $protocol"
  printf '%s  %s\n' "$digest" "$destination" | sha256sum -c - >/dev/null || die "Installer checksum mismatch: $protocol"
  bash -n "$destination" || die "Invalid installer syntax: $protocol"
}
run_installer() {
  local protocol="$1" script="$2" password=""
  local -a args=(install --domain "${DOMAINS[$protocol]}" --email "$EMAIL" --port "${PORTS[$protocol]}")
  [[ -z "${VERSIONS[$protocol]}" ]] || args+=(--version "${VERSIONS[$protocol]}")
  if [[ "$protocol" == trojan ]]; then
    (( ! NO_BBR )) || args+=(--no-bbr)
  else
    ((HTTPS_PORT == 0)) || args+=(--https-port "$HTTPS_PORT")
    (( ! NO_MASQUERADE )) || args+=(--no-masquerade)
  fi
  (( ! YES )) || args+=(--yes)
  if [[ -n "${PASSWORD_FILES[$protocol]}" ]]; then
    password="$(read_password_file "${PASSWORD_FILES[$protocol]}")" || return 1
  elif ((PASSWORD_STDIN)); then
    password="$STDIN_PASSWORD"
  fi
  if [[ -n "$password" ]]; then
    printf '%s\n' "$password" | bash "$script" "${args[@]}" --password-stdin
  else
    bash "$script" "${args[@]}"
  fi
}
main() {
  parse_args "$@"
  choose_protocol
  prepare_plan
  local protocol completed=""
  for protocol in "${PENDING[@]}"; do
    info "INSTALL $protocol: domain=${DOMAINS[$protocol]} port=${PORTS[$protocol]}"
  done
  if ((DRY_RUN)) || ((${#PENDING[@]} == 0)); then return 0; fi
  [[ "$EUID" == 0 ]] || die "Run with sudo or as root."
  command -v curl >/dev/null && command -v sha256sum >/dev/null && command -v flock >/dev/null || die "Install curl, coreutils and util-linux first."
  exec 8>/run/lock/mofatizi-installer.lock
  flock -n 8 || die "Another unified installer is running."
  WORK_DIR="$(mktemp -d)"
  trap 'rm -rf -- "$WORK_DIR"' EXIT
  # Validate every download before the first installer makes changes.
  for protocol in "${PENDING[@]}"; do download_installer "$protocol" "$WORK_DIR/$protocol.sh"; done
  for protocol in "${PENDING[@]}"; do
    if run_installer "$protocol" "$WORK_DIR/$protocol.sh"; then
      completed+=" $protocol"
    else
      die "Failed: $protocol. Completed:${completed:- none}. Existing/other successful services are retained; fix the reported error before retrying."
    fi
  done
  info "Installation completed:${completed}. Verify public connectivity in Shadowrocket."
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
