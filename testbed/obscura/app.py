"""Obscura DocHub — INSANE-level pentest box. INTENTIONALLY VULNERABLE.

No known CVE here — the flaws are custom logic mistakes you must find by reading
the source (which an arbitrary-file-read exposes). Chain:
  1. arbitrary file read on /download?file= (no sanitization) → read this source
  2. source review reveals is_admin(): a cookie whose first '.'-part is 'admin'
     is trusted WITHOUT any signature → forge session=admin.x
  3. /admin/convert concatenates user input into a shell command → RCE → foothold

Runs as 'www'. Loopback only.
"""
import base64
import hashlib
import hmac
import os
import subprocess

from flask import Flask, Response, request

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
SECRET = b"obscura-signing-key-do-not-share"   # signs normal user tokens


def make_token(user: str) -> str:
    sig = hmac.new(SECRET, user.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(user.encode()).decode() + "." + sig


def is_admin(cookie: str) -> bool:
    if not cookie:
        return False
    if cookie.split(".", 1)[0] == "admin":   # BUG: 'admin.' prefix trusted, no signature
        return True
    try:                                      # normal path: verify a signed user (none are admin)
        user_b64, sig = cookie.rsplit(".", 1)
        user = base64.urlsafe_b64decode(user_b64).decode()
        good = hmac.new(SECRET, user.encode(), hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(sig, good) and user == "superadmin"
    except Exception:
        return False


@app.route("/")
def home():
    return ('<!doctype html><title>Obscura DocHub</title><h1>Obscura DocHub</h1>'
            '<p>Internal document hub.</p>'
            '<p>Sample: <a href="/download?file=welcome.txt">welcome.txt</a></p>')


@app.route("/download")
def download():
    f = request.args.get("file", "welcome.txt")
    try:
        with open(os.path.join(BASE, f), "rb") as fh:   # no path sanitization → arbitrary read
            return Response(fh.read(), mimetype="text/plain")
    except OSError as e:
        return Response(str(e), status=404)


@app.route("/admin/convert")
def convert():
    if not is_admin(request.cookies.get("session", "")):
        return Response("admin only", status=403)
    opts = request.args.get("opts", "-version")
    return Response(subprocess.getoutput("convert " + opts), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
