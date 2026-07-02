# Guia — Configurar agendamento

**Problema**: Você precisa configurar quando e para quem um relatório ou alerta deve ser enviado — frequência, horários, canais e destinatários.

---

## 1. Os dois eixos: quem recebe × quando roda

São configurações independentes:

| Eixo | Onde configura | Tabela |
|------|----------------|--------|
| **Quem recebe** (fixos) | Admin Panel → Alertas/Relatórios → Destinatários | `alertas_destinatarios` / `relatorios_destinatarios` |
| **Quem recebe** (dinâmicos) | No processador, extraído do ERP (`contatos_setores`) | — (runtime) |
| **Quando roda** | Admin Panel → Agendamentos, ou `POST /agendamentos` | `agendamentos` |

O agendamento dispara a execução; o orquestrador resolve os destinatários na hora (fixos + extras do agendamento + criador do agendamento).

## 2. Criar agendamento via API

```bash
curl -X POST http://localhost:8099/agendamentos \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": 1,
    "tipo_recurso": "relatorio",
    "recurso_id": 2,
    "frequencia": "diaria",
    "horarios": [{"hora": 7, "minuto": 0}],
    "apenas_dias_uteis": true,
    "timezone": "America/Sao_Paulo",
    "canais": ["whatsapp"],
    "parametros": {"data_inicio": "{{ontem}}"}
  }'
```

Frequências: `diaria` | `semanal` (requer `dia_semana` 1-7) | `mensal` (requer `dia_mes`) | `intervalo` (requer `intervalo_minutos`).

Detalhes de todos os campos: [Agendamentos via API](agendamentos-via-api.md).

## 3. Horários e fuso — como funciona

**Regra única: o horário que você agenda é o horário do `timezone` do agendamento.** Agendou `07:00` com `timezone: America/Sao_Paulo` → dispara às **07:00 de São Paulo**, sempre.

O que acontece por baixo:

```
Você agenda:          07:00 (America/Sao_Paulo)
Banco grava:          proximo_envio = 10:00 UTC        ← sempre UTC no banco
Dispatcher compara:   proximo_envio <= NOW()            ← NOW() também é UTC
Dispara quando:       10:00 UTC = 07:00 em São Paulo ✓
```

| Onde você vê o horário | Fuso exibido |
|------------------------|--------------|
| Coluna `proximo_envio` no banco (SQL direto) | **UTC** (3h à frente de SP) |
| Respostas da API (`GET /agendamentos`) | Fuso do agendamento (ISO com offset, ex: `07:00:00-03:00`) |
| Admin Panel | America/Sao_Paulo |

Se você olhar o banco direto e ver `10:00`, **não está errado** — é o mesmo instante que 07:00 SP. Só o banco fala UTC.

- `timezone` é por agendamento (default `America/Sao_Paulo`). Unidades em outro fuso (ex: `America/Cuiaba`) agendam no fuso delas.
- Horário de verão: `zoneinfo` resolve automaticamente — 07:00 local continua 07:00 local.
- `frequencia: intervalo` ignora horários e fuso: próxima execução = agora + N minutos.

## 4. Cooldown de alertas

O cooldown evita spam e é **por item** (fingerprint SHA256 da linha): o mesmo item não re-notifica dentro da janela; um item novo dispara na hora. Configurado no `config.json` do alerta (`cooldown_minutos`), aplicado via sync.

O cooldown só conta quando alguma entrega foi criada de fato — disparo sem destinatário ou bloqueado por rate limit não entra em cooldown.

Forçar disparo ignorando cooldown e dedup (só para testes manuais):

```bash
curl -X POST "http://localhost:8099/alertas/conexoes_inativas/verificar?forcar=true"
```

## 5. Pausar e reativar

```bash
# Pausar (soft delete)
curl -X DELETE http://localhost:8099/agendamentos/5

# Reativar
curl -X PATCH http://localhost:8099/agendamentos/5 \
  -H "Content-Type: application/json" -d '{"ativo": true}'
```

## 6. Consultar agendamentos

```bash
curl http://localhost:8099/agendamentos            # ativos
curl "http://localhost:8099/agendamentos?apenas_ativos=false"
```

---

**Ver também**:
- [Agendamentos via API](agendamentos-via-api.md) — referência completa dos campos
- [Cadastrar destinatários](cadastrar-destinatarios-agendamentos.md)
- [Referência — Banco de dados](../referencia/banco-de-dados.md)
