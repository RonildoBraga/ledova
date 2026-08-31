PYTHON ?= python3

.PHONY: help install check lint test run worker docker-build require-env

help:
	@echo "Ledova backend"
	@echo "  make install       Install development dependencies"
	@echo "  make check         Run Django's configuration checks"
	@echo "  make lint          Check formatting and lint"
	@echo "  make test          Run credential-free Django unit tests"
	@echo "  make run           Start the local Django server using .env"
	@echo "  make worker        Start the local background worker using .env"
	@echo "  make docker-build  Build the local backend image"

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

check:
	SECRET_KEY="$$( $(PYTHON) -c 'import secrets; print(secrets.token_urlsafe(32))')" STORAGE_BACKEND=local $(PYTHON) manage.py check

lint:
	$(PYTHON) -m black --check --config pyproject.toml .
	$(PYTHON) -m isort --check-only --settings-path pyproject.toml .
	$(PYTHON) -m flake8 .

require-env:
	@test -f .env || { echo "Copy .env.example to .env and fill required values first."; exit 1; }

test:
	$(PYTHON) manage.py test --settings=ledova_backend.settings.test

run: require-env
	@set -a; . ./.env; set +a; exec $(PYTHON) manage.py runserver

worker: require-env
	@set -a; . ./.env; set +a; exec $(PYTHON) manage.py procrastinate worker

docker-build:
	docker build -t ledova-backend .

.DEFAULT_GOAL := help
