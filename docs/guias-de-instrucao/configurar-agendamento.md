# Guia — Configurar agendamento de alerta

**Problema**: Você precisa configurar quando e para quem um alerta deve ser enviado — frequência, horários, canais e destinatários.

---

## 1. Entenda a tabela de condições

Cada alerta pode ter uma ou mais **condições** na tabela `alertas_condicoes`. Cada condição define:

| Campo | Descrição |
|-------|-----------|
| `alerta_id` | Qual alerta esta condição pertence |
| `nome` | Nome descritivo da condição (ex: "Plantão diurno") |
| `destinatarios` | JSONB com `[{"usuario_id": 1}, {"usuario_id": 2}]` ou `[{"email": "extra@exemplo.com"}]` |
| `canais` | Array: `{whatsapp, email}` |
| `cooldown_minutos` | Tempo mínimo entre disparos |
| `ativo` | `TRUE` = ativa, `FALSE` = pausada |

## 2. Crie uma condição para o alerta

Exemplo: configurar o alerta `conexoes_inativas` para notificar dois usuários por e-mail, com cooldown de 60 minutos:

```sql
INSERT INTO alertas_condicoes (alerta_id, nome, destinatarios, canais, cooldown_minutos)
SELECT
  a.id,
  'Notificar equipe de infra',
  '[{"usuario_id": 1}, {"usuario_id": 2}]'::jsonb,
  ARRAY['email'],
  60
FROM alertas a
WHERE a.nome = 'conexoes_inativas';
```

## 3. Crie uma condição com múltiplos canais

Condição que notifica por e-mail e WhatsApp:

```sql
INSERT INTO alertas_condicoes (alerta_id, nome, destinatarios, canais, cooldown_minutos)
SELECT
  a.id,
  'Notificar geral',
  '[{"usuario_id": 1}]'::jsonb,
  ARRAY['email', 'whatsapp'],
  120
FROM alertas a
WHERE a.nome = 'conexoes_inativas';
```

## 4. Destinatários fixos vs. dinâmicos

O Nexus suporta dois tipos de destinatários:

### Fixos (tabela `usuarios`)

Referenciados por `usuario_id`. O sistema busca automaticamente nome, e-mail e WhatsApp:

```json
[{"usuario_id": 1}, {"usuario_id": 3}]
```

### Externos (e-mail direto)

Para destinatários que não estão cadastrados no Nexus:

```json
[{"email": "alerta@empresa.com"}]
```

## 5. Entenda o cooldown

O cooldown evita spam. Se um alerta disparou às 10:00 com cooldown de 60 minutos, ele não disparará novamente até as 11:00, mesmo que a condição ainda seja verdadeira.

Para forçar um disparo ignorando o cooldown (útil em testes):

```bash
curl -X POST "http://localhost:8000/alertas/conexoes_inativas/verificar?forcar=true"
```

## 6. Pausar uma condição

```sql
UPDATE alertas_condicoes
SET ativo = FALSE
WHERE nome = 'Notificar equipe de infra';
```

Reativar:

```sql
UPDATE alertas_condicoes
SET ativo = TRUE
WHERE nome = 'Notificar equipe de infra';
```

## 7. Consultar condições existentes

```sql
SELECT
  ac.id,
  ac.nome AS condicao,
  a.nome AS alerta,
  ac.canais,
  ac.cooldown_minutos,
  ac.ultimo_disparo,
  ac.ativo
FROM alertas_condicoes ac
JOIN alertas a ON a.id = ac.alerta_id
ORDER BY a.nome, ac.nome;
```

---

**Ver também**:
- [Referência — Banco de dados](../referencia/banco-de-dados.md) — esquema da tabela `alertas_condicoes`
- [Explicação — Renderização de mensagens](../explicacao/renderizacao-mensagens.md)
