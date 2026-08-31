# Ledova local-development commands.
# Production deployment and mainnet operations are intentionally out of scope.

NPM ?= npm
PYTHON ?= python3

.PHONY: help install install-backend init-local check-local-env build check test \
	dev-up dev-down dev-logs contracts-compile contracts-test contracts-deploy-local \
	contracts-deploy-testnet

help:
	@echo "Ledova local development"
	@echo "  make install                  Install JavaScript dependencies"
	@echo "  make install-backend          Install backend development dependencies"
	@echo "  make init-local               Create owner-only local .env files"
	@echo "  make build                    Build packages, dashboard, marketing, and contracts"
	@echo "  make check                    Run static checks, including mobile and Django"
	@echo "  make test                     Run workspace and contract tests"
	@echo "  make dev-up                   Start the local Docker Compose stack"
	@echo "  make dev-down                 Stop the local Docker Compose stack"
	@echo "  make dev-logs                 Follow local stack logs"
	@echo "  make contracts-deploy-local   Deploy example contracts to a local Hardhat node"
	@echo "  make contracts-deploy-testnet Deploy contracts to configured testnet only"

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
	$(NPM) run build:packages
	$(NPM) run build -w dashboard
	$(NPM) --prefix marketing run build
	$(NPM) --prefix contracts run compile

check: install-backend
	$(NPM) run typecheck
	$(NPM) --prefix marketing run type-check
	$(NPM) --prefix mobile run type-check
	cd backend && SECRET_KEY="$$( $(PYTHON) -c 'import secrets; print(secrets.token_urlsafe(32))')" STORAGE_BACKEND=local $(PYTHON) manage.py check

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

.DEFAULT_GOAL := help
