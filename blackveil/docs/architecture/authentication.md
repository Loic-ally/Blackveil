# Authentication authority

`aether-auth` runs the Go binary in auth mode. Nginx forwards only
`/api/auth/` credential operations to it. Registration creates an ordinary
operator, a tenant and the initial equipment history in one transaction. Login
checks bcrypt credentials; sessions use random tokens with only their SHA-256
digests stored in PostgreSQL. Logout deletes the session record.

For every protected request, the API forwards only the session cookie to
`GET http://aether-auth:8080/internal/session`. The authority returns the user,
tenant and current database role. The API does not cache this decision, follows
no redirects and uses a three-second request deadline. Revoked sessions return
401; authority failures, malformed responses and unknown roles return 503.
The private session route is not forwarded by the gateway.

Auth joins the private app and data networks. It has no VM volume, lab network
membership or published ports. This is a process and network boundary; both
services still share the database account. Separate least-privilege database
roles and migration ownership remain required before final hardening.

Verification: Go authority-contract tests cover rejection and identity
propagation; `scripts/smoke.py` exercises registration, login, logout and tenant
isolation through the gateway. `scripts/vm-verify.py` checks the terminal role
gate through the same authority. `scripts/check-network.sh` includes auth in
its port-publication and player-network exclusions.
