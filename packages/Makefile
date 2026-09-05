NPM ?= npm
ROOT := ..

.PHONY: help install lint test typecheck

help:
	@echo "Ledova shared package (@ledova/shared, consumed from source)"
	@echo "  make install    Install the root workspace"
	@echo "  make lint       Lint the shared package"
	@echo "  make test       Run the shared package tests"
	@echo "  make typecheck  Type-check the shared package"

install:
	$(NPM) --prefix $(ROOT) ci

lint:
	$(NPM) --prefix $(ROOT) run lint -w @ledova/shared

test:
	$(NPM) --prefix $(ROOT) run test -w @ledova/shared

typecheck:
	$(NPM) --prefix $(ROOT) run typecheck -w @ledova/shared
