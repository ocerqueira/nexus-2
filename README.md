# Nexus

API agnóstica para geração de relatórios e alertas consultando múltiplos bancos de dados. O Nexus expõe relatórios e alertas cadastrados no filesystem como endpoints REST, prontos para consumo por ferramentas de automação como N8N.

## Funcionalidades

- **Catálogo agnóstico**: Relatórios e alertas são criados como pastas no filesystem — sem SQL, sem migration, sem mexer no core
- **Multi-banco**: Consulta PostgreSQL, Firebird e MySQL simultaneamente com credenciais criptografadas (Fernet)
- **Múltiplos formatos**: JSON (API), HTML (e-mail/web) e PDF (download)
- **Notificações**: WhatsApp (Evolution API) e e-mail com templates Jinja2 por canal
- **Agendamentos**: Execução recorrente com frequência diária/semanal/mensal, múltiplos horários, dias úteis
- **Orquestração de alertas**: Cooldown, destinatários dinâmicos e fixos, múltiplos canais, deduplicação por fingerprint
- **Interface admin**: Painel web (Tailwind + HTMX) para gerenciar conexões, usuários, agendamentos e permissões
- **Autenticação**: API Key obrigatória, middleware HTTP
- **Sincronização AD**: Importa usuários do Active Directory via LDAP

## Stack

| Componente | Tecnologia |
|---|---|
| Linguagem | Python 3.14 |
| Framework | FastAPI + Uvicorn |
| Banco interno | PostgreSQL (Docker) |
| SQL | SQLAlchemy 2.0 (executor, sem ORM) |
| Templates | Jinja2 |
| PDF | WeasyPrint |
| Criptografia | Fernet (AES-128) |
| Frontend admin | Tailwind CSS + HTMX + Jinja2 |
| Gerenciador de pacotes | UV |

## Início rápido

```bash
# 1. Subir banco
docker compose up -d

# 2. Instalar dependências
uv sync

# 3. Configurar .env
cp .env.example .env
# Edite DATABASE_URL e gere CHAVE_CRIPTOGRAFIA:
# uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. Executar
uv run uvicorn main:app --reload --port 8000
```

Acesse:
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Admin: http://localhost:8000/admin
- Health check: http://localhost:8000/saude

## Estrutura

```
nexus-2/
├── main.py                  # FastAPI + lifespan + routers
├── config.py                # Pydantic Settings (.env)
├── docker-compose.yml       # PostgreSQL
├── Dockerfile               # Container da API
├── pyproject.toml           # Dependências
├── banco/                   # Migrations SQL idempotentes
├── app/
│   ├── bd.py                # Engine SQLAlchemy
│   ├── core/                # Criptografia, conexões, sync, orquestrador, renderizadores
│   ├── rotas/               # Endpoints REST + Admin HTML
│   ├── relatorios/          # Catálogo de relatórios (pastas com config.json + SQL + processador)
│   ├── alertas/             # Catálogo de alertas (pastas com config.json + SQL + processador + mensagens)
│   └── templates/           # Templates Jinja2 do admin
├── testes/                  # Testes automatizados
└── docs/                    # Documentação completa (Diátaxis)
```

## Documentação

A documentação completa está em [`docs/index.md`](docs/index.md) e segue o framework **Diátaxis**:

- [Tutoriais](docs/tutoriais/index.md) — Aprenda fazendo
- [Guias de instrução](docs/guias-de-instrucao/index.md) — Resolva problemas específicos
- [Referência](docs/referencia/index.md) — Detalhes técnicos de cada componente
- [Explicação](docs/explicacao/index.md) — Entenda as decisões de design

## Licença

Proprietário — uso interno.
