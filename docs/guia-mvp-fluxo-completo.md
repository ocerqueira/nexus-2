# Guia MVP — Fluxo Completo

Cobre: conexão BD → usuário → permissão → relatório/alerta → agendamento → n8n.

---

## 1. Subir a API

### Dev local (recomendado)

```bash
make dev-build   # primeira vez
make dev         # subir sem rebuild
```

API em `http://localhost:8099` | Docs em `http://localhost:8099/docs`

### Produção

```bash
make prod-build
```

Ver [guia de deploy](../deploy.md) para configuração completa.

---

## 2. Cadastrar conexão ao ERP

```http
POST /conexoes
X-Api-Key: nexus-redecorp-2024
Content-Type: application/json

{
  "nome": "erp_principal",
  "tipo": "firebird",
  "host": "192.168.1.10",
  "porta": 3050,
  "banco": "/dados/empresa.fdb",
  "usuario": "SYSDBA",
  "senha": "masterkey"
}
```

Resposta: `{ "status": "criada", "id": 1 }` → guarda o `id`.

---

## 3. Cadastrar usuário

```http
POST /usuarios
Content-Type: application/json

{
  "identificador": "5511999990001",
  "nome": "Lucas",
  "origem": "whatsapp",
  "whatsapp_numero": "5511999990001"
}
```

Resposta: `{ "status": "criado", "id": 1 }` → guarda o `id`.

---

## 4. Ver recursos disponíveis

```http
GET /relatorios
GET /alertas
```

Retorna IDs de banco dos recursos — necessários para permissão e agendamento.

> **Importante:** `recurso_id` em permissões/agendamentos é o `id` das tabelas
> `relatorios`/`alertas`, não o nome em texto.

---

## 5. Conceder permissão

### Para relatório

```http
POST /permissoes
Content-Type: application/json

{
  "usuario_id": 1,
  "tipo_recurso": "relatorio",
  "recurso_id": 1,
  "pode_solicitar": true,
  "pode_agendar": true,
  "limite_diario": 10
}
```

### Para alerta

```http
POST /permissoes
Content-Type: application/json

{
  "usuario_id": 1,
  "tipo_recurso": "alerta",
  "recurso_id": 1,
  "pode_solicitar": true,
  "pode_agendar": true
}
```

### Verificar permissão (endpoint para n8n)

```http
GET /permissoes/verificar?usuario_id=1&tipo_recurso=relatorio&recurso_id=1
```

---

## 6. Testar relatório

```http
POST /relatorios/pedidos_por_vendedor/solicitar?formato=html
Content-Type: application/json

{}
```

Formatos disponíveis: `json` | `html` | `pdf`

Relatórios disponíveis (ver `/relatorios`):
- `pedidos_por_vendedor`
- `desempenho_vendas`
- `dashboard_conexoes`
- `itens_comprimento_por_carga`

---

## 7. Testar alerta

```http
POST /alertas/conexoes_inativas/verificar
Content-Type: application/json

{}
```

Parâmetro `?forcar=true` ignora cooldown.

Alertas disponíveis (ver `/alertas`):
- `conexoes_inativas`
- `item_comprimento_excedente`

Resposta inclui `deve_notificar: true/false` e lista de despachos criados.

---

## 8. Criar agendamento

```http
POST /agendamentos
Content-Type: application/json

{
  "usuario_id": 1,
  "tipo_recurso": "relatorio",
  "recurso_id": 1,
  "frequencia": "diaria",
  "horarios": [{"hora": 8, "minuto": 0}],
  "apenas_dias_uteis": true,
  "canais": ["whatsapp"],
  "parametros": {}
}
```

Frequências: `diaria` | `semanal` (requer `dia_semana` 1-7) | `mensal` (requer `dia_mes` 1-31) | `intervalo` (requer `intervalo_minutos`)

---

## 9. Fluxo n8n

### Polling (Cron a cada 1 minuto)

```http
GET /agendamentos/proximas-execucoes
```

Retorna agendamentos prontos para executar. Tolerância de 60 min de atraso — se passou mais, recalcula e pula.

### Executar e marcar

```
Para cada agendamento retornado:
  1. Se tipo_recurso = "relatorio":
       POST /relatorios/{recurso_nome}/solicitar?formato=html
  2. Se tipo_recurso = "alerta":
       POST /alertas/{recurso_nome}/verificar
  3. Envia resultado via WhatsApp/email
  4. POST /agendamentos/{id}/marcar-executado
```

### Chatbot WhatsApp (estado de sessão)

```http
GET  /chatbot/sessao/{numero}   # busca estado atual
PUT  /chatbot/sessao/{numero}   # salva novo estado
DELETE /chatbot/sessao/{numero} # reseta sessão
```

### Buscar usuário pelo número (n8n)

```http
GET /usuarios/whatsapp/5511999990001
```

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DATABASE_URL` | `postgresql+psycopg://nexus_admin:nexus_dev_2024@localhost:55432/nexus` | Postgres do Nexus (dev: porta 5433 no host, configurado no `.env.local`) |
| `CHAVE_CRIPTOGRAFIA` | chave dev | Fernet — trocar em produção, **não trocar após cadastrar conexões** |
| `AMBIENTE` | `desenvolvimento` | `producao` desativa debug |
| `DEBUG` | `true` | Loga SQL quando true |
| `API_KEY` | `nexus-redecorp-2024` (dev) | Chave de autenticação enviada no header `X-Api-Key` |
