"""Acme Notes — a small demo web app.

INTENTIONALLY VULNERABLE. This is a practice target for MetSec. Do not deploy it
anywhere reachable from the internet. Run it only on a host you control:

    pip install flask requests
    python testbed/vulnapp.py           # serves on http://127.0.0.1:5000

Seeds a throwaway SQLite db with a few users on startup.
"""
import base64
import os
import sqlite3
import subprocess

import requests
from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template_string, request)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"
DB = os.path.join(os.path.dirname(__file__), "vulnapp.db")


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def seed():
    c = db()
    c.executescript(
        "DROP TABLE IF EXISTS users;"
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT,"
        " email TEXT, role TEXT);"
        "INSERT INTO users (username,password,email,role) VALUES"
        " ('alice','p@ssw0rd','alice@acme.test','user'),"
        " ('bob','letmein','bob@acme.test','user'),"
        " ('admin','S3cretAdmin!','admin@acme.test','admin');")
    c.commit()
    c.close()


def token(username):
    return base64.b64encode(username.encode()).decode()


HOME = """<!doctype html><html><head><title>Acme Notes</title>
<script src="https://code.jquery.com/jquery-1.7.2.min.js"></script></head>
<body><h1>Acme Notes</h1>
<ul>
<li><a href="/search?q=notes">Search</a></li>
<li><a href="/login">Login</a></li>
<li><a href="/profile?id=1">My profile</a></li>
<li><a href="/greet?name=guest">Greeting</a></li>
<li><a href="/tools">Network tools</a></li>
<li><a href="/go?next=/">Home</a></li>
</ul></body></html>"""


@app.route("/")
def home():
    return HOME


@app.route("/search")
def search():  # reflects user input into HTML without escaping
    q = request.args.get("q", "")
    return Response("<h1>Results for " + q + "</h1>", mimetype="text/html")


@app.route("/go")
def go():  # redirects to a user-supplied destination
    return redirect(request.args.get("next", "/"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        q = "SELECT * FROM users WHERE username='%s' AND password='%s'" % (u, p)
        try:
            row = db().execute(q).fetchone()
        except sqlite3.Error as e:
            return Response("query error: " + str(e), status=500)
        if row:
            resp = make_response(redirect("/admin-panel"))
            resp.set_cookie("session", token(row["username"]))
            return resp
        return Response("Invalid credentials", status=401)
    return Response('<form method="post"><input name="username">'
                    '<input name="password" type="password">'
                    '<button>Sign in</button></form>', mimetype="text/html")


@app.route("/profile")
def profile():  # returns any user's record by id, no authorization check
    uid = request.args.get("id", "1")
    row = db().execute("SELECT id,username,email,role FROM users WHERE id=?", (uid,)).fetchone()
    return jsonify(dict(row)) if row else (Response("not found", status=404))


@app.route("/greet")
def greet():  # renders a template built from user input
    name = request.args.get("name", "guest")
    return render_template_string("Hello " + name + "!")


@app.route("/tools")
def tools():
    return Response('<a href="/ping?host=127.0.0.1">ping</a> '
                    '<a href="/fetch?url=http://127.0.0.1:5000/">fetch</a>',
                    mimetype="text/html")


@app.route("/ping")
def ping():  # runs a shell command with a user-supplied argument
    host = request.args.get("host", "127.0.0.1")
    return Response(subprocess.getoutput("ping -c 1 " + host), mimetype="text/plain")


@app.route("/fetch")
def fetch():  # fetches a user-supplied URL server-side
    url = request.args.get("url", "")
    try:
        return Response(requests.get(url, timeout=3).text[:800], mimetype="text/plain")
    except requests.RequestException as e:
        return Response(str(e), status=502)


@app.route("/admin-panel")
def admin_panel():  # trusts an unsigned, guessable session cookie
    try:
        user = base64.b64decode(request.cookies.get("session", "")).decode()
    except (ValueError, UnicodeDecodeError):
        user = ""
    row = db().execute("SELECT role FROM users WHERE username=?", (user,)).fetchone()
    if row and row["role"] == "admin":
        users = [dict(r) for r in db().execute("SELECT id,username,email,role FROM users")]
        return jsonify({"panel": "admin", "users": users})
    return Response("forbidden", status=403)


@app.route("/.env")
def dotenv():
    return Response("SECRET_KEY=dev-secret-key-change-me\nDB_PASSWORD=admin123\n"
                    "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n", mimetype="text/plain")


@app.route("/.git/config")
def gitconfig():
    return Response('[remote "origin"]\n\turl = git@github.com:acme/acme-notes.git\n',
                    mimetype="text/plain")


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /admin-panel\nDisallow: /.env\n",
                    mimetype="text/plain")


if __name__ == "__main__":
    seed()
    app.run(host="127.0.0.1", port=5000, debug=True)
