#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
printf 'This removes BLACK VEIL database, cache, and message-bus volumes. Type RESET to continue: '
read answer
[ "$answer" = RESET ] || { echo 'Reset cancelled.'; exit 1; }
docker compose --env-file .env -f compose.yaml down --volumes --remove-orphans
echo 'BLACK VEIL services and persistent challenge data have been removed.'
