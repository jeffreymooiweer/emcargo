#!/bin/bash
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Align container user with volume ownership (common on Unraid).
if [ "$(id -u)" -eq 0 ]; then
  if ! getent group emcargo >/dev/null 2>&1; then
    groupadd -g "$PGID" emcargo
  else
    groupmod -o -g "$PGID" emcargo 2>/dev/null || true
  fi
  if ! id emcargo >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -s /bin/bash emcargo
  else
    usermod -o -u "$PUID" -g "$PGID" emcargo 2>/dev/null || true
  fi

  mkdir -p /data/templates /data/exports /data/logs
  chown -R "${PUID}:${PGID}" /data

  # Where the operator mounted the Docker socket (for in-app updating),
  # hand the app user access to it: the socket carries the host's group
  # id — the docker group on most distributions, root (0) on Unraid —
  # and neither maps to anything the app user is in. Joining that gid as
  # a supplementary group grants exactly the access the operator chose
  # to give this container, and changes nothing on the host.
  if [ -S /var/run/docker.sock ]; then
    SOCK_GID="$(stat -c %g /var/run/docker.sock)"
    getent group "$SOCK_GID" >/dev/null 2>&1 || groupadd -o -g "$SOCK_GID" dockersock
    usermod -aG "$SOCK_GID" emcargo 2>/dev/null || true
  fi

  exec gosu emcargo uvicorn app.main:app --host 0.0.0.0 --port 8080
fi

mkdir -p /data/templates /data/exports /data/logs

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
