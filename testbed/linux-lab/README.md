# MetSec Linux lab

A HackTheBox-style target in a container: a vulnerable web app on a Linux host
with a full path from the web to **root**. INTENTIONALLY VULNERABLE — run only
on a host you control, bound to loopback.

## The intended path

1. **Web RCE** — `/ping?host=` has a command-injection sink.
2. **Foothold** — the agent gets command execution as the low-priv `webuser`.
3. **Privesc** — `webuser` may run `/usr/bin/find` as root with NOPASSWD
   (`sudo -l`). GTFOBins: `sudo find . -exec /bin/sh \; -quit` → **root**.
4. **Proof** — read `/root/root.txt` (`FLAG{metsec_reached_root}`), readable only by root.

## Run

```bash
./run.sh                      # builds + serves on http://127.0.0.1:5001
```

Then point MetSec at it (scope must list 127.0.0.1, mode dev or prod):

```bash
metsec assess http://127.0.0.1:5001/ --scope scope.yaml --active --exploit --out report/
```

Expect: web command-injection → foothold as `webuser` → `privesc_scan` surfaces the
`sudo find` candidate → escalation → `uid=0` and the root flag, captured as findings.
