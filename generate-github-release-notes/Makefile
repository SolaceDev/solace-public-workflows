# Makefile for generate-github-release-notes action

.PHONY: help test test-python test-docker build clean lint

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

test: ## Run all tests
	@echo "Running all tests..."
	python3 tests/run_tests.py

test-python: ## Run Python unit tests only
	@echo "Running Python unit tests..."
	cd tests && python3 -m unittest test_simple.py -v


build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t generate-github-release-notes .


lint: ## Run linting on Python files
	@echo "Running linting..."
	@command -v flake8 >/dev/null 2>&1 || { echo "flake8 not installed. Install with: pip install flake8"; exit 1; }
	flake8 generate-github-release-notes.py tests/ --max-line-length=100 --ignore=E501,W503

clean: ## Clean up temporary files
	@echo "Cleaning up..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@rm -f test-*.md
	@rm -f *.md.tmp

install-dev: ## Install development dependencies
	@echo "Installing development dependencies..."
	pip3 install flake8 PyYAML
