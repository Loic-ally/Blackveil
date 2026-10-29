#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

compose='docker compose --env-file .env -f compose.yaml'
$compose config --quiet

for service in aether-web aether-api aether-worker aether-telemetry aether-db aether-cache aether-bus; do
  id=$($compose ps -q "$service")
  [ -n "$id" ] || { echo "FAIL: $service is not running"; exit 1; }
  ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$id")
  [ "$ports" = 'null' ] || [ "$ports" = '{}' ] || { echo "FAIL: $service has a host-published port: $ports"; exit 1; }
done

gateway=$($compose ps -q aether-gateway)
[ -n "$gateway" ] || { echo 'FAIL: gateway is not running'; exit 1; }
gateway_ports=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$gateway")
python3 - "$gateway_ports" <<'PY'
import json, sys
bindings=json.loads(sys.argv[1] or "null") or {}
assert set(bindings) == {"443/tcp"}, f"gateway published unexpected host ports: {bindings}"
assert all(item["HostPort"] == "443" for item in bindings["443/tcp"]), bindings
PY

gateway_networks=$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$gateway")
case "$gateway_networks" in *blackveil_data_internal*) echo 'FAIL: gateway is attached to the data network'; exit 1;; esac
for service in aether-web aether-api aether-worker aether-telemetry aether-db aether-cache aether-bus; do
  id=$($compose ps -q "$service")
  networks=$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$id")
  case "$networks" in *blackveil_edge*) echo "FAIL: $service is attached to the player network"; exit 1;; esac
done

docker network inspect blackveil_app_internal --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: app network is not internal'; exit 1; }
docker network inspect blackveil_data_internal --format '{{.Internal}}' | grep -qx true || { echo 'FAIL: data network is not internal'; exit 1; }
$compose exec -T aether-gateway wget -qO- http://aether-api:8080/healthz >/dev/null || { echo 'FAIL: gateway cannot reach the API health check'; exit 1; }
echo 'PASS: only the gateway is host-published; private services have no published ports; internal networks are isolated.'
