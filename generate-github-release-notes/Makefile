# Makefile for generate-github-release-notes action

.PHONY: help test test-unit test-integration test-docker build clean lint install-deps check-deps

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install-deps: ## Install dependencies using uv
	@echo "Installing dependencies with uv..."
	@command -v uv >/dev/null 2>&1 || { echo "uv not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	uv sync --frozen --extra dev

check-deps: ## Check if dependencies are installed
	@command -v uv >/dev/null 2>&1 || { echo "❌ uv not installed. Run 'make install-deps' first"; exit 1; }
	@echo "✅ Dependencies check passed"

test: check-deps ## Run all tests
	@echo "🧪 Running all tests..."
	uv run python tests/run_tests.py

test-unit: check-deps ## Run unit tests only
	@echo "🔬 Running unit tests..."
	uv run python -m pytest tests/test_simple.py -v

test-integration: check-deps ## Run integration tests
	@echo "🔗 Running integration tests..."
	uv run python -m pytest tests/test_generate_release_notes.py -v

test-docker: ## Test Docker build and basic functionality
	@echo "🐳 Testing Docker build..."
	docker build -t test-generate-release-notes .
	@echo "✅ Docker build successful"
	@echo "🧪 Testing Docker image..."
	@echo '{"types":[{"type":"feat","section":"Features"}]}' > test-config.json
	@docker run --rm \
		-e GITHUB_TOKEN="fake-token" \
		-e GITHUB_REPOSITORY="test/repo" \
		-v "$(PWD):/workspace" \
		-w /workspace \
		test-generate-release-notes \
		"nonexistent" "nonexistent" "docker-test.md" "test-config.json" || true
	@rm -f test-config.json docker-test.md
	@echo "✅ Docker test completed"

build: ## Build Docker image
	@echo "🏗️  Building Docker image..."
	docker build -t generate-github-release-notes .
	@echo "✅ Docker image built successfully"

lint: check-deps ## Run linting on Python files
	@echo "🔍 Running linting..."
	uv run python -m flake8 generate-github-release-notes.py tests/ \
		--max-line-length=100 \
		--ignore=E501,W503,E203 \
		--exclude=__pycache__,*.pyc

format: check-deps ## Format Python code
	@echo "🎨 Formatting Python code..."
	@command -v black >/dev/null 2>&1 || uv add --dev black
	uv run black generate-github-release-notes.py tests/ --line-length=100

validate-action: ## Validate action.yaml and Dockerfile
	@echo "✅ Validating action metadata..."
	@test -f action.yaml || { echo "❌ action.yaml not found"; exit 1; }
	@test -f Dockerfile || { echo "❌ Dockerfile not found"; exit 1; }
	@python3 -c "import yaml; yaml.safe_load(open('action.yaml'))" || { echo "❌ Invalid action.yaml"; exit 1; }
	@echo "✅ Action metadata is valid"

clean: ## Clean up temporary files
	@echo "🧹 Cleaning up..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "test-*.md" -delete
	@find . -type f -name "*.md.tmp" -delete
	@find . -type f -name "docker-test.md" -delete
	@find . -type f -name "test-config.json" -delete
	@echo "✅ Cleanup completed"

ci-test: ## Run tests as they would run in CI
	@echo "🚀 Running CI-style tests..."
	@$(MAKE) install-deps
	@$(MAKE) validate-action
	@$(MAKE) test-unit
	@$(MAKE) test-integration
	@$(MAKE) test-docker
	@$(MAKE) lint
	@echo "🎉 All CI tests passed!"

dev-setup: ## Set up development environment
	@echo "🛠️  Setting up development environment..."
	@command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; }
	@$(MAKE) install-deps
	@echo "✅ Development environment ready!"
