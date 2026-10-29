COMPOSE = docker compose --env-file .env -f compose.yaml

.PHONY: setup up down reset logs check integration network-check vm-up vm-down vm-reset vm-shell vm-verify

setup:
	@test -f .env || cp .env.example .env
	@./scripts/setup-local.sh

up:
	@test -f .env || (echo 'Run make setup first.' && exit 1)
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

reset:
	@./scripts/reset.sh

logs:
	$(COMPOSE) logs -f --tail=100

check:
	cd api && GOPATH=/tmp/blackveil-gopath GOMODCACHE=/tmp/blackveil-gomod GOCACHE=/tmp/blackveil-go-cache go test ./...
	cd web && npm ci && npm run build
	$(COMPOSE) config --quiet

integration: up
	python3 scripts/smoke.py

network-check:
	@./scripts/check-network.sh

vm-up:
	@test -f .env || (echo 'Run make setup first.' && exit 1)
	docker compose --env-file .env -f compose.yaml --profile vm up -d --build --wait aether-linux-vm

vm-down:
	docker compose --env-file .env -f compose.yaml --profile vm stop aether-linux-vm

vm-reset:
	@./scripts/vm-reset.sh

vm-shell:
	docker compose --env-file .env -f compose.yaml --profile vm exec aether-linux-vm sh -c 'umask 077; cp /var/lib/aether-vm/operator_ed25519 /tmp/operator_ed25519; exec ssh -i /tmp/operator_ed25519 -o UserKnownHostsFile=/var/lib/aether-vm/known_hosts -o StrictHostKeyChecking=accept-new -p 2222 operator@127.0.0.1'

vm-verify:
	python3 scripts/vm-verify.py
