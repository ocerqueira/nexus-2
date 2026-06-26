# Configurar chatbot WhatsApp (Evolution API + n8n)

Ativa o chatbot interativo para que usuários consultem relatórios e alertas pelo WhatsApp digitando *menu*.

---

## Pré-requisitos

- Evolution API rodando com uma instância conectada (QR escaneado)
- n8n configurado com o `nexus_despachos_sender` já ativo
- Nexus rodando e acessível pela rede do n8n
- Variáveis de ambiente do n8n disponíveis (`$env.*`)

---

## Parte 1 — n8n: importar o workflow

### Passo 1 — Importar

No n8n: **Workflows → Import from file** → selecione `docs/n8n/nexus_chatbot.json`.

### Passo 2 — Configurar variáveis de ambiente

O workflow lê as credenciais via `$env.*`. Configure no n8n em **Settings → Environment Variables**:

| Variável | Exemplo | Descrição |
|----------|---------|-----------|
| `NEXUS_URL` | `http://192.168.1.100:8099` | URL base do Nexus (sem barra final) |
| `NEXUS_API_KEY` | `sua_chave_aqui` | Chave em `X-Api-Key` |
| `EVOLUTION_URL` | `https://api.evolution.com` | URL base da Evolution API (sem barra final) |
| `EVOLUTION_INSTANCE` | `minha_instancia` | Nome da instância no Evolution |
| `EVOLUTION_API_KEY` | `sua_chave_evolution` | API key da Evolution API |

> Se preferir não usar variáveis de ambiente, edite os campos diretamente nos nós HTTP Request do workflow.

### Passo 3 — Obter a URL do webhook

1. Abra o workflow importado
2. Clique no nó **Webhook — Evolution messages.upsert**
3. Copie a **Test URL** (para testes) ou a **Production URL** (para uso real)

O path será: `.../webhook/nexus-chatbot`

### Passo 4 — Ativar o workflow

Clique em **Activate** (canto superior direito). O webhook só responde com o workflow ativo.

---

## Parte 2 — Evolution API: configurar webhook

### Passo 1 — Acessar o painel da instância

No Evolution Manager ou via API, abra a instância que receberá as mensagens.

### Passo 2 — Configurar o webhook

Via API (recomendado):

```
POST {EVOLUTION_URL}/webhook/set/{INSTANCE_NAME}
Header: apikey: {EVOLUTION_API_KEY}
Content-Type: application/json

{
  "webhook": {
    "enabled": true,
    "url": "{N8N_WEBHOOK_URL}",
    "webhookByEvents": false,
    "webhookBase64": false,
    "events": ["MESSAGES_UPSERT"]
  }
}
```

Substitua `{N8N_WEBHOOK_URL}` pela URL copiada no Passo 3 acima.

**Atenção:** `webhookBase64: false` — o Nexus chatbot não usa base64 no webhook de entrada.

### Passo 3 — Verificar

```
GET {EVOLUTION_URL}/webhook/find/{INSTANCE_NAME}
Header: apikey: {EVOLUTION_API_KEY}
```

Resposta esperada: `"enabled": true` e `"url"` apontando para o n8n.

---

## Parte 3 — Testar o fluxo

### Teste básico

1. Envie qualquer mensagem para o número conectado à instância
2. O Evolution encaminha para o n8n via webhook
3. O n8n processa e responde com o menu principal (lista interativa)

### Fluxo esperado

```
Usuário: "oi"
Bot: [Lista] Nexus — Sistema ERP
     📊 Relatórios: Pedidos por Vendedor
     🚨 Alertas: Comprimento Excedente
     ❓ Ajuda

Usuário: [seleciona Pedidos por Vendedor]
Bot: [Lista] Período — pedidos por vendedor
     ⚡ Este mês / Mês passado / 30 dias / Trimestre
     🗓️ Período personalizado

Usuário: [seleciona Este mês]
Bot: [PDF] pedidos_por_vendedor.pdf + legenda com período
```

### Comandos especiais

| Entrada | Comportamento |
|---------|---------------|
| `menu` (qualquer momento) | Volta ao menu principal |
| `0` | Volta ao menu principal |
| Período personalizado | Pede data início → data fim (DD/MM/YYYY) |

---

## Resolução de problemas

### Mensagem não chega no n8n

- Confirme que o workflow está **ativo** (não apenas salvo)
- Verifique a URL do webhook: deve ser Production URL, não Test URL
- Teste o webhook manualmente: `POST {N8N_WEBHOOK_URL}` com body `{}`

### n8n recebe mas não responde

- Abra a execução com erro no n8n (Executions → abrir a falha)
- Erro 401 nos nós HTTP → `NEXUS_API_KEY` incorreta ou não configurada
- Erro 401 nos nós Evolution → `EVOLUTION_API_KEY` incorreta
- Erro de conexão → `NEXUS_URL` ou `EVOLUTION_URL` incorreta

### Sessão não persiste entre mensagens

O estado do chatbot fica na tabela `chatbot_sessoes` no PostgreSQL do Nexus.
Verifique: `GET /chatbot/sessao/{numero}` deve retornar o estado atual.
Se retornar erro 500 → a tabela pode não existir; rode as migrations do banco.

### Menu não aparece (sendList rejeitado)

A Evolution API `sendList` exige que o número seja do tipo Business (WABA) ou que o número destino suporte listas interativas. Se o WhatsApp retornar erro, o tipo de conta pode não suportar listas.

---

## Adicionar novos relatórios/alertas ao menu

O menu está definido no nó **Code — build menu principal** do workflow n8n.

Para adicionar um relatório:
```javascript
{ rowId: 'rel_nome_do_relatorio', title: 'Título Exibido', description: 'Descrição curta' }
```

Para adicionar um alerta:
```javascript
{ rowId: 'alerta_nome_do_alerta', title: 'Título Exibido', description: 'Descrição curta' }
```

O prefixo `rel_` / `alerta_` é obrigatório — o state machine usa para identificar o tipo e chamar o endpoint correto no Nexus.
