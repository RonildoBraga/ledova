NPM ?= npm
ROOT := ..

.PHONY: help install build lint test typecheck validate clean \
	build-constants build-types build-utils build-services

help:
	@echo "Ledova shared packages"
	@echo "  make install    Install the root workspace"
	@echo "  make build      Build packages in dependency order"
	@echo "  make lint       Lint all shared packages"
	@echo "  make test       Run shared-package tests"
	@echo "  make typecheck  Type-check all shared packages"
	@echo "  make validate   Validate package metadata and entry points"

install:
	$(NPM) --prefix $(ROOT) ci

build:
	$(NPM) --prefix $(ROOT) run build:packages

lint:
	$(NPM) --prefix $(ROOT) run lint --workspaces --if-present

test:
	$(NPM) --prefix $(ROOT) run test --workspaces --if-present

typecheck:
	$(NPM) --prefix $(ROOT) run typecheck --workspaces --if-present

validate:
	$(NPM) --prefix $(ROOT)/packages run validate:packages

clean:
	$(NPM) --prefix $(ROOT) run clean --workspaces --if-present

build-constants:
	$(NPM) --prefix $(ROOT) run build -w @ledova/shared-constants

build-types: build-constants
	$(NPM) --prefix $(ROOT) run build -w @ledova/shared-types

build-utils: build-types
	$(NPM) --prefix $(ROOT) run build -w @ledova/shared-utils

build-services: build-utils
	$(NPM) --prefix $(ROOT) run build -w @ledova/shared-services
