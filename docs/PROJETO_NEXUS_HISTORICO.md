# Projeto Nexus — Histórico e Decisões

> Documento de referência do que foi construído, como, e por quê.
> Atualizado até: 23/06/2026

---

## 1. Visão Geral

**Nexus** é um sistema FastAPI agnóstico que gera **relatórios** (PDF/HTML/JSON) e **alertas** (JSON com mensagens prontas) consultando múltiplos bancos. O N8N consome os payloads e distribui via WhatsApp (Evolution API) e Email.

**Localização:** `P:\python\ativos\nexus`
**Plataforma:** Windows + Python 3.14 + UV

### Cenário real de uso

- ERP em Firebird 5.0+ (6 unidades isoladas, uma multiempresa com `cod_empresa` 1 e 2)
- DW em PostgreSQL 17+
- Intranet em PostgreSQL 17+
- Vendedores e assistentes têm telefones cadastrados no ERP (Firebird)
- Gestor, logística e outros vêm de tabela `usuarios` (preparada para AD futuro)

---

## 2. Stack Técnica

| Componente | Versão / Lib |
|---|---|
| Linguagem | Python 3.14 |
| Package manager | UV |
| Linter | Ruff |
| API framework | FastAPI + Uvicorn |
| Banco interno | PostgreSQL 18-alpine (Docker) |
| Executor SQL | SQLAlchemy 2.0 (apenas executor, **sem ORM, sem Alembic**) |
| Driver Postgres | `psycopg[binary]` |
| Driver Firebird | `sqlalchemy-firebird` |
| Templates | Jinja2 |
| PDF | WeasyPrint |
| Criptografia | `cryptography` (Fernet) |
| Configuração | `pydantic-settings` |

---

## 3. Decisões Arquiteturais Chave

1. **Filesystem é fonte da verdade.** Relatórios/alertas vivem em pastas (`app/relatorios/X/`, `app/alertas/X/`). Banco mantém catálogo sincronizado.
2. **Sincronização híbrida.** Auto no startup + endpoint manual `POST /sincronizar`.
3. **Sem ORM, sem Alembic.** Apenas SQLAlchemy como executor. SQL puro em arquivos versionados.
4. **Identificação por nome OU ID** nos endpoints.
5. **Marcadores `-- name: query_nome`** em arquivos `.sql` (parser próprio).
6. **Senhas com Fernet.** Criptografadas no banco, chave única no `.env` (`CHAVE_CRIPTOGRAFIA`). Backup manual via 1Password/Bitwarden + arquivo `RECUPERACAO.md`.
7. **Multi-banco abstraído** pelo `GerenciadorConexoes` — cache de engines, descriptografia em memória, URLs por tipo.
8. **Queries explícitas por cenário** (sem `:param IS NULL OR ...`).
9. **Templates de mensagem por canal.** Convenção do filesystem dita o comportamento:
   - `whatsapp_consolidado.txt`, `email_consolidado_html.html`, `email_consolidado_assunto.txt`
   - `whatsapp_individual.txt`, `email_individual_html.html`, `email_individual_assunto.txt`
10. **3 tipos de destinatários:**
    - **Dinâmicos** — vêm do SQL (ex: vendedor + assistente do ERP)
    - **Fixos** — cadastrados no banco em `alertas_condicoes.destinatarios`
    - **Avulsos** — passados via parâmetro na chamada
11. **Cooldown automático** via `alertas_condicoes.cooldown_minutos` + `ultimo_disparo`.
12. **N8N consulta o Nexus** (não o contrário). Cron a cada minuto chamará `/agendamentos/proximas-execucoes`.
13. **Idempotência total.** SQL usa `IF NOT EXISTS` + `DROP TRIGGER IF EXISTS`. Subir 2x = mesmo estado.
14. **Português (PT-BR) em snake_case** para nomes de variáveis, funções, módulos.

---

## 4. Estrutura de Pastas

```
nexus/
├── docker-compose.yml          (Postgres 18-alpine)
├── pyproject.toml
├── main.py                     (FastAPI + lifespan + routers)
├── config.py                   (Pydantic Settings)
├── .env                        (DATABASE_URL, CHAVE_CRIPTOGRAFIA)
├── RECUPERACAO.md              (procedimento de recuperação da chave)
├── banco/
│   └── 001_estrutura_inicial.sql
├── app/
│   ├── bd.py                   (engine SQLAlchemy)
│   ├── core/
│   │   ├── inicializador.py    (executa SQLs da pasta banco/)
│   │   ├── criptografia.py     (Fernet)
│   │   ├── gerenciador_conexoes.py
│   │   ├── carregador_sql.py   (parser de queries com -- name:)
│   │   ├── renderizador.py     (relatórios: HTML/PDF)
│   │   ├── sincronizador.py    (filesystem ↔ banco)
│   │   ├── renderizador_mensagens.py  (templates de mensagens)
│   │   ├── orquestrador_alertas.py    (fluxo completo do alerta)
│   │   └── templates/
│   │       └── base.html       (template base de relatórios)
│   ├── rotas/
│   │   ├── saude.py            (GET /saude, POST /sincronizar)
│   │   ├── relatorios.py       (POST /relatorios/{nome}/solicitar)
│   │   └── alertas.py          (POST /alertas/{nome}/verificar)
│   ├── relatorios/
│   │   └── teste_conexoes/
│   │       ├── config.json
│   │       ├── consultas.sql
│   │       ├── processador.py
│   │       └── template.html
│   └── alertas/
│       └── conexoes_inativas/
│           ├── config.json
│           ├── consultas.sql
│           ├── processador.py
│           └── mensagens/
│               ├── whatsapp_consolidado.txt
│               ├── email_consolidado_assunto.txt
│               └── email_consolidado_html.html
```

---

## 5. Modelagem do Banco — 11 Tabelas

Arquivo: `banco/001_estrutura_inicial.sql` (idempotente).

| Tabela | Função |
|---|---|
| `usuarios` | Cadastro de pessoas (preparado para AD) |
| `conexoes_bd` | Catálogo de bancos externos com senha criptografada |
| `grupos_conexoes` | Agrupamento de conexões (multiempresa) |
| `grupos_conexoes_itens` | Itens dos grupos |
| `relatorios` | Catálogo sincronizado de relatórios |
| `alertas` | Catálogo sincronizado de alertas |
| `alertas_condicoes` | Condições de disparo + destinatários + canais + cooldown |
| `permissoes` | Controle de acesso (hard delete) |
| `chatbot_sessoes` | Sessões do chatbot WhatsApp |
| `historico` | Auditoria de toda execução |
| `agendamentos` | Execuções automáticas (tabela única com JSONB) |

**Convenções:**
- IDs: `SERIAL`
- Timestamps: `TIMESTAMPTZ`
- Estruturas flexíveis: `JSONB`
- Soft delete via `status` (`ativo`/`inativo`/`removido`) em `relatorios`/`alertas`
- Soft delete via `ativo` boolean nas demais
- Hard delete apenas em `permissoes`
- Trigger genérico `atualizar_coluna_atualizado_em()` aplicado em 7 tabelas

---

## 6. Funcionalidades Implementadas

### 6.1 Infraestrutura

- Docker Compose com Postgres 18-alpine (porta externa `55432`)
- UV init + Python 3.14 pinned
- Pydantic Settings com `.env`
- Engine SQLAlchemy com pool (`echo=False`)
- Logging estruturado

### 6.2 Banco

- 10 tabelas criadas via SQL idempotente
- Triggers de `atualizado_em` automáticos
- Comentários documentando colunas
- `CHECK` constraints validando enums

### 6.3 Multi-banco + dependências

- `GerenciadorConexoes` funcionando com **Postgres E Firebird 5.0.4** testados em produção
- Cache de engines + descriptografia em memória
- Conexões cadastradas:
  - `nexus_proprio` (postgres) — auto-referencial para testes
  - `erp_teste` (firebird local) — cópia de produção do ERP

### 6.4 Relatórios

- Sistema completo com 3 formatos (JSON / HTML / PDF)
- Relatório `teste_conexoes` funcionando
- Templates Jinja2 com `base.html` + `extends`
- WeasyPrint gerando PDF (com warnings GTK inofensivos no Windows)

### 6.5 Alertas + Orquestrador

- Estrutura `app/alertas/conexoes_inativas/` completa
- Templates de mensagem renderizando (`whatsapp_consolidado` + `email_consolidado_html` + `email_consolidado_assunto`)
- Orquestrador completo:
  - Busca alerta no banco
  - Verifica cooldown
  - Executa via processador
  - Renderiza templates
  - Atualiza `ultimo_disparo`
  - Registra histórico
- Detecção automática de capacidades via filesystem (tem arquivo `*_individual.*`? Tem arquivo `*_consolidado.*`?)
- Cooldown funcionando + parâmetro `forcar=true` para ignorar

### 6.6 Sincronização

- `sincronizar_filesystem_com_banco()` popula `relatorios` e `alertas` no startup
- Detecta: pastas novas (insere), modificadas (atualiza), sumidas (marca `removido`), reaparecidas (reativa)
- Endpoint manual `POST /sincronizar`

### 6.7 Pydantic Models para Body

- `RequisicaoAlerta` e `RequisicaoRelatorio` com `parametros: dict = Field(default_factory=dict)` para resolver bug de JSON vazio no Swagger.

### 6.8 Administração

### 6.8 Dados de Teste Cadastrados

- Usuário admin (`id=1`, `identificador='admin_nexus'`, `whatsapp='5511999999999'`)
- Condição em `alertas_condicoes` para o alerta `conexoes_inativas`

---

## 7. Endpoints da API (Hoje)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/saude` | Health check (API + banco) |
| POST | `/sincronizar` | Força sincronização manual |
| GET | `/relatorios` | Lista relatórios disponíveis |
| POST | `/relatorios/{nome}/solicitar` | Gera relatório (`?formato=json\|html\|pdf`) |
| GET | `/alertas` | Lista alertas disponíveis |
| POST | `/alertas/{nome}/verificar` | Verifica e retorna payload (`?forcar=true`) |

---

## 8. Fluxos Validados End-to-End

### 8.1 Relatório
```
POST /relatorios/teste_conexoes/solicitar?formato=pdf
  → Router (relatorios.py)
  → Processador (valida + escolhe query + executa)
  → Gerenciador (conecta no Postgres, executa SQL)
  → Renderizador (Jinja2 + WeasyPrint)
  → PDF baixado
```

### 8.2 Alerta
```
POST /alertas/conexoes_inativas/verificar?forcar=true
  → Router (alertas.py)
  → Orquestrador
     ├─ busca alerta no banco
     ├─ verifica cooldown
     ├─ chama processador.verificar()
     ├─ renderiza mensagens (whatsapp + email)
     ├─ busca destinatários fixos
     ├─ atualiza ultimo_disparo
     └─ registra histórico
  → Payload completo com mensagens prontas
```

---

## 9. Observações Técnicas Importantes

- Nomenclatura **PT-BR snake_case**
- Nome da instância FastAPI no `main.py`: `app` (não `aplicacao`)
- Comando para rodar: `uv run uvicorn main:app --reload`
- Comando para acessar Postgres: `docker exec -it nexus-postgres psql -U nexus_admin -d nexus`
- Senha Postgres do Nexus: `nexus_dev_2024`
- Chave Fernet guardada no `.env` E em gerenciador de senhas pessoal
- WeasyPrint funciona no Windows com warnings UWP inofensivos (GLib-GIO-WARNING podem ser ignorados)
- Driver Firebird usa `fbclient.dll` no PATH local

---

## 10. Pontos Não Triviais Que Foram Resolvidos

| Problema | Solução |
|---|---|
| Senhas em texto puro no banco | Fernet + chave no `.env` + backup no gerenciador de senhas |
| Multi-banco sem complicar código | `GerenciadorConexoes` abstrai tudo, URL por tipo |
| SQL "encavalando" parâmetros opcionais | Queries explícitas por cenário (sem `IS NULL OR`) |
| Como N8N saber qual mensagem mandar | Nexus já retorna mensagens prontas por canal |
| Engessar destinatários por alerta | 3 tipos: dinâmicos (SQL), fixos (banco), avulsos (parâmetro) |
| Spam de alertas repetidos | Cooldown automático com `ultimo_disparo` + `cooldown_minutos` |
| Cache de conexão antigo após mudança | `gerenciador_conexoes.limpar_cache()` + reload do uvicorn |
| Pasta removida = perde histórico? | Não. Status muda para `removido`, dados preservados |
| Bug JSON vazio no Swagger | Pydantic Model `RequisicaoX` com `Field(default_factory=dict)` |
| `categoria` em alertas (não existe) | Sincronizador separado por tabela (funções diferentes) |