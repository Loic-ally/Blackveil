#!/usr/bin/env python3
"""Archive non-sensitive outcomes from disposable full-chain/reset verification."""
import datetime
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
now = datetime.datetime.now(datetime.timezone.utc)
run = ROOT / 'organizer/validation-runs' / now.strftime('%Y%m%dT%H%M%SZ')
run.mkdir(parents=True, exist_ok=False)
command = [sys.executable, 'scripts/verify-reset.py', *sys.argv[1:]]
summary = {
    'started_utc': now.isoformat(),
    'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
    'environment': platform.platform(),
    'configuration': 'isolated random Compose project, fresh secrets and named volumes; challenge and patched guests; build cache allowed',
    'command': command, 'exit_code': None, 'checks': [], 'status': 'running',
}

def save():
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (run / 'report.md').write_text('# Disposable validation run\n\n' +
        '\n'.join(f'- {key}: `{summary[key]}`' for key in
                  ('started_utc', 'commit', 'dirty', 'environment', 'configuration', 'command', 'exit_code', 'status')) +
        '\n\n## Verified outcomes\n\n' + '\n'.join('- ' + item for item in summary['checks']) +
        '\n\nOnly allowlisted outcome lines are archived. Raw output, cookies, receipts, proof bundles and flags are not archived. A failing exit code invalidates full acceptance.\n')

save()
print('Evidence directory:', run, flush=True)
proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in proc.stdout:
    # Do not persist arbitrary subprocess output: assertions can contain challenge secrets.
    if line.startswith(('PASS:', 'OK:', '== ')) and not re.search(r'BV\{|signature|receipt.*:', line, re.I):
        clean = line.strip()
        summary['checks'].append(clean)
        print(clean, flush=True)
        save()
    elif any(term in line for term in ('Error', 'error:', 'FAIL', 'failed', 'unhealthy', 'AssertionError')):
        print('Diagnostic:', re.sub(r'([a-fA-F0-9]{32,}|BV\{[^}]*\})', '[redacted]', line.strip())[:500], flush=True)
summary['exit_code'] = proc.wait()
summary['status'] = 'passed' if summary['exit_code'] == 0 else 'failed'
summary['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
save()
print('Validation exit:', summary['exit_code'], flush=True)
sys.exit(summary['exit_code'])
