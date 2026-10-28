.PHONY: up down test build
up:
	docker compose up --build -d

down:
	docker compose down

test:
	cd backend && .venv/bin/pytest -q

build:
	cd frontend && npm run build
