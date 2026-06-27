# Workflow N8N — Nexus Dispatcher

> Workflow único que atende **relatórios e alertas** agendados no Nexus.
> O N8N consulta o Nexus a cada minuto e decide o que fazer com cada agendamento.
> Envio via **Evolution API** (WhatsApp) e SMTP (Email).

---

## Visão geral do fluxo

```
[Cron Trigger a cada minuto]
       │
       ▼
[GET /agendamentos/proximas-execucoes]
       │
       ├── total = 0 → fim (nada a fazer)
       │
       └── total > 0
              │
              ▼
       [Loop: para cada agendamento]
              │
              ├── tipo_recurso = "relatorio" ──▶ POST /relatorios/{nome}/solicitar?formato=pdf
              │                                        │
              │                                        └── anexa PDF no email
              │
              └── tipo_recurso = "alerta"   ──▶ POST /alertas/{nome}/verificar
                                                     │
                                                     ├── deve_notificar = false → pula
                                                     │
                                                     └── deve_notificar = true
                                                            │
                                                            ▼
                                                     [Loop: cada destinatário]
                                                            │
                                                            ├── canal "whatsapp" → Evolution API
                                                            └── canal "email"    → SMTP
                                                                      │
                                                                      ▼
                                                     [POST /agendamentos/{id}/marcar-executado]
```

---

## Nós do workflow

### 1. Cron Trigger

- **Tipo:** Schedule Trigger (Cron)
- **Config:** `* * * * *` (a cada minuto)
- **Nome:** "Cron — a cada minuto"

---

### 2. Consultar agendamentos prontos

- **Tipo:** HTTP Request
- **Método:** GET
- **URL:** `{{ $env.NEXUS_URL }}/agendamentos/proximas-execucoes`
- **Resposta esperada:**

```json
{
  "total": 2,
  "agendamentos": [
    {
      "id": 1,
      "usuario_id": 1,
      "tipo_recurso": "alerta",
      "recurso_id": 1,
      "frequencia": "diaria",
      "horarios": [{"hora": 9, "minuto": 0}],
      "parametros": {"forcar": false},
      "canais": ["whatsapp", "email"],
      "ultimo_envio": "2026-06-21T09:00:00",
      "proximo_envio": "2026-06-22T09:00:00"
    },
    {
      "id": 2,
      "tipo_recurso": "relatorio",
      "recurso_id": 1,
      "frequencia": "semanal",
      "dia_semana": 1,
      "horarios": [{"hora": 8, "minuto": 0}],
      "canais": ["email"],
      "ultimo_envio": null,
      "proximo_envio": "2026-06-22T08:00:00"
    }
  ]
}
```

---

### 3. IF — Tem agendamentos?

- **Condição:** `{{ $json.total > 0 }}`
- **False:** fim do workflow
- **True:** continua para o Loop

---

### 4. Loop Over Items

- **Tipo:** Loop Over Items (ou Split In Batches com batch size = 1)
- **Fonte:** `{{ $json.agendamentos }}`
- Cada iteração expõe um agendamento individual

---

### 5. Switch — Chamar endpoint conforme tipo

> **Nota:** O `recurso_nome` (nome técnico do alerta/relatório) já é retornado pelo endpoint `GET /agendamentos/proximas-execucoes`. Não é necessário fazer chamadas extras para resolver `recurso_id → nome`.

#### 5a. Relatório

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $json.NEXUS_URL }}/relatorios/{{ $json.recurso_nome }}/solicitar`
- **Query:** `?formato=pdf`
- **Body (JSON):**
```json
{
  "parametros": {{ $json.parametros }}
}
```
- **Options:** `responseFormat: "file"`, `outputDataFieldName: "data"`
- **Resposta:** PDF binário (Content-Type: application/pdf)

#### 5b. Alerta

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $json.NEXUS_URL }}/alertas/{{ $json.recurso_nome }}/verificar`
- **Body (JSON):**
```json
{
  "parametros": {{ $json.parametros }}
}
```
- **Resposta (quando deve_notificar = true):**

```json
{
  "alerta": {"id": 1, "nome": "item_comprimento_excedente", "titulo": "...", "severidade": "critico"},
  "deve_notificar": true,
  "resumo": "3 itens com comprimento excedente",
  "total_encontrado": 3,
  "itens_notificados": 3,
  "despachos": [
    {"id": 1, "status": "pendente", "canal": "whatsapp", "destino": "5511999999999", "destinatario": "João", "enviar_apos": null},
    {"id": 2, "status": "pendente", "canal": "whatsapp", "destino": "5511988888888", "destinatario": "Maria", "enviar_apos": null}
  ],
  "despachos_bloqueados_rate_limit": 0,
  "historico_id": 42
}
```

> **Importante:** O Nexus cria os despachos internamente. O dispatcher **não** precisa fazer loop de destinatários nem chamar a Evolution API — isso é responsabilidade do `nexus_despachos_sender`. O dispatcher apenas chama `/verificar` e depois `/marcar-executado`.

---

### 7. IF — Deve notificar?

- **Condição (alertas):** `{{ $json.deve_notificar === true }}`
- **Condição (relatórios):** sempre true (relatórios sempre distribuem)
- **False:** pular envio, ir direto para marcar-executado

---

### 8. Enviar notificações

> **Arquitetura:** para **alertas**, o Nexus já criou os despachos internamente. O dispatcher apenas confirma a execução via `marcar-executado`. A entrega real (Evolution/SMTP) é feita pelo `nexus_despachos_sender` em paralelo.
>
> Para **relatórios**, o dispatcher ainda executa o envio direto (PDF via Evolution ou SMTP).

#### 8a. WhatsApp com PDF (relatórios)

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $json.EVOLUTION_URL }}/message/sendMedia/{{ $json.EVOLUTION_INSTANCE }}`
- **Headers:** `apikey: {{ $json.EVOLUTION_API_KEY }}`
- **Body (JSON):**
```json
{
  "number": "{{ $json.usuario_whatsapp }}",
  "mediatype": "document",
  "mimetype": "application/pdf",
  "caption": "{{ $json.caption }}",
  "media": "{{ $json.pdf_base64 }}",
  "fileName": "{{ $json.filename }}"
}
```

#### 8e. Email com PDF anexo (relatórios)

- **Tipo:** Email (Send) com anexo
- **From:** `{{ $json.SMTP_USER }}`
- **To:** `{{ $json.usuario_email }}`
- **Subject:** `Relatório: {{ $json.recurso_nome }}`
- **Anexo:** PDF em base64 (gerado pelo nó "Code — PDF base64")

---

### 9. Callback — Marcar como executado

Após todos os envios, confirmar ao Nexus:

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $json.NEXUS_URL }}/agendamentos/{{ $json.agendamento_id }}/marcar-executado`
- **Sem body**

**Resposta esperada:**
```json
{
  "status": "executado",
  "id": 1,
  "ultimo_envio": "2026-06-22T09:00:15",
  "proximo_envio": "2026-06-23T09:00:00"
}
```

---

## Configuração do workflow

O workflow usa um nó **⚙️ Config (Edite aqui)** do tipo `Set` com as seguintes variáveis (atualize os valores antes de ativar):

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `NEXUS_URL` | URL base da API Nexus | `http://192.168.1.100:8000` |
| `EVOLUTION_URL` | URL da Evolution API | `https://evo.empresa.com` |
| `EVOLUTION_INSTANCE` | Nome da instância Evolution | `nexus-producao` |
| `EVOLUTION_API_KEY` | API Key da instância Evolution | `abc123...` |
| `SMTP_HOST` | Servidor SMTP | `smtp.gmail.com` |
| `SMTP_PORT` | Porta SMTP | `587` |
| `SMTP_USER` | Usuário SMTP (remetente) | `nexus@empresa.com` |
| `SMTP_PASSWORD` | Senha ou app password | `xxxx xxxx xxxx xxxx` |

> **Nota:** O `recurso_nome` já é resolvido pelo endpoint `GET /agendamentos/proximas-execucoes` (via JOIN no banco). Não é necessário fazer chamadas extras para mapear `recurso_id → nome`.

---

## Exemplo de payload Evolution API para mídia (PDF)

Se for enviar o PDF do relatório como anexo via WhatsApp:

- **URL:** `{{ $env.EVOLUTION_URL }}/message/sendMedia/{{ $env.EVOLUTION_INSTANCE }}`
- **Body (JSON):**

```json
{
  "number": "5511999999999",
  "mediatype": "document",
  "fileName": "relatorio_teste_conexoes.pdf",
  "caption": "Segue o relatório solicitado",
  "media": "data:application/pdf;base64,{{ $binary.data }}"
}
```

> Nota: o N8N precisará converter o PDF binário recebido do Nexus para base64.
> Use um nó Function com:
> ```javascript
> return {
>   base64: Buffer.from(await items[0].binary.data).toString('base64')
> };
> ```

---

## Resumo dos endpoints Nexus usados pelo workflow

| Ordem | Método | Endpoint | Quando |
|-------|--------|----------|--------|
| 1 | GET | `/agendamentos/proximas-execucoes` | Toda execução (1/min) |
| 2a | POST | `/relatorios/{nome}/solicitar?formato=pdf` | Se `tipo_recurso = relatorio` |
| 2b | POST | `/alertas/{nome}/verificar` | Se `tipo_recurso = alerta` |
| 3 | POST | `/agendamentos/{id}/marcar-executado` | Após envio concluído |

---

## Diagrama visual para importação no N8N

```
[Schedule: */1 * * * *]
        │
        ▼
[⚙️ Config (Set)]
        │
        ▼
[HTTP: GET /proximas-execucoes]
        │
        ▼
[IF: total > 0] — false → fim
   true  ↓
        ▼
[Split Out: agendamentos]
        │
        ▼
[IF: tipo_recurso]

   "alerta"                         "relatorio"
        │                                │
        ▼                                ▼
[POST /alertas/{nome}/            [POST /relatorios/{nome}/
 verificar?forcar=true]            solicitar?formato=pdf]
        │                                │
        ▼                                ▼
[IF: deve_notificar?]              [Code: PDF base64]
   false → marcar-executado             │
   true  ↓                              ▼
        ▼                         ┌─────┴─────┐
[Code: montar destinatários]      │ WhatsApp  │  │ Email     │
   (consolidadas ou individuais)   │ sendMedia │  │ SMTP+PDF  │
        │                          └─────┬─────┘
        ▼                                │
[Switch: canal]                          │
   "whatsapp"    "email"                 │
        │           │                     │
        ▼           ▼                     │
[Evolution     [SMTP Send]               │
 sendText]        │                      │
        │           │                     │
        └───────────┴─────────────────────┘
                        │
                        ▼
              [POST /agendamentos/
               {id}/marcar-executado]
```

---

## Observações importantes

1. **Tolerância de atraso:** o endpoint `/proximas-execucoes` já trata atrasos de até 60 minutos automaticamente. Se o N8N ficar offline por 30min, ao voltar os agendamentos ainda estarão lá (recalculados se passou de 60min).

2. **Idempotência:** o workflow pode rodar em paralelo sem risco — o cooldown no Nexus impede disparos duplicados de alertas.

3. **Escalabilidade:** se houver 50 agendamentos prontos ao mesmo tempo, o loop processa sequencialmente. Para paralelismo, use Split In Batches com batch size maior.

4. **Erro no envio:** se a Evolution API falhar, o N8N pode retentar. O `marcar-executado` só deve ser chamado após confirmação de todos os envios — ou mova-o para um caminho separado com tratamento de erro.

5. **Segurança:** todos os HTTP Requests devem incluir o header `X-Api-Key: {{ $env.NEXUS_API_KEY }}`.


> Chatbot WhatsApp: ver [Configurar chatbot WhatsApp](../guias-de-instrucao/configurar-chatbot-whatsapp.md).
