# Referência — API Rotas

## Visão geral

O Nexus expõe uma API REST via FastAPI na porta 8000. Todas as rotas aceitam e retornam JSON, exceto os formatos `html` e `pdf` de relatórios.

## Sistema

### `GET /saude`

Health check do sistema.

**Resposta**:
```json
{
  "status": "ok",
  "servico": "nexus",
  "versao": "0.1.0",
  "ambiente": "desenvolvimento",
  "componentes": {
    "api": "ok",
    "banco_dados": "ok"
  }
}
```

Status possíveis: `ok` (tudo funcionando), `degradado` (banco indisponível).

### `POST /sincronizar`

Força a sincronização do filesystem com o banco. Útil após criar/remover pastas de relatórios ou alertas sem reiniciar a aplicação.

**Resposta**:
```json
{
  "status": "ok",
  "mensagem": "Sincronização concluída",
  "detalhes": {
    "relatorios": {"inseridos": 0, "atualizados": 0, "removidos": 0, "reativados": 0, "ativos": 1},
    "alertas": {"inseridos": 0, "atualizados": 0, "removidos": 0, "reativados": 0, "ativos": 1}
  }
}
```

---

## Relatórios

### `GET /relatorios`

Lista todos os relatórios com status `ativo` cadastrados no banco.

**Resposta**:
```json
{
  "total": 1,
  "relatorios": [
    {"id": 1, "nome": "teste_conexoes", "titulo": "Teste de Conexões", "descricao": "Catálogo de conexões", "categoria": null, "status": "ativo"}
  ]
}
```

### `POST /relatorios/{nome}/solicitar`

Solicita a geração de um relatório.

**Parâmetros de path**:

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `nome` | string | Nome técnico do relatório (pasta em `app/relatorios/`) |

**Query parameters**:

| Parâmetro | Tipo | Padrão | Valores |
|-----------|------|--------|---------|
| `formato` | string | `json` | `json`, `html`, `pdf` |

**Body** (opcional):
```json
{
  "parametros": {
    "apenas_ativas": true,
    "tipo_banco": "postgres"
  }
}
```

**Resposta por formato**:

- `json`: `{"status": "sucesso", "relatorio": "...", "payload": {...}}`
- `html`: HTML string com `Content-Type: text/html`
- `pdf`: bytes binários com `Content-Type: application/pdf` e header `Content-Disposition: attachment`

**Erros**:

| Código | Condição |
|--------|----------|
| 400 | Formato inválido ou parâmetros inválidos |
| 404 | Relatório não encontrado |
| 500 | Erro no processador |

---

## Alertas

### `GET /alertas`

Lista todos os alertas com status `ativo` no banco.

**Resposta**:
```json
{
  "total": 1,
  "alertas": [
    {"id": 1, "nome": "conexoes_inativas", "titulo": "Conexões Inativas Detectadas", "descricao": "...", "severidade": "aviso", "status": "ativo"}
  ]
}
```

### `POST /alertas/{nome}/verificar`

Executa a verificação de um alerta.

**Parâmetros de path**:

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `nome` | string | Nome técnico do alerta (pasta em `app/alertas/`) |

**Query parameters**:

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `forcar` | boolean | `false` | Se `true`, ignora o cooldown |

**Body** (opcional):
```json
{
  "parametros": {
    "incluir_observacoes": false
  }
}
```

**Resposta (deve notificar)**:
```json
{
  "alerta": {"id": 1, "nome": "item_comprimento_excedente", "titulo": "Comprimento Excedente", "severidade": "critico"},
  "deve_notificar": true,
  "resumo": "3 itens com comprimento excedente",
  "total_encontrado": 3,
  "itens_notificados": 3,
  "despachos": [
    {"id": 1, "status": "pendente", "canal": "whatsapp", "destino": "5511999999999", "destinatario": "João Vendedor", "enviar_apos": null},
    {"id": 2, "status": "pendente", "canal": "whatsapp", "destino": "5511988888888", "destinatario": "Maria Assistente", "enviar_apos": null}
  ],
  "despachos_bloqueados_rate_limit": 0,
  "historico_id": 42
}
```

Os despachos são inseridos na tabela `despachos` com `status=pendente`. O workflow `nexus_despachos_sender` no n8n faz polling em `/despachos/pendentes` e executa a entrega.

**Resposta (em cooldown)**:
```json
{
  "alerta": {"id": 1, "nome": "conexoes_inativas", "titulo": "...", "severidade": "aviso"},
  "deve_notificar": false,
  "motivo": "em_cooldown",
  "tempo_restante_min": 45
}
```

**Resposta (sem dados)**:
```json
{
  "alerta": {"id": 1, "nome": "conexoes_inativas", "titulo": "...", "severidade": "aviso"},
  "deve_notificar": false,
  "motivo": "sem_dados",
  "resumo": "Nenhuma conexão inativa"
}
```

**Campos da resposta**:

| Campo | Descrição |
|-------|-----------|
| `alerta` | Dados básicos do alerta (id, nome, título, severidade) |
| `deve_notificar` | `true` se despachos pendentes foram criados |
| `motivo` | Se `deve_notificar=false`, explica o motivo |
| `resumo` | Texto curto descritivo do resultado |
| `total_encontrado` | Total de itens retornados pelo processador |
| `itens_notificados` | Itens que passaram pelo filtro de cooldown/dedup |
| `despachos` | Array de despachos pendentes criados (id, canal, destino, destinatario, enviar_apos) |
| `despachos_bloqueados_rate_limit` | Despachos bloqueados por rate limit (auditável) |
| `historico_id` | ID do registro de auditoria em `historico` |

**Erros**:

| Código | Condição |
|--------|----------|
| 404 | Alerta não encontrado ou sem processador registrado |
| 500 | Erro no processador |

**Campo `motivo` quando `deve_notificar = false`:**

| `motivo` | Causa |
|---|---|
| `sem_dados` | Query retornou zero linhas |
| `em_cooldown` | Alerta em cooldown global |
| `todos_itens_em_cooldown` | Itens encontrados, mas todos já foram notificados dentro do cooldown |
| `parametros_invalidos` | Parâmetros rejeitados pelo `validar()` do processador |

---

---

## Despachos

Unidades rastreáveis de entrega. Criados internamente pelo Nexus ao verificar alertas ou solicitar relatórios com `notificar=true`. O workflow `nexus_despachos_sender` no n8n faz polling e executa o envio.

### `GET /despachos/pendentes`

Retorna despachos com `status=pendente` e `enviar_apos IS NULL OR enviar_apos <= NOW()`. Endpoint principal do n8n sender.

**Query parameters**:

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `canal` | string | Filtrar por canal (`whatsapp`, `email`) |
| `limite` | integer | Máximo de registros retornados (padrão: 50) |

**Resposta**:
```json
{
  "total": 2,
  "despachos": [
    {
      "id": 1,
      "canal": "whatsapp",
      "destino": "5511999999999",
      "payload": {"mensagem": "⚠️ Item X com comprimento excedente"},
      "alerta_id": 1,
      "relatorio_nome": null,
      "tentativas": 0
    }
  ]
}
```

### `GET /despachos`

Lista histórico de despachos com filtros.

**Query parameters**: `status`, `canal`, `alerta_id`, `relatorio_nome`, `limite`, `offset`.

### `PATCH /despachos/{id}/status`

Callback do n8n após tentativa de envio.

**Body**:
```json
{
  "status": "enviado",
  "tentativas": 1,
  "erro": null
}
```

Status válidos: `enviado` | `falhou` | `confirmado` | `cancelado`.

Despachos com `status=falhou` e `tentativas < 3` voltam automaticamente para `pendente` no próximo polling.

---

## Chatbot

Rotas de sessão do chatbot WhatsApp. Persistem estado entre mensagens para navegação por menus.

### `GET /chatbot/sessao/{numero}`

Retorna a sessão atual de um número WhatsApp. Se não existir, retorna `etapa: "idle"`.

**Parâmetros de path**: `numero` — número WhatsApp sem `@s.whatsapp.net` (ex: `5517981006771`).

**Resposta**:
```json
{
  "numero": "5517981006771",
  "etapa": "aguardando_periodo",
  "recurso_tipo": "relatorio",
  "recurso_nome": "pedidos_por_vendedor",
  "parametros": { "cod_empresa": 1 }
}
```

**Etapas possíveis:**

| `etapa` | Significado |
|---|---|
| `idle` | Sem sessão ativa (inicial) |
| `aguardando_menu` | Menu principal enviado, aguardando seleção |
| `aguardando_periodo` | Usuário selecionou relatório, aguardando período |
| `aguardando_data_inicio` | Período personalizado: aguardando data de início (texto) |
| `aguardando_data_fim` | Aguardando data de fim (texto) |

### `PUT /chatbot/sessao/{numero}`

Cria ou atualiza a sessão.

**Body**:
```json
{
  "etapa": "aguardando_periodo",
  "recurso_tipo": "relatorio",
  "recurso_nome": "pedidos_por_vendedor",
  "parametros": { "cod_empresa": 1, "data_inicio": "2026-01-01" }
}
```

**Resposta**: `{"numero": "...", "etapa": "aguardando_periodo"}`

### `DELETE /chatbot/sessao/{numero}`

Limpa a sessão (reset para `idle`).

**Resposta**: `{"numero": "...", "etapa": "idle"}`

---

## Agendamentos

### `GET /agendamentos/proximas-execucoes`

**Endpoint principal do dispatcher N8N** — consultado a cada minuto via Cron.

Retorna agendamentos ativos cujo `proximo_envio` já passou. Já inclui o `recurso_nome` resolvido (nome técnico do alerta/relatório), eliminando a necessidade de chamadas extras para resolver `recurso_id → nome`.

**Resposta**:
```json
{
  "total": 1,
  "agendamentos": [
    {
      "id": 1,
      "usuario_id": 1,
      "tipo_recurso": "alerta",
      "recurso_id": 1,
      "recurso_nome": "item_comprimento_excedente",
      "usuario_nome": "João Silva",
      "usuario_whatsapp": "5511999999999",
      "usuario_email": "joao@empresa.com",
      "frequencia": "diaria",
      "horarios": [{"hora": 9, "minuto": 0}],
      "parametros": {"cod_empresa": 1},
      "canais": ["whatsapp", "email"],
      "proximo_envio": "2026-06-24T09:00:00"
    }
  ]
}
```

### `POST /agendamentos/{id}/marcar-executado`

Confirma a execução de um agendamento. Atualiza `ultimo_envio` e recalcula `proximo_envio`. Chamado pelo dispatcher **após** todos os envios concluírem.

**Resposta**:
```json
{
  "status": "executado",
  "id": 1,
  "ultimo_envio": "2026-06-24T09:00:15",
  "proximo_envio": "2026-06-25T09:00:00"
}
```
