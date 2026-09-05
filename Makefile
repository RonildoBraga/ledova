# Ledova local-development commands.
# Production deployment and mainnet operations are intentionally out of scope.

NPM ?= npm
PYTHON ?= python3

.PHONY: help install install-backend init-local check-local-env build generate-tokens check check-comments test \
	dev-up dev-down dev-logs contracts-compile contracts-test contracts-deploy-local \
	contracts-deploy-testnet chain-test

# Hardhat account #0: a public development key that only ever holds local test ether.
CHAIN_TEST_PORT ?= 8545
CHAIN_TEST_RPC_URL ?= http://127.0.0.1:$(CHAIN_TEST_PORT)
CHAIN_TEST_OPERATOR_KEY ?= 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
# Django settings for the chain test; ledova_backend.settings.test_postgres (with the POSTGRES_* variables set)
# also runs the concurrency case, which needs a database that honours row locks.
CHAIN_TEST_SETTINGS ?= ledova_backend.settings.test

help:
	@echo "Ledova local development"
	@echo "  make install                  Install JavaScript dependencies"
	@echo "  make install-backend          Install backend development dependencies"
	@echo "  make init-local               Create owner-only local .env files"
	@echo "  make build                    Build dashboard, marketing, and contracts"
	@echo "  make generate-tokens          Regenerate the CSS design tokens from packages/shared"
	@echo "  make check                    Run static checks, including mobile and Django"
	@echo "  make check-comments           Fail on any comment or docstring in source"
	@echo "  make test                     Run workspace and contract tests"
	@echo "  make dev-up                   Start the local Docker Compose stack"
	@echo "  make dev-down                 Stop the local Docker Compose stack"
	@echo "  make dev-logs                 Follow local stack logs"
	@echo "  make contracts-deploy-local   Deploy example contracts to a local Hardhat node"
	@echo "  make contracts-deploy-testnet Deploy contracts to configured testnet only"
	@echo "  make chain-test               Start a Hardhat node, deploy the core contracts, run the real-chain backend test"

install:
	$(NPM) ci
	$(NPM) --prefix contracts ci
	$(NPM) --prefix marketing ci
	$(NPM) --prefix mobile ci

install-backend:
	$(PYTHON) -m pip install -r backend/requirements-dev.txt

init-local:
	$(PYTHON) scripts/init-local-env.py

check-local-env:
	$(PYTHON) scripts/init-local-env.py --check

build:
	$(NPM) run build -w dashboard
	$(NPM) --prefix marketing run build
	$(NPM) --prefix contracts run compile

generate-tokens:
	$(NPM) exec -- tsx packages/scripts/generate-css-tokens.mjs

check: check-comments install-backend
	$(NPM) run typecheck
	$(NPM) --prefix marketing run type-check
	$(NPM) --prefix mobile run type-check
	cd backend && SECRET_KEY="$$( $(PYTHON) -c 'import secrets; print(secrets.token_urlsafe(32))')" STORAGE_BACKEND=local $(PYTHON) manage.py check

check-comments:
	$(PYTHON) scripts/check-comments.py

test:
	$(NPM) test
	$(NPM) --prefix contracts test

dev-up: check-local-env
	docker compose up --build

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

contracts-compile:
	$(NPM) --prefix contracts run compile

contracts-test:
	$(NPM) --prefix contracts test

contracts-deploy-local:
	$(NPM) --prefix contracts run deploy:local:core

contracts-deploy-testnet:
	$(NPM) --prefix contracts run deploy:testnet

chain-test:
	@set -e; \
	$(NPM) --prefix contracts run compile; \
	( cd contracts && exec node_modules/.bin/hardhat node --port $(CHAIN_TEST_PORT) ) > .hardhat-node.log 2>&1 & \
	node_pid=$$!; \
	trap 'kill $$node_pid 2>/dev/null || true; wait $$node_pid 2>/dev/null || true' EXIT; \
	ready=0; \
	for attempt in $$(seq 1 60); do \
		curl -sf -X POST -H 'content-type: application/json' \
			--data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' $(CHAIN_TEST_RPC_URL) > /dev/null \
			&& { ready=1; break; }; \
		sleep 1; \
	done; \
	if [ "$$ready" != 1 ]; then \
		echo "Hardhat node did not answer on $(CHAIN_TEST_RPC_URL) within 60s; see .hardhat-node.log" >&2; exit 1; \
	fi; \
	$(NPM) --prefix contracts run deploy:local:core; \
	set -a; . ./.deployed-contracts.env; set +a; \
	cd backend && \
	CHAIN_TEST_RPC_URL=$(CHAIN_TEST_RPC_URL) BLOCKCHAIN_RPC_URL=$(CHAIN_TEST_RPC_URL) BLOCKCHAIN_CHAIN_ID=31337 \
	BLOCKCHAIN_OPERATOR_KEY=$(CHAIN_TEST_OPERATOR_KEY) SECRET_KEY=chain-test STORAGE_BACKEND=local \
	$(PYTHON) manage.py test tokens.tests.test_chain_integration --settings=$(CHAIN_TEST_SETTINGS) --noinput

.DEFAULT_GOAL := help
