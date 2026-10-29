#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

printf 'This removes only the disposable Linux guest disks and SSH keys. Type RESET-VM to continue: '
read answer
[ "$answer" = RESET-VM ] || { echo 'VM reset cancelled.'; exit 1; }

docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify rm --stop --force aether-linux-vm aether-linux-vm-patched >/dev/null 2>&1 || true
docker compose --env-file .env -f compose.yaml rm --stop --force aether-api >/dev/null 2>&1 || true
project=$(sed -n 's/^BLACKVEIL_PROJECT=//p' .env); project=${project:-blackveil}
for volume in "${project}_linux_vm_state" "${project}_linux_vm_patched_state"; do
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    docker volume rm "$volume" >/dev/null
  fi
done
docker compose --env-file .env -f compose.yaml up -d --build aether-api
echo 'Linux VM state and operator keys removed. The API was restarted; application data is unchanged.'
