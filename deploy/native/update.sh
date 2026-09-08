#!/usr/bin/env bash
# Update a native EMCargo installation to the latest release, or to a
# named one. This is install.sh run again: the new bundle lands next to the
# old one, the `current` link moves, the service restarts. The data directory
# is never touched. Roll back by pointing the link at the previous release:
#   ln -sfn /opt/emcargo/releases/<old version> /opt/emcargo/current && systemctl restart emcargo
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/install.sh" "$@"
