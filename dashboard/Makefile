.PHONY: help install dev build preview test typecheck lint

help:
	@echo "Ledova dashboard (local development only)"
	@echo "  make install    Install the root workspace"
	@echo "  make dev        Start Vite locally"
	@echo "  make build      Build shared packages and dashboard"
	@echo "  make test       Run dashboard tests"
	@echo "  make typecheck  Check TypeScript"
	@echo "  make lint       Check source lint"

install:
	cd .. && npm ci

dev:
	npm run dev

build:
	cd .. && npm run build:packages
	npm run build

preview:
	npm run preview

test:
	npm test

typecheck:
	npm run type-check

lint:
	npm run lint

.DEFAULT_GOAL := help
