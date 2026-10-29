# Citadel — multi-stage pentest box

A harder, chained target for Watson. INTENTIONALLY VULNERABLE — run only on a host
you control, bound to loopback. Themed on current real-world techniques (SSTI RCE,
cf. Foreman CVE-2026-12544; the whole chain must be walked in order).

## The intended path

1. **Recon** — `robots.txt` discloses `/admin/report` and `/preview`; old jQuery; SSRF on `/preview`.
2. **Auth bypass** — SQL injection in `/login` (`admin'-- `) → authenticated **admin** session.
3. **RCE** — `/admin/report?name=` is Jinja2 **SSTI**, reachable *only* with the admin session
   → remote code execution → foothold as low-priv **`appuser`**.
4. **Privesc** — enumerate: `appuser` may run `tar` as root with NOPASSWD. GTFOBins:
   `sudo tar -cf /dev/null /dev/null --checkpoint=1 --checkpoint-action=exec=/bin/sh` → **root**.
   (Alternate: SUID `base64` reads root-only files without a shell.)
5. **Proof** — `/root/root.txt` = `FLAG{citadel_ssti_to_root_2026}`; loot `/opt/app/.env`.

Each stage gates the next: no SSTI without the admin session, no admin without the SQLi.

## Run

```bash
./run.sh        # builds + serves on http://127.0.0.1:5002
```

Then point Watson at it (scope lists 127.0.0.1, exploitation on):

```bash
watson scan --web http://127.0.0.1:5002/ --scope scope.yaml --exploit --budget 40
```
