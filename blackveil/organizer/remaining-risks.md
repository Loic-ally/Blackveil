# BLACK VEIL — remaining risks

Private organizer material. Review date: 2026-10-29. Current executed results
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
- Final evidence correlation, scoring and difficulty validation remain unfinished.
  Stages 09–15 are intentionally unimplemented.

A test script's presence is not a successful test result. Failures or incomplete
runs must stay visible in the validation report.
