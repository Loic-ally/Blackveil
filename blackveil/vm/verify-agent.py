import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

KEY = bytes.fromhex(os.environ["AETHER_AGENT_KEY"])
PRINCIPAL = "svc:aether-reporting"
TENANT_A = "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"


def signature(job, tenant, legacy=None):
    fields = [job, PRINCIPAL, tenant]
    if legacy is not None:
        fields.append(str(legacy))
    message = "\n".join(fields).encode()
    return hmac.new(KEY, message, hashlib.sha256).hexdigest()


def post(host, envelope):
    request = urllib.request.Request(
        f"http://{host}:18080/v1/legacy/archive",
        data=json.dumps(envelope).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def envelope(legacy, patched=False):
    job = "verify-job-2026-10"
    result = {
        "job_id": job,
        "principal": PRINCIPAL,
        "tenant_uuid": TENANT_A,
        "legacy_tenant_no": legacy,
    }
    result["signature"] = signature(job, TENANT_A, legacy if patched else None)
    return result


health = urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=5)
assert health.status == 200

status, own = post("127.0.0.1", envelope(4101))
assert status == 200 and own["resolved_legacy_tenant_no"] == 4101, (status, own)

challenge_tampered = envelope(4101)
challenge_tampered["legacy_tenant_no"] = 4102
status, leaked = post("127.0.0.1", challenge_tampered)
assert status == 200 and leaked["resolved_legacy_tenant_no"] == 4102, (status, leaked)
assert "harbor-process" in leaked["records"]["record"]

status, canonical = post("aether-linux-vm-patched", envelope(4101, patched=True))
assert status == 200 and canonical["resolved_legacy_tenant_no"] == 4101, (status, canonical)

patched_tampered = envelope(4101, patched=True)
patched_tampered["legacy_tenant_no"] = 4102
status, rejected = post("aether-linux-vm-patched", patched_tampered)
assert status == 403, (status, rejected)
print("PASS: Debian VM agent boots; challenge accepts a mismatched unsigned legacy ID; patched agent rejects it.")
