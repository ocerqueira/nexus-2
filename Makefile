# =============================================================================
# Nexus — Comandos por ambiente
# =============================================================================
# Uso: make <comando>
#
# Dev local:
#   make dev          sobe postgres + postgres-metas + api (build se necessário)
#   make dev-build    força rebuild da imagem
#   make dev-down     para tudo
#   make dev-logs     acompanha logs da API
#   make dev-db       abre psql no banco de dev
#
# Produção (rodar no servidor):
#   make prod         sobe api (usa .env)
#   make prod-build   força rebuild
#   make prod-logs    acompanha logs
#   make prod-down    para
# =============================================================================

COMPOSE_DEV  = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.yml

# ─── Dev local ───────────────────────────────────────────────────────────────

dev:
	$(COMPOSE_DEV) up -d

dev-build:
	$(COMPOSE_DEV) up -d --build

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f nexus

dev-db:
	docker exec -it nexus-postgres-dev psql -U nexus_admin -d nexus

# ─── Produção ────────────────────────────────────────────────────────────────

prod:
	$(COMPOSE_PROD) up -d

prod-build:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f nexus

# ─── Utilitários ─────────────────────────────────────────────────────────────

status:
	@echo "=== DEV ===" && $(COMPOSE_DEV) ps 2>/dev/null || true
	@echo "=== PROD ===" && $(COMPOSE_PROD) ps 2>/dev/null || true

.PHONY: dev dev-build dev-down dev-logs dev-db prod prod-build prod-down prod-logs status
