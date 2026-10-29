COMPOSE = docker compose --env-file .env -f compose.yaml

.PHONY: setup up down reset logs check integration network-check

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
