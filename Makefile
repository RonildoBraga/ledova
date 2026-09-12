# Ledova local-development commands.
# Production deployment and mainnet operations are intentionally out of scope.

NPM ?= npm
PYTHON ?= python3

# The API type drift gate reads a generated OpenAPI schema rather than generating one,
# so it needs no Django on the host. CI generates it in the Django job, where the
# database schema generation touches already exists, and writes it to this same path -
# two files naming one artefact differently is how `make check-api-types` comes to say
# no schema exists while CI has just written one.
SCHEMA ?= /tmp/ledova-schema.json
SCHEMA_ENVIRONMENT ?= /tmp/ledova-schema-environment.json
SCHEMA_COMPARISON ?= /tmp/ledova-schema-comparison.json
CLIENT_OPERATIONS_REPORT ?= /tmp/ledova-client-operations.json

.PHONY: help install install-backend install-node-if-missing init-local check-local-env build generate-tokens check check-comments check-layers \
	check-logging check-schema-responses check-test-shadowing check-docs check-api-types check-self-imports check-mobile-test-awaits test-gates audit test \
	dev-up dev-down dev-logs contracts-compile contracts-test contracts-deploy-local \
	contracts-deploy-testnet chain-test smoke lint check-type-check \
	install-schema-environment generate-api-schema check-api-schema update-api-schema check-client-operations

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
	@echo "  make check-self-imports       Check workspace package imports after installing Node dependencies"
	@echo "  make lint                     Run ESLint and solhint across every workspace"
	@echo "  make check-comments           Fail on any comment or docstring in source"
	@echo "  make check-layers             Fail on a new backend layer violation"
	@echo "  make check-type-check         Fail when a type-check script would examine no files"
	@echo "  make check-logging            Fail on a log line that can carry a credential or an email"
	@echo "  make check-schema-responses   Fail on a view whose response the schema does not know"
	@echo "  make check-test-shadowing     Fail on a test helper that shadows a TestCase method"
	@echo "  make check-docs               Fail when a document disagrees with the tree it describes"
	@echo "  make check-connection-binding  Fail on a transaction or cursor bound to the default connection"
	@echo "  make check-api-types          Fail on a shared type that requires a field the API never sends"
	@echo "  make install-schema-environment Install development dependencies with the schema toolchain constraints"
	@echo "  make generate-api-schema      Generate JSON from an already migrated isolated PostgreSQL database"
	@echo "  make check-api-schema         Generate and compare the complete committed OpenAPI snapshot"
	@echo "  make update-api-schema        Generate, check contracts and explicitly replace the snapshot"
	@echo "  make check-client-operations  Check shared, dashboard and mobile HTTP operations against the snapshot"
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

install-schema-environment:
	$(PYTHON) -m pip install -r backend/requirements-dev.txt -c backend/schema/requirements.txt

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

check: check-comments check-layers check-logging check-connection-binding check-error-bodies check-type-check check-schema-responses check-test-shadowing check-docs install-backend install-node-if-missing
	$(MAKE) check-self-imports
	$(NPM) run typecheck
	$(NPM) --prefix mobile run check:resolution
	$(MAKE) check-mobile-test-awaits
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
check-connection-binding:
	$(PYTHON) scripts/check-connection-binding.py

check-error-bodies:
	$(PYTHON) scripts/check-error-bodies.py

check-test-shadowing:
	$(PYTHON) scripts/check-test-shadowing.py

check-docs:
	$(PYTHON) scripts/check-docs.py
check-api-types:
	@test -f $(SCHEMA) || { \
	  echo "No schema at $(SCHEMA). Generate one first:"; \
	  echo "  make generate-api-schema SCHEMA=$(SCHEMA)"; \
	  echo "or pass SCHEMA=<path>. CI generates it in the Django job."; \
	  exit 1; }
	$(PYTHON) scripts/check-api-types.py --schema $(SCHEMA)

generate-api-schema:
	cd backend && $(PYTHON) manage.py export_api_schema --settings=ledova_backend.settings.test_postgres \
	  --file "$(abspath $(SCHEMA))" --report "$(abspath $(SCHEMA_ENVIRONMENT))"

check-api-schema: generate-api-schema
	$(PYTHON) scripts/check-api-schema.py --schema "$(SCHEMA)" --report "$(SCHEMA_COMPARISON)"

update-api-schema: generate-api-schema
	$(PYTHON) scripts/check-api-types.py --schema "$(SCHEMA)"
	node scripts/check-client-operations.mjs --schema "$(SCHEMA)" --report "$(CLIENT_OPERATIONS_REPORT)"
	$(PYTHON) scripts/check-api-schema.py --schema "$(SCHEMA)" --report "$(SCHEMA_COMPARISON)" --update

check-client-operations:
	node --test scripts/tests/check-client-operations.test.mjs
	node scripts/check-client-operations.mjs --report "$(CLIENT_OPERATIONS_REPORT)"

check-logging:
	$(PYTHON) scripts/check-logging.py

check-self-imports:
	node scripts/check-self-imports.mjs
	node --test scripts/tests/check-self-imports.test.mjs

check-mobile-test-awaits:
	node --test scripts/tests/check-mobile-test-awaits.test.mjs

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
	    wallets.tests.test_submission_chain \
	--settings=$(CHAIN_TEST_SETTINGS) --noinput

.DEFAULT_GOAL := help
