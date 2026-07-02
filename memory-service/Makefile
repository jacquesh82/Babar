# Raccourcis de développement memory-service.
.PHONY: help up down logs test lint fmt migrate worker

help:  ## Liste les cibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up:  ## Démarre la stack (api + postgres/pgvector + redis + worker)
	docker compose up --build -d

down:  ## Arrête la stack
	docker compose down

logs:  ## Suit les logs
	docker compose logs -f

test:  ## Lance les tests
	pytest -q

lint:  ## Vérifie lint + format (sans modifier)
	ruff check . && ruff format --check .

fmt:  ## Applique lint --fix + format
	ruff check --fix . && ruff format .

migrate:  ## Applique les migrations SQL sur le postgres de la stack
	@for f in storage/migrations/*.sql; do \
		echo "Applying $$f"; \
		docker compose exec -T postgres psql -U $${POSTGRES_USER:-memory} -d $${POSTGRES_DB:-memory} -v ON_ERROR_STOP=1 < $$f; \
	done

worker:  ## Exécute un cycle de consolidation unique (local)
	python -m consolidation.worker --once
