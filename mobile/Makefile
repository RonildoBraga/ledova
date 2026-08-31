.PHONY: help install sync-packages start ios android typecheck lint doctor

help:
	@echo "Ledova mobile app (local development only)"
	@echo "  make install        Install dependencies"
	@echo "  make sync-packages  Build local shared packages"
	@echo "  make start          Start Expo"
	@echo "  make ios            Run the iOS development build"
	@echo "  make android        Run the Android development build"
	@echo "  make typecheck      Check TypeScript"
	@echo "  make lint           Check source lint"

install:
	npm ci

sync-packages:
	cd .. && npm run build:packages

start: sync-packages
	npm start

ios: sync-packages
	npm run ios

android: sync-packages
	npm run android

typecheck:
	npm run type-check

lint:
	npm run lint

doctor:
	npx expo-doctor

.DEFAULT_GOAL := help
