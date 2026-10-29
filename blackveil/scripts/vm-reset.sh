#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

printf 'This removes only the disposable Linux guest disks and SSH keys. Type RESET-VM to continue: '
read answer
[ "$answer" = RESET-VM ] || { echo 'VM reset cancelled.'; exit 1; }

docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify rm --stop --force aether-linux-vm aether-linux-vm-patched >/dev/null 2>&1 || true
docker volume rm blackveil_linux_vm_state blackveil_linux_vm_patched_state >/dev/null 2>&1 || true
echo 'Linux VM state and operator keys removed. Application data is unchanged.'
