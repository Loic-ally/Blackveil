#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

compose='docker compose --env-file .env -f compose.yaml'
project=$(sed -n 's/^BLACKVEIL_PROJECT=//p' .env); project=${project:-blackveil}
port=$(sed -n 's/^BLACKVEIL_HTTPS_PORT=//p' .env); port=${port:-443}
$compose config --quiet

for service in aether-web aether-api aether-auth aether-migrate aether-legacy aether-worker aether-telemetry aether-db aether-cache aether-bus aether-validator aether-linux-vm aether-linux-vm-patched; do
  id=$($compose ps -q "$service")
  [ -n "$id" ] || continue
  ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$id")
  [ "$ports" = 'null' ] || [ "$ports" = '{}' ] || { echo "FAIL: $service has a host-published port: $ports"; exit 1; }
done

gateway=$($compose ps -q aether-gateway)
[ -n "$gateway" ] || { echo 'FAIL: gateway is not running'; exit 1; }
gateway_ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$gateway")
python3 - "$gateway_ports" "$port" <<'PY'
import json, sys
bindings=json.loads(sys.argv[1] or "null") or {}
assert set(bindings) == {"443/tcp"}, f"gateway published unexpected host ports: {bindings}"
assert all(item["HostPort"] == sys.argv[2] for item in bindings["443/tcp"]), bindings
PY

gateway_networks=$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$gateway")
case "$gateway_networks" in *"${project}_data_internal"*) echo 'FAIL: gateway is attached to the data network'; exit 1;; esac
case "$gateway_networks" in *"${project}_lab_internal"*) echo 'FAIL: gateway is attached to the Linux lab network'; exit 1;; esac
for service in aether-web aether-api aether-auth aether-migrate aether-legacy aether-worker aether-telemetry aether-db aether-cache aether-bus aether-validator aether-linux-vm aether-linux-vm-patched; do
  id=$($compose ps -q "$service")
  [ -n "$id" ] || continue
  networks=$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$id")
  case "$networks" in *"${project}_edge"*) echo "FAIL: $service is attached to the player network"; exit 1;; esac
  if [ "$service" = aether-api ] || [ "$service" = aether-worker ]; then
    case "$networks" in *"${project}_lab_internal"*) :;; *) echo "FAIL: $service is not attached to the private lab network"; exit 1;; esac
  fi
  if [ "$service" = aether-linux-vm ] || [ "$service" = aether-linux-vm-patched ]; then
    case "$networks" in *"${project}_lab_internal"*) :;; *) echo "FAIL: $service is not on the private lab network"; exit 1;; esac
    case "$networks" in *"${project}_data_internal"*|*"${project}_app_internal"*) echo "FAIL: $service is attached to a non-lab application network"; exit 1;; esac
  fi
done

api=$($compose ps -q aether-api)
api_mounts=$(docker inspect --format '{{json .Mounts}}' "$api")
python3 - "$api_mounts" "$project" <<'PY'
import json, sys
mounts=json.loads(sys.argv[1])
state=[m for m in mounts if m["Destination"] == "/var/lib/aether-vm"]
assert len(state) == 1, f"API must have exactly one Linux VM state mount: {state}"
assert state[0]["Type"] == "volume" and state[0]["Name"] == sys.argv[2] + "_linux_vm_state", state[0]
assert state[0]["RW"] is False, f"API Linux VM state mount must be read-only: {state[0]}"
PY

docker network inspect "${project}_app_internal" --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: app network is not internal'; exit 1; }
docker network inspect "${project}_data_internal" --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: data network is not internal'; exit 1; }
docker network inspect "${project}_lab_internal" --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: lab network is not internal'; exit 1; }
docker network inspect "${project}_validator_internal" --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: validator network is not internal'; exit 1; }
$compose exec -T aether-gateway wget -qO- http://aether-api:8080/healthz >/dev/null || { echo 'FAIL: gateway cannot reach the API health check'; exit 1; }
echo 'PASS: only the gateway is host-published; VM ports are private; application and lab networks are isolated.'
