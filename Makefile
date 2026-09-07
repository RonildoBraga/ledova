# Ledova local-development commands.
# Production deployment and mainnet operations are intentionally out of scope.

NPM ?= npm
PYTHON ?= python3

.PHONY: help install install-backend install-node-if-missing init-local check-local-env build generate-tokens check check-comments check-layers \
	check-logging check-schema-responses check-test-shadowing test-gates audit test \
	dev-up dev-down dev-logs contracts-compile contracts-test contracts-deploy-local \
	contracts-deploy-testnet chain-test smoke lint check-type-check

# CHAIN_TEST_PORT is the single knob for the local chain: it moves the Hardhat node, the backend's
# BLOCKCHAIN_RPC_URL and, through LOCALHOST_RPC_URL, the `localhost` network in contracts/hardhat.config.ts
# that `deploy:local:core` connects to. Two worktrees can therefore run `make chain-test` at once on
# different ports. The default stays 8545, which is what a bare `npx hardhat node` uses.
CHAIN_TEST_PORT ?= 8545
CHAIN_TEST_RPC_URL ?= http://127.0.0.1:$(CHAIN_TEST_PORT)
# Hardhat account #0: a public development key that only ever holds local test ether.
CHAIN_TEST_OPERATOR_KEY ?= 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
# Django settings for the chain test; ledova_backend.settings.test_postgres (with the POSTGRES_* variables set)
# also runs the concurrency case, which needs a database that honours row locks.
CHAIN_TEST_SETTINGS ?= ledova_backend.settings.test

# `make smoke` installs the Chromium that Playwright drives. On a developer machine the system
# libraries are already there; a bare CI image is not, so CI passes PLAYWRIGHT_BROWSER_DEPS=--with-deps
# and takes the sudo apt-get install that flag performs. Left empty, the target needs no root.
PLAYWRIGHT_BROWSER_DEPS ?=

help:
	@echo "Ledova local development"
	@echo "  make install                  Install JavaScript dependencies"
	@echo "  make install-backend          Install backend development dependencies"
	@echo "  make init-local               Create owner-only local .env files"
	@echo "  make build                    Build dashboard, marketing, and contracts"
	@echo "  make generate-tokens          Regenerate the CSS design tokens from packages/shared"
	@echo "  make check                    Run static checks, including mobile and Django"
	@echo "  make lint                     Run ESLint and solhint across every workspace"
	@echo "  make check-comments           Fail on any comment or docstring in source"
	@echo "  make check-layers             Fail on a new backend layer violation"
	@echo "  make check-type-check         Fail when a type-check script would examine no files"
	@echo "  make check-logging            Fail on a log line that can carry a credential or an email"
	@echo "  make check-schema-responses   Fail on a view whose response the schema does not know"
	@echo "  make check-test-shadowing     Fail on a test helper that shadows a TestCase method"
	@echo "  make check-error-bodies       Fail on an API error body built from an exception's text"
	@echo "  make test-gates               Run the unit tests of the gate scripts"
	@echo "  make audit                    Fail on a new production dependency advisory"
	@echo "  make test                     Run workspace, mobile, and contract tests"
	@echo "  make smoke                    Run the dashboard smoke tests against the built bundle"
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

# Each workspace resolves from its own node_modules. mobile's type-check reads
# expo/tsconfig.base, so without mobile's own install tsc fails before it reads a
# line of project code, which looks like a real type error and is not.
install-node-if-missing:
	@test -d node_modules || $(NPM) ci
	@test -d marketing/node_modules || $(NPM) --prefix marketing ci
	@test -d mobile/node_modules || $(NPM) --prefix mobile ci

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

check: check-comments check-layers check-logging check-error-bodies check-type-check check-schema-responses check-test-shadowing install-backend install-node-if-missing
	$(NPM) run typecheck
	$(NPM) --prefix mobile run check:resolution
	cd backend && SECRET_KEY="$$( $(PYTHON) -c 'import secrets; print(secrets.token_urlsafe(32))')" STORAGE_BACKEND=local $(PYTHON) manage.py check

lint:
	$(NPM) run lint
	$(NPM) --prefix marketing run lint
	$(NPM) --prefix mobile run lint
	$(NPM) --prefix contracts run lint

check-comments:
	$(PYTHON) scripts/check-comments.py

check-type-check:
	$(PYTHON) scripts/check-type-check.py

check-layers:
	$(PYTHON) scripts/check-layers.py

check-schema-responses:
	$(PYTHON) scripts/check-schema-responses.py
check-error-bodies:
	$(PYTHON) scripts/check-error-bodies.py

check-test-shadowing:
	$(PYTHON) scripts/check-test-shadowing.py

check-logging:
	$(PYTHON) scripts/check-logging.py

test-gates:
	$(PYTHON) -m unittest discover --start-directory scripts/tests --top-level-directory scripts/tests

audit:
	$(NPM) audit --omit=dev --audit-level=low
	$(NPM) --prefix marketing audit --omit=dev --audit-level=low
	$(NPM) --prefix contracts audit --omit=dev --audit-level=low
	$(NPM) --prefix mobile audit --omit=dev --audit-level=critical
	$(PYTHON) -m pip_audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1845

test:
	$(NPM) test
	$(NPM) --prefix mobile test
	$(NPM) --prefix contracts test

smoke:
	$(NPM) exec -- playwright install $(PLAYWRIGHT_BROWSER_DEPS) chromium
	$(NPM) run test:smoke -w dashboard

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
	LOCALHOST_RPC_URL=$(CHAIN_TEST_RPC_URL) $(NPM) --prefix contracts run deploy:local:core

contracts-deploy-testnet:
	$(NPM) --prefix contracts run deploy:testnet

chain-test:
	@set -e; \
	$(PYTHON) scripts/check-port-free.py $(CHAIN_TEST_PORT); \
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
	LOCALHOST_RPC_URL=$(CHAIN_TEST_RPC_URL) $(NPM) --prefix contracts run deploy:local:core; \
	set -a; . ./.deployed-contracts.env; set +a; \
	cd backend && \
	CHAIN_TEST_RPC_URL=$(CHAIN_TEST_RPC_URL) BLOCKCHAIN_RPC_URL=$(CHAIN_TEST_RPC_URL) BLOCKCHAIN_CHAIN_ID=31337 \
	BLOCKCHAIN_OPERATOR_KEY=$(CHAIN_TEST_OPERATOR_KEY) SECRET_KEY=chain-test STORAGE_BACKEND=local \
	$(PYTHON) manage.py test tokens.tests.test_chain_integration offerings.tests.test_chain_allotment \
	--settings=$(CHAIN_TEST_SETTINGS) --noinput

.DEFAULT_GOAL := help
