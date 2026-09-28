# Convenience targets. None of these are required -- everything here can be run by hand
# following README.md -- but `make setup && make test && make run` is the fastest path from
# a clean checkout to a working app, and having it scripted removes any ambiguity about what
# "run the documented steps" means.

VENV := venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

.PHONY: setup test seed run docker-up docker-down clean

setup:
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example."; else echo ".env already exists, leaving it alone."; fi

test:
	$(PYTEST) tests/ -v

seed:
	$(PY) scripts/seed_db.py

run:
	$(PY) run.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf $(VENV) instance epi.db .pytest_cache
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
