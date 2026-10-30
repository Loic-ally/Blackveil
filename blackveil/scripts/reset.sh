#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
printf 'This removes BLACK VEIL database, cache, message-bus, and Linux VM state. Type RESET to continue: '
read answer
[ "$answer" = RESET ] || { echo 'Reset cancelled.'; exit 1; }
docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify --profile validator down --volumes --remove-orphans
echo 'BLACK VEIL services, application data, and Linux VM state have been removed.'
