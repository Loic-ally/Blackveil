# Blackveil

Intentionally vulnerable practice targets, split out of [Watson](https://github.com/Loic-ally/Watson).
For local, isolated testing only.

## `blackveil/`

Multi-stage CTF environment. See [`blackveil/README.md`](blackveil/README.md).

## Practice labs (`testbed/`)

Run `./testbed/<box>/run.sh`:

- **linux-lab** — web command injection → `sudo find` → root (introductory).
- **citadel** — SQL-injection auth bypass → admin SSTI RCE → `sudo tar` → root (multi-stage).
- **obscura** — no known CVE: LFI → source review → custom auth bypass → command injection
  → unsafe-YAML deserialization privilege escalation → root.
- **vulnapp.py** — `python testbed/vulnapp.py` serves on http://127.0.0.1:5000.
