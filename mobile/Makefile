.PHONY: help install start ios android typecheck lint doctor native-check

help:
	@echo "Ledova mobile app (local development only)"
	@echo "  make install        Install dependencies"
	@echo "  make start          Start Expo"
	@echo "  make ios            Run the iOS development build"
	@echo "  make android        Run the Android development build"
	@echo "  make typecheck      Check TypeScript"
	@echo "  make lint           Check source lint"
	@echo "  make native-check   Regenerate and check native Debug/Release policy"
	@echo "  Native build/probe procedure: ../docs/MOBILE.md"

install:
	npm ci

start:
	npm start

ios:
	npm run ios

android:
	npm run android

typecheck:
	npm run type-check

lint:
	npm run lint

doctor:
	npx expo-doctor

native-check:
	npm run native:prebuild
	npm run check:native

.DEFAULT_GOAL := help
