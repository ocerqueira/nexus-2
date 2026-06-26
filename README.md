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

## Ambientes

| Arquivo | Ambiente | No git? |
|---|---|---|
| `.env.exemplo` | Template (sem valores) | ✅ sim |
| `.env` | Produção | ❌ nunca |
| `.env.local` | Dev local | ❌ nunca |

Copie o template para o ambiente desejado e preencha os valores:

```bash
cp .env.exemplo .env        # produção
cp .env.exemplo .env.local  # dev local
```

Gere as chaves necessárias:

```bash
# API Key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Chave de criptografia Fernet (ATENÇÃO: não troque em produção após registrar conexões)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Dev local

Sobe PostgreSQL isolado + API em containers Docker. Não toca no banco de produção.

```bash
make dev-build    # primeira vez ou após mudar código/dependências
make dev          # subir sem rebuild
make dev-logs     # acompanhar logs da API em tempo real
make dev-down     # parar tudo
make dev-db       # abrir psql no banco de dev
```

API disponível em `http://localhost:8099` — Swagger em `http://localhost:8099/docs`.

O banco de dev roda na porta **5433** (prod usa 5432) — impossível confundir por acidente.

## Produção

Rodar no servidor. Usa `.env` com as credenciais reais.

```bash
make prod-build   # deploy com rebuild da imagem
make prod         # subir sem rebuild
make prod-logs    # acompanhar logs
make prod-down    # parar
```

Ver containers de ambos os ambientes:

```bash
make status
```

## Estrutura

```
nexus-2/
├── .env.exemplo             # Template de variáveis (commitar — sem valores reais)
├── .env                     # Produção (não commitar)
├── .env.local               # Dev local (não commitar)
├── Makefile                 # Comandos: make dev-build, make prod-logs, etc.
├── docker-compose.yml       # Produção: só a API, usa .env
├── docker-compose.dev.yml   # Dev: postgres + postgres-metas + API, usa .env.local
├── Dockerfile               # Imagem da API
├── main.py                  # FastAPI + lifespan + routers
├── pyproject.toml           # Dependências (UV)
├── banco/                   # Migrations SQL idempotentes
├── app/
│   ├── bd.py                # Engine SQLAlchemy
│   ├── core/                # Orquestrador, sincronizador, criptografia, tokens, renderizadores
│   ├── rotas/               # Endpoints REST
│   ├── relatorios/          # Catálogo: cada pasta = 1 relatório (config.json + processador.py)
│   ├── alertas/             # Catálogo: cada pasta = 1 alerta  (config.json + processador.py)
│   └── templates/           # Templates Jinja2 (PDF + admin)
└── docs/                    # Documentação (Diátaxis)
```

### Adicionar relatório ou alerta

Crie uma pasta em `app/relatorios/<nome>/` com `config.json` e `processador.py`. No próximo restart, o sincronizador registra no banco automaticamente — sem mexer em nenhum outro arquivo.

## Documentação

A documentação completa está em [`docs/index.md`](docs/index.md) e segue o framework **Diátaxis**:

- [Tutoriais](docs/tutoriais/index.md) — Aprenda fazendo
- [Guias de instrução](docs/guias-de-instrucao/index.md) — Resolva problemas específicos
- [Referência](docs/referencia/index.md) — Detalhes técnicos de cada componente
- [Explicação](docs/explicacao/index.md) — Entenda as decisões de design

## Licença

Proprietário — uso interno.
