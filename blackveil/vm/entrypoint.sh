#!/bin/sh
set -eu

state=/var/lib/aether-vm
mkdir -p "$state"
chgrp 10001 "$state"
chmod 0710 "$state"
umask 077

case "${AETHER_AGENT_MODE:-challenge}" in
  challenge|patched) mode=${AETHER_AGENT_MODE:-challenge} ;;
  *) echo 'AETHER_AGENT_MODE must be challenge or patched' >&2; exit 2 ;;
esac

key=${AETHER_AGENT_KEY:-}
case "$key" in
  ''|*[!0-9a-fA-F]*) echo 'AETHER_AGENT_KEY must be hexadecimal' >&2; exit 2 ;;
esac
[ "${#key}" -ge 64 ] || { echo 'AETHER_AGENT_KEY must contain at least 32 bytes' >&2; exit 2; }

if [ ! -s "$state/operator_ed25519" ]; then
  ssh-keygen -q -t ed25519 -N '' -C 'blackveil-linux-operator' -f "$state/operator_ed25519"
fi
chmod 0640 "$state/operator_ed25519"
chmod 0644 "$state/operator_ed25519.pub"

if [ ! -s "$state/overlay.qcow2" ]; then
  qemu-img create -q -f qcow2 -F qcow2 -b /opt/aether/debian-base.qcow2 "$state/overlay.qcow2" 12G
fi

python3 /opt/aether/render-cloud-init.py \
  --agent /opt/aether/aether-agent \
  --public-key "$state/operator_ed25519.pub" \
  --key "$key" \
  --mode "$mode" \
  --output "$state"
cloud-localds -f iso "$state/seed.iso" "$state/user-data" "$state/meta-data"

run_qemu() {
  "$@" &
  qemu_pid=$!
  trap 'kill "$qemu_pid" 2>/dev/null || true; wait "$qemu_pid" || true' INT TERM
  cp "$state/operator_ed25519" /tmp/bootstrap-key
  chmod 0600 /tmp/bootstrap-key
  while kill -0 "$qemu_pid" 2>/dev/null; do
    if ! curl --fail --silent --max-time 2 http://127.0.0.1:18080/healthz >/dev/null; then
      sleep 2
      continue
    fi
    if ! ssh -i /tmp/bootstrap-key -p 2222 -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null operator@127.0.0.1 'cloud-init status --wait >/dev/null' </dev/null >/dev/null 2>&1; then
      sleep 5
      continue
    fi
    host_key=$(ssh-keyscan -T 2 -p 2222 -t ed25519 127.0.0.1 2>/dev/null | awk '$2 == "ssh-ed25519" {print $2 " " $3; exit}')
    if [ -n "$host_key" ]; then
      printf '%s\n' "$host_key" > "$state/guest_host_ed25519.pub"
      chmod 0644 "$state/guest_host_ed25519.pub"
      touch /tmp/vm-ready
      break
    fi
    sleep 1
  done
  wait "$qemu_pid"
}

if [ "$(uname -m)" = aarch64 ]; then
  run_qemu qemu-system-aarch64 \
    -machine virt -accel tcg,thread=multi -cpu max -smp 1 -m 768 \
    -bios /usr/share/AAVMF/AAVMF_CODE.fd \
    -drive if=none,file="$state/overlay.qcow2",format=qcow2,id=hd0 \
    -device virtio-blk-pci,drive=hd0 \
    -drive if=none,file="$state/seed.iso",format=raw,readonly=on,id=seed0 \
    -device virtio-blk-pci,drive=seed0 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22,hostfwd=tcp::18080-:8080 \
    -device virtio-net-device,netdev=net0 \
    -display none -monitor none -serial stdio -no-reboot
  exit $?
fi

run_qemu qemu-system-x86_64 \
  -machine q35,accel=tcg,thread=multi -cpu max -smp 1 -m 768 \
  -bios /usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=none,file="$state/overlay.qcow2",format=qcow2,id=hd0 \
  -device virtio-blk-pci,drive=hd0 \
  -drive if=none,file="$state/seed.iso",format=raw,readonly=on,id=seed0 \
  -device virtio-blk-pci,drive=seed0 \
  -netdev user,id=net0,hostfwd=tcp::2222-:22,hostfwd=tcp::18080-:8080 \
  -device virtio-net-pci,netdev=net0 \
  -display none -monitor none -serial stdio -no-reboot
