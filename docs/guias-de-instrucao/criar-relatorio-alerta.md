# Criar novo relatório ou alerta — passo a passo

Do zero até o primeiro envio: estrutura de arquivos, cadastro no banco, destinatários e agendamento.

---

## Parte 1 — Novo relatório

### Estrutura de arquivos

```
app/relatorios/
└── nome_do_relatorio/
    ├── config.json       ← metadados e parâmetros aceitos
    ├── consultas.sql     ← queries nomeadas (-- name:)
    ├── processador.py    ← lógica de busca e transformação
    └── template.html     ← layout do PDF (Jinja2 + WeasyPrint)
```

---

### Passo 1 — `config.json`

```json
{
  "titulo": "Nome Exibido no Relatório",
  "descricao": "O que este relatório mostra.",
  "categoria": "comercial",
  "parametros": [
    {
      "nome": "data_inicio",
      "tipo": "date",
      "obrigatorio": false,
      "padrao": null,
      "rotulo": "Data de início (AAAA-MM-DD)"
    },
    {
      "nome": "data_fim",
      "tipo": "date",
      "obrigatorio": false,
      "padrao": null,
      "rotulo": "Data de fim (AAAA-MM-DD)"
    }
  ]
}
```

---

### Passo 2 — `consultas.sql`

Cada query começa com `-- name:` (só ASCII — o driver Firebird rejeita acentos em comentários).

```sql
-- name: buscar_dados_principais
SELECT
    campo1,
    campo2
FROM tabela
WHERE data_campo BETWEEN :data_inicio AND :data_fim
  AND cod_empresa = :cod_empresa
ORDER BY campo1;
```

---

### Passo 3 — `processador.py`

Interface obrigatória: `validar()` e `buscar_dados()`.

```python
"""Processador do relatório: nome_do_relatorio"""

from pathlib import Path
from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO = "erp_firebird"   # nome cadastrado em conexoes_bd


class ProcessadorNomeDoRelatorio:

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        if not parametros.get("data_inicio"):
            return False, "Parâmetro 'data_inicio' é obrigatório"
        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict:
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=carregar_query(ARQUIVO_CONSULTAS, "buscar_dados_principais"),
            parametros={
                "data_inicio": parametros["data_inicio"],
                "data_fim":    parametros.get("data_fim", parametros["data_inicio"]),
                "cod_empresa": parametros.get("cod_empresa", 1),
            },
        )

        return {
            "total": len(linhas),
            "linhas": linhas,
            "resumo": f"{len(linhas)} registros encontrados",
        }
```

> **Importante:** o nome da classe deve começar com `Processador` (ex: `ProcessadorVendasDiarias`).
> O Nexus descobre a classe automaticamente — sem alterar nenhum arquivo de rotas.

---

### Passo 4 — `template.html`

Herda do base e usa Jinja2 para renderizar os dados:

```html
{% extends "base.html" %}

{% block conteudo %}
<h1>{{ titulo }}</h1>
<p>Período: {{ parametros.data_inicio }} a {{ parametros.data_fim }}</p>

<table>
  <thead>
    <tr><th>Campo 1</th><th>Campo 2</th></tr>
  </thead>
  <tbody>
    {% for linha in linhas %}
    <tr>
      <td>{{ linha.campo1 }}</td>
      <td>{{ linha.campo2 }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

---

### Passo 5 — Registrar no banco

```
POST /sincronizar
Header: X-Api-Key: <chave>
```

Isso descobre todos os relatórios e alertas novos em `app/relatorios/` e `app/alertas/` e os insere na tabela `relatorios`.

Verificar: `GET /relatorios` — o novo deve aparecer com `status: ativo`.

---

### Passo 6 — Testar localmente

```
POST /relatorios/nome_do_relatorio/solicitar?formato=pdf
Header: X-Api-Key: <chave>
Body:
{
  "parametros": {
    "data_inicio": "2025-01-01",
    "data_fim":    "2025-01-31"
  }
}
```

Retorna o PDF como binário. Abra no navegador para validar layout.

---

### Passo 7 — Configurar destinatários fixos

Ver [Cadastrar destinatários e agendamentos](cadastrar-destinatarios-agendamentos.md) — Passos 1 a 3.

```
POST /admin/relatorios/{relatorio_id}/destinatarios
  usuario_id:       <id>
  canais:           whatsapp
  formato_whatsapp: documento
```

---

### Passo 8 — Criar agendamento

```
POST /admin/agendamentos
  tipo:         relatorio
  recurso_nome: nome_do_relatorio
  usuario_id:   <id do criador>
  canais:       whatsapp
  cron:         0 7 * * *
  parametros:   {"data_inicio":"{{mes_atual_inicio}}","data_fim":"{{hoje}}"}
```

---

## Parte 2 — Novo alerta

### Estrutura de arquivos

```
app/alertas/
└── nome_do_alerta/
    ├── config.json       ← metadados, severidade, parâmetros
    ├── consultas.sql     ← queries nomeadas
    ├── processador.py    ← lógica de detecção
    └── mensagens/
        ├── whatsapp.j2   ← template da mensagem WhatsApp (Jinja2)
        └── email.html.j2 ← template do e-mail (opcional)
```

---

### Passo 1 — `config.json`

```json
{
  "titulo": "Nome do Alerta",
  "descricao": "O que este alerta detecta.",
  "severidade": "critico",
  "parametros": [
    {
      "nome": "data_inicio",
      "tipo": "date",
      "obrigatorio": false,
      "padrao": null,
      "rotulo": "Data de início. Padrão: 3 dias atrás."
    }
  ]
}
```

`severidade`: `critico` | `aviso` | `info`

---

### Passo 2 — `consultas.sql`

```sql
-- name: detectar_ocorrencias
SELECT
    campo_chave,
    descricao,
    data_evento
FROM tabela_erp
WHERE data_evento >= :data_inicio
  AND cod_empresa = :cod_empresa
ORDER BY data_evento DESC;
```

---

### Passo 3 — `processador.py`

Interface obrigatória: `validar()` e `verificar()`.

```python
"""Processador do alerta: nome_do_alerta"""

import hashlib, json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO = "erp_firebird"


class ProcessadorNomeDoAlerta:

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        return True, ""

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        data_inicio = parametros.get("data_inicio") or (
            date.today() - timedelta(days=3)
        ).isoformat()

        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=carregar_query(ARQUIVO_CONSULTAS, "detectar_ocorrencias"),
            parametros={"data_inicio": data_inicio, "cod_empresa": parametros.get("cod_empresa", 1)},
        )

        if not linhas:
            return {
                "encontrou_dados": False,
                "total": 0,
                "resumo": "Nenhuma ocorrência encontrada",
                "dados": [],
                "contatos_setores": [],
                "estatisticas": {},
            }

        total = len(linhas)

        # Fingerprint: identidade dos dados — Nexus usa para deduplicação
        chaves = sorted((str(r.get("campo_chave", "")),) for r in linhas)
        fingerprint = hashlib.sha256(json.dumps(chaves).encode()).hexdigest()

        return {
            "encontrou_dados": True,
            "total": total,
            "resumo": f"{total} ocorrência(s) detectada(s)",
            "dados": linhas,
            "contatos_setores": [],  # preencher com telefones do ERP se necessário
            "fingerprint": fingerprint,
            "estatisticas": {"total": total},
        }
```

**`contatos_setores`**: lista de `{"nome": "...", "whatsapp": "55DD...", "setor": "..."}` extraída do ERP.
Esses números recebem o alerta automaticamente, sem cadastro no Nexus.

---

### Passo 4 — Template de mensagem

`mensagens/whatsapp.j2`:

```
*⚠ {{ titulo }}*

{{ resumo }}

{% for item in dados[:10] %}
• {{ item.campo_chave }} — {{ item.descricao }}
{% endfor %}
{% if dados|length > 10 %}
_... e mais {{ dados|length - 10 }} ocorrência(s)_
{% endif %}
```

---

### Passo 5 — Registrar e testar

```
POST /sincronizar
```

Testar com `forcar=true` para ignorar cooldown:

```
POST /alertas/nome_do_alerta/verificar?forcar=true
Header: X-Api-Key: <chave>
Body: {"parametros": {"data_inicio": "2025-01-01"}}
```

Verificar entregas criados: `GET /entregas/pendentes`

---

### Passo 6 — Adicionar destinatários fixos ao alerta

```
POST /admin/alertas/{alerta_id}/destinatarios
  usuario_id:     <id>
  canais:         whatsapp
  modo_mensagem:  consolidado   ← resumo geral | individual = uma msg por item
  limite_hora:    5             ← opcional
  limite_dia:     20            ← opcional
```

---

### Passo 7 — Configurar cooldown

```
POST /admin/alertas/{alerta_id}/cooldown
  cooldown_minutos: 60
```

---

## Referência rápida

| Etapa | Relatório | Alerta |
|-------|-----------|--------|
| Pasta | `app/relatorios/nome/` | `app/alertas/nome/` |
| Interface obrigatória | `validar()` + `buscar_dados()` | `validar()` + `verificar()` |
| Registrar no banco | `POST /sincronizar` | `POST /sincronizar` |
| Testar | `POST /solicitar?formato=pdf` | `POST /verificar?forcar=true` |
| Destinatários fixos | `POST /admin/relatorios/{id}/destinatarios` | `POST /admin/alertas/{id}/destinatarios` |
| Destinatários dinâmicos | — | `contatos_setores` no processador |
| Agendar | `POST /admin/agendamentos` (tipo=relatorio) | `POST /admin/agendamentos` (tipo=alerta) |
| Disparar manualmente | `?notificar=true` | `?forcar=true` para ignorar cooldown |
