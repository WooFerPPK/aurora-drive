#!/usr/bin/env bash
# Build the client and publish the dist tree to /var/www/fh6 (the nginx
# webroot for the FH6 racer dashboard). Sudo is only needed if the
# webroot isn't writable by the current user; the script will fall back
# to sudo automatically.
#
# Usage:
#   scripts/deploy.sh                # full build + publish + nginx reload
#   scripts/deploy.sh --no-reload    # skip nginx reload
#   scripts/deploy.sh --webroot DIR  # target a different webroot
#   scripts/deploy.sh --skip-install # don't run `npm ci` even on first run

set -euo pipefail

# Resolve script + project dirs from this file's location so the script
# works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENT_DIR="$ROOT_DIR/client"

WEBROOT="/var/www/fh6"
RELOAD_NGINX=1
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --webroot)      WEBROOT="$2"; shift 2 ;;
    --no-reload)    RELOAD_NGINX=0; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

# Pick the right write strategy. If we can write to the webroot directly,
# do; otherwise use sudo. Don't run sudo unnecessarily — it pings for a
# password and we'd rather not.
maybe_sudo() {
  if [[ -w "$(dirname "$WEBROOT")" && ( ! -e "$WEBROOT" || -w "$WEBROOT" ) ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

cd "$CLIENT_DIR"

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  if [[ ! -d node_modules || ! -e node_modules/.package-lock.json ]]; then
    echo "==> installing dependencies"
    if [[ -e package-lock.json ]]; then
      npm ci
    else
      npm install
    fi
  fi
fi

echo "==> building (vite)"
npm run build

if [[ ! -d "$CLIENT_DIR/dist" ]]; then
  echo "build produced no dist/ directory" >&2
  exit 1
fi

echo "==> publishing to $WEBROOT"
maybe_sudo mkdir -p "$WEBROOT"

# Mirror dist/ -> webroot. Prefer rsync if available so unchanged files
# don't get re-pushed; fall back to cp for portability.
if command -v rsync >/dev/null 2>&1; then
  maybe_sudo rsync -a --delete "$CLIENT_DIR/dist/" "$WEBROOT/"
else
  maybe_sudo rm -rf "$WEBROOT"
  maybe_sudo mkdir -p "$WEBROOT"
  maybe_sudo cp -R "$CLIENT_DIR/dist/." "$WEBROOT/"
fi

if [[ "$RELOAD_NGINX" -eq 1 ]] && command -v nginx >/dev/null 2>&1; then
  echo "==> reloading nginx"
  if maybe_sudo nginx -t; then
    maybe_sudo systemctl reload nginx 2>/dev/null \
      || maybe_sudo service nginx reload 2>/dev/null \
      || maybe_sudo nginx -s reload
  else
    echo "nginx -t failed; skipping reload" >&2
    exit 1
  fi
fi

echo "==> done"
echo "    served at: http://localhost/"
echo "    webroot:   $WEBROOT"
