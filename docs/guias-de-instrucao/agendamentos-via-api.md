# Cadastrar usuários e agendamentos via API

Guia passo a passo usando endpoints JSON diretos (sem admin panel).

**Base URL:** `http://192.168.1.163:8099`  
**Header obrigatório:** `X-Api-Key: nexus-redecorp-2024`

---

## 1. Criar usuário

```
POST /usuarios
Content-Type: application/json
```

```json
{
  "identificador": "5517991283694",
  "nome": "Lucas Cerqueira",
  "origem": "manual",
  "whatsapp_numero": "5517991283694",
  "email": "lucas@noroaco.com.br",
  "departamento": "TI"
}
```

> `identificador` deve ser único (use o número WhatsApp ou email).  
> `whatsapp_numero`: DDI+DDD+número sem espaços ou símbolos.

**Resposta:**
```json
{ "status": "criado", "id": 20 }
```

Anote o `id` — será o `usuario_id` no agendamento.

---

## 2. Descobrir IDs dos recursos

**Relatórios disponíveis:**
```
GET /relatorios
```

**Alertas disponíveis:**
```
GET /alertas
```

Anote o `id` do recurso desejado.

| Nome | ID atual |
|------|----------|
| `itens_comprimento_por_carga` | 3 |
| `item_comprimento_excedente` (alerta) | 2 |

---

## 3. Criar agendamento de relatório

```
POST /agendamentos
Content-Type: application/json
```

```json
{
  "usuario_id": 20,
  "tipo_recurso": "relatorio",
  "recurso_id": 3,
  "frequencia": "diaria",
  "horarios": [{"hora": 8, "minuto": 0}],
  "apenas_dias_uteis": true,
  "canais": ["whatsapp"],
  "parametros": {},
  "timezone": "America/Sao_Paulo"
}
```

**Opções de frequência:**

| `frequencia` | Campo extra obrigatório | Exemplo |
|---|---|---|
| `diaria` | — | todo dia |
| `semanal` | `"dia_semana": 2` | toda terça (1=seg…7=dom) |
| `mensal` | `"dia_mes": 1` | dia 1 de cada mês |
| `intervalo` | `"intervalo_minutos": 30` | a cada 30 min |

**Múltiplos horários no dia:**
```json
"horarios": [{"hora": 8, "minuto": 0}, {"hora": 18, "minuto": 0}]
```

**Parâmetros com tokens dinâmicos:**
```json
"parametros": {
  "data_inicio": "{{mes_atual_inicio}}",
  "data_fim": "{{hoje}}"
}
```

| Token | Resolve para |
|-------|-------------|
| `{{hoje}}` | Data atual (AAAA-MM-DD) |
| `{{ontem}}` | Ontem |
| `{{mes_atual_inicio}}` | Primeiro dia do mês atual |
| `{{mes_atual_fim}}` | Último dia do mês atual |
| `{{mes_anterior_inicio}}` | Primeiro dia do mês anterior |
| `{{mes_anterior_fim}}` | Último dia do mês anterior |

**Resposta:**
```json
{ "status": "criado", "id": 7, "proximo_envio": "2026-06-30T08:00:00-03:00" }
```

---

## 4. Criar agendamento de alerta

```
POST /agendamentos
Content-Type: application/json
```

```json
{
  "usuario_id": 20,
  "tipo_recurso": "alerta",
  "recurso_id": 2,
  "frequencia": "intervalo",
  "intervalo_minutos": 30,
  "canais": ["whatsapp"],
  "parametros": {}
}
```

> Alertas geralmente usam `frequencia: intervalo` para verificação periódica.  
> O Nexus aplica cooldown e deduplicação automaticamente — sem risco de spam.

---

## 5. Testar imediatamente (sem esperar o cron)

### Relatório

```
POST /relatorios/itens_comprimento_por_carga/solicitar?formato=json&notificar=true&agendamento_id=7
Content-Type: application/json

{ "parametros": {} }
```

> Substitua `agendamento_id=7` pelo ID retornado no passo 3.  
> Com `notificar=true`, o Nexus cria as entregas no banco — o sender n8n entrega em até 1 min.

### Alerta

```
POST /alertas/item_comprimento_excedente/verificar?forcar=true
Content-Type: application/json

{ "parametros": {} }
```

> `forcar=true` ignora cooldown e deduplicação — útil para teste.

---

## 6. Verificar entregas criadas

```
GET /entregas/pendentes?incluir_retry=true
```

Se `total > 0`, as entregas estão na fila e o sender n8n vai processar no próximo ciclo (a cada 1 minuto).

---

## Gerenciar agendamentos

```
GET  /agendamentos               # listar todos
GET  /agendamentos?tipo_recurso=relatorio
PATCH /agendamentos/{id}         # atualizar (enviar só campos alterados)
DELETE /agendamentos/{id}        # desativar (soft delete)
```

**Desativar temporariamente:**
```json
PATCH /agendamentos/7
{ "ativo": false }
```

**Alterar horário:**
```json
PATCH /agendamentos/7
{ "horarios": [{"hora": 7, "minuto": 30}] }
```
