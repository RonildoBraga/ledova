.PHONY: help install dev build preview typecheck lint

help:
	@echo "Ledova marketing site (local development only)"
	@echo "  make install    Install dependencies"
	@echo "  make dev        Start Vite locally"
	@echo "  make build      Build the site"
	@echo "  make typecheck  Check TypeScript"
	@echo "  make lint       Check source lint"

install:
	npm ci

dev:
	npm run dev

build:
	npm run build

preview:
	npm run preview

typecheck:
	npm run type-check

lint:
	npm run lint

.DEFAULT_GOAL := help
