# Explicação — Arquitetura geral

## Visão em camadas

O Nexus é organizado em camadas com responsabilidades claras. O diagrama abaixo mostra o fluxo de uma requisição até a resposta.

```
┌─────────────────────────────────────────────────┐
│                    N8N / Cliente                 │
│         (consome a API, decide quando chamar)    │
└──────────────────────┬──────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────┐
│              Rotas (app/rotas/)                  │
│  - Validação de entrada (Pydantic)               │
│  - Roteamento para processadores                 │
│  - Escolha de formato de saída                   │
└──────┬──────────────────────────────┬───────────┘
       │                              │
       ▼                              ▼
┌──────────────┐              ┌──────────────────┐
│ Orquestrador │              │   Renderizador   │
│ de Alertas   │              │   (HTML, PDF)    │
│ (cooldown,   │              └──────────────────┘
│  dest.,      │
│  histórico)  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│             Processadores                         │
│  (app/relatorios/*/ e app/alertas/*/)             │
│  - validar()                                      │
│  - buscar_dados() / verificar()                   │
└──────┬───────────────────────────────┬───────────┘
       │                               │
       ▼                               ▼
┌──────────────┐              ┌──────────────────┐
│ Carregador   │              │  Gerenciador de   │
│ de SQL       │              │  Conexões         │
│ (-- name:)   │              │  (pool, cache,    │
└──────────────┘              │   criptografia)   │
                              └──────┬───────────┘
                                     │
                                     ▼
                              ┌──────────────────┐
                              │  Bancos externos  │
                              │  (PG, FB, MySQL)  │
                              └──────────────────┘
```

## Fluxo de inicialização

1. **FastAPI lifespan**: `ciclo_vida()` em `main.py`
2. **`garantir_estrutura_banco()`**: executa `banco/*.sql` em ordem alfabética (idempotente via `IF NOT EXISTS`)
3. **`sincronizar_filesystem_com_banco()`**: lê `app/relatorios/*/config.json` e `app/alertas/*/config.json`, insere/atualiza/remove nas tabelas `relatorios` e `alertas`
4. **Pronto**: API disponível em `localhost:8000`

A sincronização AD (`app/core/sincronizador_ad.py`) é executada sob demanda via `POST /ad/sincronizar` — não no startup.

## Fluxo de um relatório

```
POST /relatorios/{nome}/solicitar?formato=pdf
  │
  ├─ 1. Valida formato e parâmetros
  ├─ 2. Instancia processador → validar()
  ├─ 3. processador.buscar_dados() → dict
  │     └─ carregar_query() + gerenciador_conexoes.executar()
  │        ou engine.connect() (banco interno)
  ├─ 4. Escolhe formato:
  │     ├─ json → retorna payload
  │     ├─ html → renderizar_html(template + dados)
  │     └─ pdf  → gerar_pdf(html)
  └─ 5. Retorna resposta HTTP
```

## Fluxo de um alerta

```
POST /alertas/{nome}/verificar?forcar=false
  │
  ├─ 1. Orquestrador busca alerta no banco
  ├─ 2. Verifica cooldown (a menos que forcar=true)
  ├─ 3. Valida parâmetros
  ├─ 4. processador.verificar() → dict com encontrou_dados
  ├─ 5. Se encontrou_dados=false → retorna sem_dados
  ├─ 6. detectar_capacidades_alerta() (quais templates existem)
  ├─ 7. renderizar_mensagens_consolidadas() (Jinja2)
  ├─ 8. renderizar_mensagens_individuais() (uma por linha)
  ├─ 9. Buscar destinatários do banco
  ├─ 10. Consolidar canais
  ├─ 11. Atualizar ultimo_disparo
  ├─ 12. Registrar histórico
  └─ 13. Retorna payload completo
```

## Módulos principais

| Módulo | Responsabilidade |
|--------|-----------------|
| `app/bd.py` | Engine SQLAlchemy do banco interno (pool_size=5) |
| `app/core/criptografia.py` | Criptografia/descriptografia Fernet |
| `app/core/gerenciador_conexoes.py` | Pool de conexões externas, cache, descriptografia on-the-fly |
| `app/core/carregador_sql.py` | Parser de arquivos `.sql` com marcadores `-- name:` |
| `app/core/sincronizador.py` | Sincroniza filesystem ↔ tabelas `relatorios` e `alertas` |
| `app/core/sincronizador_ad.py` | Sincronização de usuários com Active Directory via LDAP |
| `app/core/inicializador.py` | Executa arquivos SQL de estrutura do banco |
| `app/core/autenticacao.py` | Middleware de autenticação API Key |
| `app/core/orquestrador_alertas.py` | Pipeline completo de verificação de alerta |
| `app/core/orquestrador_relatorios.py` | Pipeline de geração + entrega de relatórios |
| `app/core/entregas_comum.py` | Helpers compartilhados: modo teste, janela de silêncio, validação de contatos (WhatsApp/email), inserção de entregas |
| `app/core/processadores.py` | Descoberta automática de processadores + verificação de contrato no startup |
| `app/core/resolvedor_parametros.py` | Resolução de tokens dinâmicos ({{hoje}}, {{mes_anterior_inicio}}, ...) |
| `app/core/renderizador.py` | Renderização HTML e geração PDF de relatórios |
| `app/core/renderizador_mensagens.py` | Renderização de mensagens de alerta (Jinja2 por canal) |
| `app/core/calculadora_agenda.py` | Cálculo de próximas execuções de agendamentos |
| `app/rotas/` | Endpoints FastAPI (saude, relatórios, alertas, admin, chatbot, AD, usuários, conexões, permissões, agendamentos) |

## Decisões de design

### Sincronização filesystem → banco

O banco é fonte de verdade para metadados (título, status, etc), mas a **origem** é o filesystem. Isso permite:

- Versionar relatórios e alertas no Git
- Criar novos sem SQL — basta criar pastas e arquivos
- Detectar remoções automaticamente (status `removido` no banco)

### Orquestrador como fachada

O `orquestrador_alertas.py` é o ponto central que junta filesystem + banco + renderização + destinatários. Os processadores de alerta são mantidos simples (`validar` + `verificar`). Isso torna o sistema agnóstico: para criar um alerta novo, basta adicionar uma pasta — o orquestrador não precisa ser modificado.

### Templates opcionais

O `detectar_capacidades_alerta()` inspeciona quais arquivos de template existem na pasta `mensagens/` do alerta. Se um arquivo não existe, aquela capacidade simplesmente não aparece no payload. Isso permite que alertas simples tenham só WhatsApp, enquanto alertas complexos tenham todos os canais.

### Cache em dois níveis no gerenciador de conexões

O `GerenciadorConexoes` mantém cache de dados (evita consultar `conexoes_bd` toda vez) e cache de engines SQLAlchemy (evita recriar pools). O cache pode ser limpo seletivamente ou totalmente via `limpar_cache()`.
