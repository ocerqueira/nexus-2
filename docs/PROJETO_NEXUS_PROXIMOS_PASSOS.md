# Projeto Nexus — Próximos Passos

> O que falta implementar, em ordem de prioridade.
> Atualizado até: 23/06/2026

---

## ✅ CONCLUÍDO — Agendamentos

A implementação de agendamentos foi finalizada com sucesso.

### O que foi entregue

- **Tabela única** `agendamentos` com `horarios` e `canais` como JSONB
- **`calculadora_agenda.py`**: cálculo de próximo envio para frequências `diaria`, `semanal` e `mensal`, com suporte a dias úteis e timezone
- **Timezone**: coluna `timezone` em `agendamentos` ( padrão `America/Sao_Paulo`), cálculo com `pytz`/`zoneinfo`
- **Endpoints REST**: CRUD completo em `app/rotas/agendamentos.py`
  - `GET /agendamentos/proximas-execucoes` — endpoint de polling para N8N (tolerância de 60 min)
  - `POST /agendamentos/{id}/marcar-executado` — callback pós-envio
  - `POST /agendamentos` — criar com validação completa
  - `GET /agendamentos` — listar com filtros
  - `PATCH /agendamentos/{id}` — atualizar
  - `DELETE /agendamentos/{id}` — desativar (soft)
- **Interface admin**: gerenciamento completo via painel HTMX

---

## ✅ CONCLUÍDO — Infraestrutura e Segurança

- **Autenticação da API**: middleware `API_KEY` implementado em `app/core/autenticacao.py`. Endpoints públicos: `/saude` e `/admin`.
- **Containerização**: `Dockerfile` para FastAPI + `docker-compose.yml` com serviço `nexus-api`.
- **Permissões**: tabela `permissoes` com CRUD completo em `app/rotas/permissoes.py`. Endpoint `GET /permissoes/verificar` para N8N.
- **Interface Admin**: painel completo em `app/rotas/admin.py` (1092 linhas) — Tailwind + HTMX. Dashboards, CRUD de conexões, usuários, relatórios, alertas, agendamentos, permissões.
- **Sincronização AD**: `app/core/sincronizador_ad.py` com LDAP, upsert idempotente, desativação de usuários removidos.
- **Usuários**: CRUD completo em `app/rotas/usuarios.py` com busca por WhatsApp.

---

## 🟢 PRIORIDADE ALTA

### N8N Workflow Único (Dispatcher)

Criar **um único workflow** que serve tanto relatórios quanto alertas:

```
[Cron a cada minuto]
   ↓
[GET /agendamentos/proximas-execucoes]
   ↓
[Para cada agendamento]
   ├─ Se tipo_recurso = "relatorio" → POST /relatorios/{nome}/solicitar
   └─ Se tipo_recurso = "alerta"   → POST /alertas/{nome}/verificar
   ↓
[Se deve_notificar = true ou se é relatório]
   ├─ Para cada destinatário em payload.destinatarios
   │  └─ Para cada canal em payload.canais
   │     ├─ canal "whatsapp" → Evolution API
   │     └─ canal "email"    → SMTP
   ↓
[POST /agendamentos/{id}/marcar-executado]
```

**Status:** Workflows base exportados em `docs/n8n/` (`nexus_dispatcher.json`, `nexus_chatbot.json`). Falta implantar e testar ponta a ponta.

**Vantagem:** adicionar alerta/relatório novo no Nexus = nada muda no N8N.

### Alerta Real do ERP (já implementado: `item_comprimento_excedente`)

O alerta `item_comprimento_excedente` foi implementado e valida a arquitetura com caso real:

- ✅ Destinatários dinâmicos (`contatos_setores` — preparado para integração com `nexus_metas`)
- ✅ Destinatários fixos vindos do banco (`alertas_condicoes`)
- ✅ Multi-banco real (Firebird `REPLICA_TERRA`)
- ✅ Deduplicação por fingerprint SHA256
- ✅ Análise com pandas + estatísticas por origem de medida

**Pendência:** popular `contatos_setores` a partir da tabela `nexus_metas` (telefones de vendedores e assistentes).

---

## 🟡 PRIORIDADE MÉDIA

### Chatbot WhatsApp (parcialmente implementado)

Rotas de sessão existem (`app/rotas/chatbot.py`), tabela `chatbot_sessoes` criada. Workflow N8N exportado.

**Pendências:**
- Testar fluxo completo: menu → seleção de relatório → período → geração → envio
- Integrar com Evolution API para envio de mensagens interativas (botões)

### Identificação do Usuário no Relatório

Endpoint para receber `identificador` (WhatsApp) no payload de solicitação. Se não existir em `usuarios`, criar automaticamente com `origem="whatsapp"`.

---

## 🔵 PRIORIDADE BAIXA / FASE 2

### Aprovações

Workflow de aprovação via WhatsApp:
- Solicitação cai numa fila
- Aprovador recebe mensagem com botões (sim/não)
- Após aprovação, executa

### Parâmetros Complexos

Expandir schema de `config.json` para suportar:
- **Data/Período** (`data_inicio`, `data_fim` com validação de intervalo)
- **Lista de valores** (multi-select: `["filial_1", "filial_2"]`)
- **Range numérico** (`{"min": 80, "max": 120}`)
- **Objeto aninhado** (filtros compostos com campos independentes)
- **Ordenação dinâmica** (`{"campo": "nome", "direcao": "asc"}` com whitelist)

### Sub-relatórios

Possibilidade avaliada para cenários como:
- **Consolidação**: um relatório "Visão Geral" que incorpora seções de outros relatórios
- **Drill-down**: relatório de filiais que dispara sub-relatório de vendedores
- **Anexos em alertas**: alerta detecta problema e anexa PDF como evidência

### Observabilidade

- Métricas Prometheus
- Dashboard Grafana
- Alertas de erro do próprio Nexus

---

## 📋 Roadmap Sugerido

1. **N8N Workflow Único** — implantar e testar dispatcher
2. **Popular `contatos_setores`** — integrar `nexus_metas` no alerta `item_comprimento_excedente`
3. **Chatbot WhatsApp** — testar fluxo completo com Evolution API
4. **Identificação do Usuário** — auto-cadastro por WhatsApp
5. **Aprovações** — workflow de autorização
6. **Parâmetros Complexos** — schema expandido
7. **Observabilidade** — métricas e alertas

---

## ⚠️ Pontos de Atenção

### Cache de conexões
Sempre que alterar dados de uma conexão no banco, chamar `POST /admin/conexoes/{id}/limpar-cache` ou reiniciar o uvicorn.

### Migrações de banco
Arquivos em `banco/` são executados em ordem alfabética na inicialização:
- `001_estrutura_inicial.sql` — tabelas base (idempotente com `IF NOT EXISTS`)
- `002_chatbot_sessoes.sql` — tabela de sessões
- `003_timezone_agendamentos.sql` — coluna `timezone` em agendamentos

Para novas alterações: criar `004_xxx.sql`. `ALTER` não é naturalmente idempotente.

### Backup da chave Fernet
**Crítico.** Sem a chave, senhas são irrecuperáveis. Ver `RECUPERACAO.md`.

### Tabela `configuracoes`
Existe tabela `configuracoes` no banco (chave-valor) usada para `modo_teste`, `test_email`, `test_whatsapp`. Gerencie via SQL direto ou admin.
