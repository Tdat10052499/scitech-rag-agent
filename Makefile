.PHONY: setup test lint run up down

PYTHON ?= python

setup:  ## Install dev tooling and backend dependencies
	$(PYTHON) -m pip install -r requirements-dev.txt -r backend/requirements.txt
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
