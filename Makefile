.PHONY: setup test lint run up down frontend-setup frontend-check frontend-dev

PYTHON ?= python

setup:  ## Install dev tooling and Python module dependencies (backend, pipelines)
	$(PYTHON) -m pip install -r requirements-dev.txt -r backend/requirements.txt -r pipelines/requirements.txt
	pre-commit install

test:  ## Run all tests
	$(PYTHON) -m pytest

lint:  ## Static checks
	ruff check .

up:  ## Start local infrastructure (Qdrant)
	docker compose up -d

down:  ## Stop local infrastructure
	docker compose down

run:  ## Run the backend API locally with auto-reload
	$(PYTHON) -m uvicorn app.main:app --app-dir backend/src --reload --port 8000

frontend-setup:  ## Install frontend dependencies from the lockfile (Node.js 22, ADR 0004)
	cd frontend && npm ci

frontend-check:  ## Type check and build the frontend, as CI does
	cd frontend && npm run typecheck && npm run build

frontend-dev:  ## Run the frontend dev server on port 5173 (proxies /health and /chat to :8000)
	cd frontend && npm run dev
