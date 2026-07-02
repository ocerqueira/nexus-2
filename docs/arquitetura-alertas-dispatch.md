# Arquitetura de Dispatch — Alertas e Relatórios

> Decisões tomadas em 2026-06-24. Implementado em migration 005.

---

## Conceito central

```
EVENTO (alerta disparou / relatório gerado)
       │
       ▼
  QUEM RECEBE?
  ├─ Dinâmicos     ← processador resolve em runtime (vendedor, responsável do item)
  ├─ Fixos         ← admin configura por alerta/relatório (alertas_destinatarios / relatorios_destinatarios)
  └─ Agendamento   ← criador + lista extra (agendamentos_destinatarios)
       │
       ▼
  COMO RECEBE?
  ├─ Canal: whatsapp | email | sms
  ├─ Modo (alertas): individual (1 msg/item) | agrupado (todos itens numa msg)
  ├─ Formato (relatórios): documento PDF | resumo_texto
  └─ Janela de silêncio → enviar_apos (não perturbar entre X e Y horas)
       │
       ▼
  DESPACHO = (destinatário × canal × payload renderizado)
  Inserido em tabela `entregas` com status='pendente'
       │
       ▼
  N8N: nexus_entregas_sender
  Polling GET /entregas/pendentes → envia → PATCH /entregas/{id}/status
```

**Alertas = mensagem individual por item.** Consolidado pertence a relatórios.

---

## Tabelas (migration 005)

### `alertas_destinatarios`
Substitui `alertas_condicoes` para destinatários e canais.

| Coluna | Descrição |
|---|---|
| `alerta_id` | FK alertas |
| `usuario_id` | FK usuarios (incluindo `origem='externo'`) |
| `canais` | `["whatsapp", "email", "sms"]` |
| `modo_mensagem` | `individual` \| `agrupado` |
| `limite_hora` | Max entregas/hora — NULL = sem limite |
| `limite_dia` | Max entregas/dia — NULL = sem limite |

### `relatorios_destinatarios`

| Coluna | Descrição |
|---|---|
| `relatorio_id` | FK relatorios |
| `usuario_id` | FK usuarios |
| `canais` | canais habilitados |
| `formato_whatsapp` | `documento` \| `resumo_texto` |
| `filtro_parametros` | JSONB — override de parâmetros por destinatário (para `modo_execucao='por_destinatario'`) |

### `agendamentos_destinatarios`
Destinatários extras por agendamento, além do criador (`agendamentos.usuario_id`).

### `alertas_itens_notificados`
Fingerprint por item para cooldown granular.

| Coluna | Descrição |
|---|---|
| `alerta_id` | FK alertas |
| `item_fingerprint` | SHA256 do item. Alertas sistêmicos usam hash do estado global. |
| `ultimo_disparo` | Usado para checar cooldown: `ultimo_disparo + cooldown_minutos > agora` → em cooldown |

### `entregas`
Unidade mínima rastreável de entrega.

| Coluna | Descrição |
|---|---|
| `canal` | `whatsapp` \| `email` \| `sms` |
| `destino` | Número ou email |
| `payload` | JSONB renderizado: `{mensagem}` \| `{assunto, html}` \| `{documento_base64, mimetype, caption}` |
| `status` | `pendente` → `processando` → `enviado` → `confirmado` \| `falhou` \| `bloqueado_rate_limit` \| `cancelado` |
| `enviar_apos` | NULL = enviar agora. Preenchido se janela de silêncio ativa. |
| `processando_em` | Timestamp do claim atômico do polling (`FOR UPDATE SKIP LOCKED`) |
| `acao_requerida` | TRUE = destinatário deve confirmar ação (escalação futura) |
| `escalado_para` | FK usuarios — para quem escalar se `prazo_acao` expirar |

---

## Cooldown: por item, não por alerta

**Problema do cooldown global:** item A em cooldown bloqueia item B novo.

**Solução:** cooldown operado por fingerprint de item via `alertas_itens_notificados`.

```
Para cada item do processador:
  item_fingerprint = SHA256(json_sorted(linha_completa))
  se item_fingerprint em cooldown → pular este item
  senão → criar entregas para este item + atualizar fingerprint
```

Fingerprints e `alertas.ultimo_disparo` só são atualizados **se alguma entrega
foi criada de fato** — disparo sem destinatário, bloqueado por rate limit ou
sem template não entra em cooldown (será retentado no próximo ciclo).

Alertas sistêmicos (sem itens ERP, ex: `conexoes_inativas`):
```
fingerprint = SHA256(json_sorted(conjunto_todo))
cooldown opera sobre o estado global
```

`alertas.cooldown_minutos` → regra global configurável no admin (sem redeploy).

---

## Fingerprint: inclui valores

Fingerprint calculado sobre **todos os campos** da linha (não só chaves).
Mudança de valor em qualquer campo → novo hash → dispara alerta.

```python
item_fingerprint = SHA256(json.dumps(sorted(linha.items())))
```

---

## Janela de silêncio

Configurada por usuário: `usuarios.silencio_inicio` / `silencio_fim` / `silencio_ativo`.

Quando a entrega é criada dentro da janela → `entregas.enviar_apos = próximo_fim_janela`.
N8N só busca entregas onde `enviar_apos IS NULL OR enviar_apos <= NOW()`.

Cruzamento de meia-noite suportado (ex: 22:00 → 06:00).

---

## Rate limit

Por par `(alerta, destinatário)` configurado em `alertas_destinatarios.limite_hora` / `limite_dia`.

Quando excedido: entrega inserido com `status='bloqueado_rate_limit'` (auditável, não silencioso).

---

## Relatório filtrado por destinatário

`relatorios.modo_execucao = 'por_destinatario'`:
- Processador roda uma vez por destinatário
- Usa `relatorios_destinatarios.filtro_parametros` como override dos parâmetros
- Cada destinatário recebe PDF com seus próprios dados

Caso de uso: relatório de comissões onde cada vendedor vê só os próprios dados.

---

## Destinatários externos

`usuarios.origem = 'externo'`: clientes, motoristas, fornecedores, transportadoras.
Têm `whatsapp_numero` / `email`, sem acesso ao sistema Nexus.
Participam normalmente de `alertas_destinatarios` e entregas.

---

## Templates por canal

```
alertas/{nome}/mensagens/
  whatsapp_individual.txt     ← modo=individual, canal=whatsapp
  whatsapp_consolidado.txt    ← modo=agrupado,   canal=whatsapp
  email_individual_assunto.txt
  email_individual_html.html
  email_consolidado_assunto.txt
  email_consolidado_html.html
  sms_individual.txt          ← futuro

relatorios/{nome}/
  template.html               ← PDF (já existe)
  mensagens/
    whatsapp/resumo.txt       ← futuro (formato_whatsapp=resumo_texto)
```

API canônica: `renderizar_entrega(nome_alerta, canal, modo, contexto, linha?)`.

---

## Fluxo N8N (dois workflows)

### `nexus_dispatcher.json` — Agendamentos Trigger
```
Cron → GET /agendamentos/proximas-execucoes
  → [alerta]   POST /alertas/{nome}/verificar
               (orquestrador cria entregas internamente)
  → [relatório] POST /relatorios/{nome}/solicitar?notificar=true&agendamento_id={id}
               (orquestrador_relatorios cria entregas + PDF internamente)
  → POST /agendamentos/{id}/marcar-executado
```

### `nexus_entregas_sender.json` — Despachos Sender
```
Cron → GET /entregas/pendentes?limite=50
  → Split por entrega
  → Switch canal:
      whatsapp → [texto] Evolution sendText
               → [doc]   Evolution sendMedia
      email    → SMTP (HTML ou com PDF em anexo)
  → Code: avalia statusCode/error
  → PATCH /entregas/{id}/status {status, erro, tentativas}
```

---

## Compressão de PDF

`orquestrador_relatorios._comprimir_pdf()` usa Ghostscript (`gs`) quando disponível.
Configuração: `dPDFSETTINGS=/ebook` (150dpi — balanço qualidade/tamanho).
Se `gs` não instalado, PDF original é enviado sem compressão.

---

## Escalação futura (schema já suporta)

```sql
entregas.acao_requerida = TRUE
entregas.prazo_acao     = NOW() + INTERVAL '2 hours'
entregas.escalado_para  = usuarios.gestor_id  -- hierarquia já existe
```

Job/N8N verifica: `entregas WHERE acao_requerida AND status='enviado' AND prazo_acao < NOW()`
→ cria nova entrega para `escalado_para`.

---

## `alertas_condicoes` — deprecado

Após executar `005b_migrar_alertas_condicoes.sql` e validar:
- `cooldown_minutos` → `alertas.cooldown_minutos`
- `ultimo_disparo`  → `alertas.ultimo_disparo`
- `destinatarios`   → `alertas_destinatarios`
- `canais`          → `alertas_destinatarios.canais`

`DROP TABLE alertas_condicoes` (descomentar no 005b após validação).
