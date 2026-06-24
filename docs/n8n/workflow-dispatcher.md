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
- **URL:** `{{ $json.NEXUS_URL }}/alertas/{{ $json.recurso_nome }}/verificar?forcar=true`
- **Body (JSON):**
```json
{
  "parametros": {{ $json.parametros }}
}
```
- **Resposta (quando deve_notificar = true):**

```json
{
  "alerta": {
    "id": 1,
    "nome": "conexoes_inativas",
    "titulo": "Conexões Inativas",
    "severidade": "alto"
  },
  "deve_notificar": true,
  "resumo": "3 de 5 conexões inativas",
  "total_encontrado": 3,
  "canais": ["whatsapp", "email"],
  "destinatarios": [
    {
      "id": 1,
      "nome": "Gestor TI",
      "email": "gestor@empresa.com",
      "whatsapp": "5511999999999",
      "canais": ["whatsapp", "email"]
    }
  ],
  "mensagens_consolidadas": {
    "whatsapp": "⚠️ *Conexões Inativas*\n\n3 de 5 conexões estão offline...",
    "email_assunto": "Alerta: Conexões Inativas",
    "email_html": "<html><body><h1>Conexões Inativas</h1>...</body></html>"
  },
  "grupos_individuais": [
    {
      "dados_linha": {"conexao": "ERP Unidade 01", "erro": "timeout"},
      "mensagens": {
        "whatsapp": "🔴 ERP Unidade 01: timeout",
        "email_assunto": "Alerta: ERP Unidade 01 offline",
        "email_html": "<p>ERP Unidade 01 está offline: timeout</p>"
      }
    }
  ],
  "dados": [...]
}
```

---

### 7. IF — Deve notificar?

- **Condição (alertas):** `{{ $json.deve_notificar === true }}`
- **Condição (relatórios):** sempre true (relatórios sempre distribuem)
- **False:** pular envio, ir direto para marcar-executado

---

### 8. Enviar notificações

#### 8a. Loop de destinatários

Iterar sobre `{{ $json.destinatarios }}`.

#### 8b. WhatsApp via Evolution API

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $env.EVOLUTION_URL }}/message/sendText/{{ $env.EVOLUTION_INSTANCE }}`
- **Headers:**
  - `apikey: {{ $env.EVOLUTION_API_KEY }}`
  - `Content-Type: application/json`
- **Body (JSON):**

```json
{
  "number": "{{ $json.destinatario.canais.whatsapp }}",
  "text": "{{ $json.mensagem_whatsapp }}"
}
```

**Qual mensagem usar?**
- Se houver `grupos_individuais` com WhatsApp individual → envia uma mensagem por linha
- Senão, envia `mensagens_consolidadas.whatsapp` para cada destinatário

**Exemplo de body para mensagem individual:**
```json
{
  "number": "5511988887777",
  "text": "🔴 ERP Unidade 01 está offline desde 09:30"
}
```

**Exemplo de body para consolidada:**
```json
{
  "number": "5511999999999",
  "text": "⚠️ *Conexões Inativas*\n\n3 de 5 conexões estão offline:\n- ERP Unidade 01\n- DW Analytics\n- Intranet\n\nVerifique o Nexus para detalhes."
}
```

#### 8c. Email via SMTP (alertas)

- **Tipo:** Email (Send)
- **From:** `{{ $json.SMTP_USER }}`
- **To:** `{{ $json.email }}`
- **Subject:** `{{ $json.mensagem_email_assunto }}`
- **HTML:** `{{ $json.mensagem_email_html }}`

> Se houver mensagens individuais: o nó "Code — montar destinatários" gera uma entrada por item com `mensagem_email_assunto` e `mensagem_email_html` individuais.

#### 8d. WhatsApp com PDF (relatórios)

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

5. **Segurança:** quando o Nexus tiver autenticação (API Key), todos os HTTP Requests devem incluir o header `X-API-Key: {{ $env.NEXUS_API_KEY }}`.

---

# Workflow N8N — Chatbot Sob Demanda

> Usuário manda mensagem no WhatsApp → N8N recebe via Evolution Webhook → gera relatório → responde com PDF.
> Fluxo separado do Dispatcher. Roda em paralelo, responde em segundos.

---

## Visão geral do fluxo

```
[Usuário envia "relatorio vendas" no WhatsApp]
       │
       ▼
[Evolution Webhook — event: messages.upsert]
       │
       ▼
[IF: é mensagem de texto e começa com "relatorio"]
   false → [Responde: "Comandos disponíveis: relatorio <nome>"]
   true  ↓
       ▼
[Extrai nome do relatório da mensagem]
       │
       ├── "relatorio" (sem nome) → [GET /relatorios] → [Responde lista]
       │
       └── "relatorio vendas" (com nome)
              │
              ▼
       [POST /relatorios/{nome}/solicitar?formato=pdf]
              │
              ▼
       [Converte PDF para base64]
              │
              ▼
       [Evolution API: sendMedia — envia PDF]
              │
              ▼
       [Responde: "Pronto! Relatório gerado."]
```

---

## Nós do workflow

### 1. Evolution Webhook

- **Tipo:** Webhook
- **Path:** `/evolution-webhook`
- **Método:** POST
- **Evento:** `messages.upsert`

Payload que chega da Evolution:

```json
{
  "event": "messages.upsert",
  "data": {
    "key": {
      "remoteJid": "5511999999999@s.whatsapp.net",
      "fromMe": false
    },
    "message": {
      "conversation": "relatorio teste_conexoes"
    },
    "pushName": "Lucas"
  }
}
```

### 2. IF — É comando de relatório?

- **Condição:** `{{ $json.data.message.conversation.startsWith("relatorio") }}`
- **False:** ignora (não é comando reconhecido)
- **True:** continua

### 3. Function — Extrai argumentos

```javascript
const msg = $json.data.message.conversation;
const partes = msg.split(" ");
const comando = partes[0];       // "relatorio"
const nome = partes.slice(1).join(" "); // "teste_conexoes" ou ""

return {
  remoteJid: $json.data.key.remoteJid,
  pushName: $json.data.pushName,
  comando: comando,
  nome: nome,
  temNome: nome.length > 0
};
```

### 4. IF — Tem nome de relatório?

- **Condição:** `{{ $json.temNome === true }}`
- **False:** lista os relatórios disponíveis

#### 4a. Sem nome → Listar relatórios

- **Tipo:** HTTP Request
- **Método:** GET
- **URL:** `{{ $env.NEXUS_URL }}/relatorios`
- **Resposta:**
```json
{
  "total": 1,
  "relatorios": [
    {"nome": "teste_conexoes", "titulo": "Teste de Conexões", "subtitulo": "Catálogo"}
  ]
}
```

- **Function para montar resposta:**
```javascript
const lista = $json.relatorios.map(r => `• ${r.nome} — ${r.titulo}`).join('\n');
return {
  remoteJid: $input.first().json.remoteJid,
  text: `📊 *Relatórios disponíveis:*\n\n${lista}\n\nEnvie *relatorio <nome>* para gerar.`
};
```

- **Envia:** Evolution API `sendText`

#### 4b. Com nome → Gerar relatório

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $env.NEXUS_URL }}/relatorios/{{ $json.nome }}/solicitar?formato=pdf`
- **Body:** `{ "parametros": {} }`
- **Response:** PDF binário

### 5. IF — Relatório encontrado?

- **Condição:** status code 200
- **False:**
```json
{
  "remoteJid": "{{ $('Function — Extrai argumentos').item.json.remoteJid }}",
  "text": "❌ Relatório '{{ $json.nome }}' não encontrado. Envie *relatorio* para ver a lista."
}
```
Envia via Evolution `sendText`.

- **True:** continua

### 6. Function — Converte PDF para base64

```javascript
const base64 = Buffer.from(await $input.first().binary.data).toString('base64');
return {
  remoteJid: $('Function — Extrai argumentos').item.json.remoteJid,
  base64: `data:application/pdf;base64,${base64}`,
  fileName: `relatorio_${$('Function — Extrai argumentos').item.json.nome}.pdf`
};
```

### 7. Evolution API — Enviar PDF

- **Tipo:** HTTP Request
- **Método:** POST
- **URL:** `{{ $env.EVOLUTION_URL }}/message/sendMedia/{{ $env.EVOLUTION_INSTANCE }}`
- **Headers:**
  - `apikey: {{ $env.EVOLUTION_API_KEY }}`
  - `Content-Type: application/json`
- **Body:**
```json
{
  "number": "{{ $json.remoteJid }}",
  "mediatype": "document",
  "fileName": "{{ $json.fileName }}",
  "caption": "📄 Pronto, {{ $('Function — Extrai argumentos').item.json.pushName }}! Segue o relatório.",
  "media": "{{ $json.base64 }}"
}
```

---

## Diagrama visual do Chatbot

```
[Webhook: Evolution messages.upsert]
        │
        ▼
[IF: começa com "relatorio"]
   false → ignora
   true  ↓
        ▼
[Function: extrai nome]
        │
        ▼
[IF: temNome]
   false                          true
    │                               │
    ▼                               ▼
[GET /relatorios]          [POST /relatorios/{nome}/solicitar?formato=pdf]
    │                               │
    ▼                               ▼
[Function: monta lista]     [IF: status 200]
    │                         false       true
    ▼                          │            │
[Evolution sendText]           ▼            ▼
                         [sendText:    [Function:
                          "não          base64]
                          encontrado"]     │
                                          ▼
                                   [Evolution sendMedia
                                    — envia PDF]
```

---

## Comandos suportados pelo Chatbot

| Mensagem | Ação |
|----------|------|
| `relatorio` | Lista relatórios disponíveis |
| `relatorio teste_conexoes` | Gera e envia o PDF do relatório |
| `relatorio vendas` | Gera e envia o PDF (se existir) |

> Expansão futura: `alerta` para forçar verificação de alerta, `help` para ajuda, etc.

---

## Variáveis de ambiente adicionais para o Chatbot

As mesmas do Dispatcher:
- `NEXUS_URL`
- `EVOLUTION_URL`
- `EVOLUTION_INSTANCE`
- `EVOLUTION_API_KEY`

---

## Configuração do Webhook na Evolution API

No painel da Evolution, configure o webhook para apontar para a URL do N8N:

```
URL: https://n8n.empresa.com/webhook/evolution-webhook
Eventos: messages.upsert
```

> Em desenvolvimento local, use ngrok para expor o webhook do N8N:
> ```
> ngrok http 5678
> # URL gerada: https://abc123.ngrok.io
> # Configurar na Evolution: https://abc123.ngrok.io/webhook/evolution-webhook
> ```
