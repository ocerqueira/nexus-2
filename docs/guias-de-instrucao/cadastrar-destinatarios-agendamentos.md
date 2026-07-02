# Cadastrar destinatários e agendamentos

Guia ponta a ponta para configurar quem recebe relatórios e alertas via Swagger ou Admin Panel.

> Endpoints `/admin/*` aceitam **form-data** (não JSON). No Swagger, preencha os campos do formulário.

---

## Relatórios: configuração completa

### 1 — Criar usuário

`POST /admin/usuarios`

| Campo | Exemplo |
|-------|---------|
| `nome` | `Lucas Cerqueira` |
| `whatsapp_numero` | `5517981006771` (DDI+DDD+número) |
| `email` | `lucas@noroaco.com.br` |
| `origem` | `manual` |
| `departamento` | `Logística` (opcional) |

O `id` do usuário aparece na listagem `GET /admin/usuarios`.

---

### 2 — Verificar ID do relatório

`GET /relatorios` → localize o relatório pelo campo `nome` → anote o `id`.

---

### 3 — Destinatário fixo do relatório

Recebe o relatório **sempre** que for disparado — por agendamento ou on-demand.

`POST /admin/relatorios/{relatorio_id}/destinatarios`

| Campo | Valores |
|-------|---------|
| `usuario_id` | ID do usuário |
| `canais` | `whatsapp` e/ou `email` |
| `formato_whatsapp` | `documento` (PDF anexo) ou `resumo_texto` (mensagem de texto) |

---

### 4 — Criar agendamento

`POST /admin/agendamentos`

| Campo | Exemplo |
|-------|---------|
| `tipo` | `relatorio` |
| `recurso_nome` | `itens_comprimento_por_carga` |
| `usuario_id` | ID do criador (também recebe o relatório) |
| `canais` | `whatsapp` |
| `cron` | `0 7 * * *` |
| `parametros` | `{"data_inicio":"{{mes_atual_inicio}}","data_fim":"{{hoje}}"}` |

**Exemplos de cron:**

| Expressão | Quando dispara |
|-----------|---------------|
| `0 7 * * *` | Todo dia às 07:00 |
| `0 7 * * 1-5` | Dias úteis às 07:00 |
| `0 7 * * 1` | Toda segunda às 07:00 |
| `0 8 1 * *` | Dia 1 de cada mês às 08:00 |

**Tokens dinâmicos** (resolvidos pelo Nexus na execução):

| Token | Resolve para |
|-------|-------------|
| `{{hoje}}` | Data atual (AAAA-MM-DD) |
| `{{ontem}}` | Ontem |
| `{{mes_atual_inicio}}` | Primeiro dia do mês atual |
| `{{mes_atual_fim}}` | Último dia do mês atual |
| `{{mes_anterior_inicio}}` | Primeiro dia do mês anterior |
| `{{mes_anterior_fim}}` | Último dia do mês anterior |
| `{{semana_atual_inicio}}` | Segunda-feira da semana atual |
| `{{semana_atual_fim}}` | Domingo da semana atual |

---

### 5 — Destinatários extras do agendamento

Recebem **somente** quando esse agendamento específico rodar.

`POST /admin/agendamentos/{agendamento_id}/destinatarios`

| Campo | Exemplo |
|-------|---------|
| `usuario_id` | ID do usuário |
| `canais` | `whatsapp` |

---

### Quem recebe o quê

```
Relatório disparado
  ├─ relatorios_destinatarios  → recebem SEMPRE (passo 3)
  ├─ agendamentos_destinatarios → recebem só neste agendamento (passo 5)
  └─ usuario_id do agendamento  → criador sempre recebe (passo 4)
```

---

### Disparar manualmente via API

```
POST /relatorios/{nome}/solicitar?formato=pdf&notificar=true
Body: {"parametros": {"data_inicio": "2025-01-01", "data_fim": "2025-01-31"}}
Header: X-Api-Key: <chave>
```

Com `notificar=true`, o Nexus cria as entregas no banco e o workflow `nexus_entregas_sender` no n8n entrega.

---

## Alerta `item_comprimento_excedente`: destinatários dinâmicos

### Como funciona

O processador busca no ERP os telefones dos vendedores de cada item afetado (`TELEFONE_VENDEDOR` e `TELEFONE_VENDEDOR2`). Esses números viram entregas **automaticamente**, sem cadastro prévio no Nexus.

```
Item com comprimento excedente
  ├─ TELEFONE_VENDEDOR  → entrega individual para o vendedor
  └─ TELEFONE_VENDEDOR2 → entrega individual para o assistente
```

Cada vendedor recebe apenas os itens dos seus próprios pedidos (`modo_mensagem: individual`).

---

### Destinatários fixos do alerta

Para setores que recebem **todos** os itens (Expedição, Diretoria, Qualidade):

`GET /alertas` → anote o `id` do `item_comprimento_excedente`.

`POST /admin/alertas/{alerta_id}/destinatarios`

| Campo | Valores |
|-------|---------|
| `usuario_id` | ID do usuário |
| `canais` | `whatsapp` e/ou `email` |
| `modo_mensagem` | `consolidado` (resumo geral) ou `individual` (uma mensagem por item) |
| `limite_hora` | Max mensagens por hora (opcional) |
| `limite_dia` | Max mensagens por dia (opcional) |

---

### Cooldown e deduplicação

`POST /admin/alertas/{alerta_id}/cooldown`

```
cooldown_minutos: 60
```

O Nexus faz deduplicação por fingerprint (SHA256 dos campos do item): se o mesmo item já foi notificado dentro do cooldown, é ignorado automaticamente.

Para forçar disparo ignorando cooldown e dedup:

```
POST /alertas/{nome}/verificar?forcar=true
```

---

### Fluxo completo do alerta

```
POST /alertas/item_comprimento_excedente/verificar
  │
  ├─ Verifica cooldown global
  ├─ Executa processador → busca itens no ERP
  ├─ Por item: verifica fingerprint (dedup granular)
  │
  ├─ Destinatários dinâmicos (do ERP)
  │    └─ telefone_vendedor/assistente → entrega individual por item
  │
  └─ Destinatários fixos (alertas_destinatarios)
       ├─ modo consolidado → 1 entrega com resumo de tudo
       └─ modo individual  → 1 entrega por item
```

---

### Testar o alerta sem esperar cooldown

```
POST /alertas/item_comprimento_excedente/verificar?forcar=true
Header: X-Api-Key: <chave>
Body: {"parametros": {"data_inicio": "2025-01-01"}}
```

Verificar entregas criados: `GET /entregas/pendentes`
