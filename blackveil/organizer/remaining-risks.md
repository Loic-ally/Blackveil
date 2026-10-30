# BLACK VEIL — remaining risks

Private organizer material. Review date: 2026-10-30. Current executed results
are in [full-chain-validation.md](full-chain-validation.md).

- Patched anti-replay is process-local. Restart forgets signatures still inside
  the 120-second window. Production operator cannot restart the agent, but an
  organizer restart can reopen that window. Persistent replay storage is absent.
- The patched retained capture is intentionally stale. Its refusal alone does
  not prove numeric binding: independent organizer-signed protocol fixtures
  test binding, timestamp freshness and duplicate rejection.
- Reset and VM reset preserve the worker key in .env. Rotate it explicitly and
  reprovision guests if key rotation is required.
- Disposable agent restart testing uses a test-only sudo rule restricted to one
  unit. This differs from production permissions; boot-ID preservation proves
  it is a service restart rather than a guest reboot.
- Reset tests are local; no successful CI reset run, architecture matrix, KVM
  execution or blind playtest has been reviewed.
- Base images use tags rather than digests. No image vulnerability scan or
  kernel/QEMU escape testing was performed. Debian image latest changes fail
  the committed checksum check and require an intentional metadata update.
- Local self-signed TLS and manual hosts-file setup remain deployment constraints.
- Stages 09–15 are implemented and player-reachable. Full-chain verification
  (Stages 01–15) passes on the running stack with the rebuilt guest VMs. A
  full clean-room verification (disposable Compose project) has not yet reached
  exit 0 with the current codebase; the previous archived runs used an older
  commit. Run `python3 scripts/validate-clean-room.py` to record a new run.
- Binary updates to guest services require a VM reset (`make vm-reset`) before
  the updated binary becomes active in the running guest, because cloud-init
  only provisions once per instance-id. The render-cloud-init.py instance-id
  is now tied to a binary hash so new builds auto-provision on clean deployments;
  existing running volumes still require an explicit reset.
- No blind playtest or final difficulty scoring has been completed.

A test script's presence is not a successful test result. Failures or incomplete
runs must stay visible in the validation report.
