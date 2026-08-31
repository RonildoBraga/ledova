.PHONY: help install compile test test-coverage deploy-testnet lint check clean

.DEFAULT_GOAL := help

BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

help: ## Show this help message
	@echo "$(BLUE)Ledova Contracts - Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ## Install dependencies
	npm install

compile: ## Compile smart contracts
	npm run compile

test: ## Run tests
	npm test

test-coverage: ## Run tests with coverage
	npm run test:coverage

deploy-testnet: ## Deploy all contracts to Base Sepolia
	npm run deploy:testnet

lint: ## Format code and run Solhint linter
	@echo "$(BLUE)Formatting code...$(NC)"
	npm run format
	@echo "$(GREEN)✓ Code formatting completed$(NC)"
	@echo "$(BLUE)Running Solhint linter...$(NC)"
	npm run lint
	@echo "$(GREEN)✓ Linting completed$(NC)"

check: ## Run all checks without auto-fix (for CI)
	@echo "$(BLUE)╔════════════════════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║                     Running All Code Quality Checks                       ║$(NC)"
	@echo "$(BLUE)╚════════════════════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(YELLOW)[1/2] Checking code formatting...$(NC)"
	@npm run format:check
	@echo "$(GREEN)✓ Format check passed$(NC)"
	@echo ""
	@echo "$(YELLOW)[2/2] Running Solhint...$(NC)"
	@npm run lint
	@echo "$(GREEN)✓ Linting passed$(NC)"
	@echo ""
	@echo "$(GREEN)╔════════════════════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(GREEN)║                    ✅ All Code Quality Checks Passed!                     ║$(NC)"
	@echo "$(GREEN)╚════════════════════════════════════════════════════════════════════════════╝$(NC)"

clean: ## Clean build artifacts
	npm run clean
