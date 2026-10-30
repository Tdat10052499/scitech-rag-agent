.PHONY: setup test lint run up up-qdrant down logs frontend-setup frontend-check frontend-dev

PYTHON ?= python

setup:  ## Install dev tooling and Python module dependencies (backend, agent, pipelines)
	$(PYTHON) -m pip install -r requirements-dev.txt -r backend/requirements.txt -r agent/requirements.txt -r pipelines/requirements.txt
	pre-commit install

test:  ## Run all tests
	$(PYTHON) -m pytest

lint:  ## Static checks
	ruff check .

up:  ## Build and start the whole stack: Qdrant, backend (:8000), frontend (:8080); needs .env
	docker compose up -d --build

up-qdrant:  ## Start Qdrant only (pipelines `load`, or the backend with `make run`)
	docker compose up -d qdrant

down:  ## Stop the stack (data in the qdrant_data volume and in data/ is kept)
	docker compose down

logs:  ## Follow the logs of the stack
	docker compose logs -f

run:  ## Run the backend API locally with auto-reload
	PYTHONPATH=agent/src $(PYTHON) -m uvicorn app.main:app --app-dir backend/src --reload --port 8000

frontend-setup:  ## Install frontend dependencies from the lockfile (Node.js 22, ADR 0004)
	cd frontend && npm ci

frontend-check:  ## Type check and build the frontend, as CI does
	cd frontend && npm run typecheck && npm run build

frontend-dev:  ## Run the frontend dev server on port 5173 (proxies /health and /chat to :8000)
	cd frontend && npm run dev
