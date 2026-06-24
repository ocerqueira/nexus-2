# Tutorial — Criando um novo relatório

**Objetivo**: Criar um relatório do zero com `config.json`, `consultas.sql`, `processador.py` e `template.html`.

**Pré-requisitos**: Nexus em execução (veja [Primeira execução](primeira-execucao.md)).

---

## Cenário

Vamos criar `resumo_usuarios`, que lista usuários do banco interno do Nexus.

## 1. Crie a pasta

```bash
mkdir -p app/relatorios/resumo_usuarios
```

## 2. `config.json`

```json
{
  "titulo": "Resumo de Usuários",
  "descricao": "Lista todos os usuários cadastrados no Nexus com seus dados de contato",
  "parametros": [
    {
      "nome": "apenas_ativos",
      "tipo": "boolean",
      "obrigatorio": false,
      "padrao": true,
      "rotulo": "Listar apenas usuários ativos?"
    },
    {
      "nome": "departamento",
      "tipo": "string",
      "obrigatorio": false,
      "rotulo": "Filtrar por departamento"
    }
  ]
}
```

## 3. `consultas.sql`

Cada query é identificada com `-- name:`. O `carregador_sql` extrai por nome:

```sql
-- name: listar_apenas_ativos
SELECT id, nome, email, whatsapp_numero, departamento, cargo
FROM usuarios
WHERE ativo = TRUE
ORDER BY nome;

-- name: filtrar_por_departamento
SELECT id, nome, email, whatsapp_numero, departamento, cargo, ativo
FROM usuarios
WHERE departamento = :departamento
ORDER BY nome;
```

> **Atenção Firebird**: comentários devem ser ASCII-only — o driver cp1252 rejeita
> caracteres Unicode (`═══`, `—`, `ã`, etc.) dentro de `--` comentários.
> Use apenas letras sem acento nos comentários SQL.

## 4. `processador.py`

Interface obrigatória: `validar()` e `buscar_dados()`.

```python
"""Processador do relatório: resumo_usuarios"""

from pathlib import Path
from typing import Any

from app.bd import engine
from app.core.carregador_sql import carregar_query
from sqlalchemy import text

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"


class ProcessadorResumoUsuarios:

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        if "apenas_ativos" in parametros:
            if not isinstance(parametros["apenas_ativos"], bool):
                return False, "'apenas_ativos' deve ser true ou false"
        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        apenas_ativos = parametros.get("apenas_ativos", True)
        departamento = parametros.get("departamento")

        if departamento:
            query = carregar_query(ARQUIVO_CONSULTAS, "filtrar_por_departamento")
            params = {"departamento": departamento}
        else:
            query = carregar_query(ARQUIVO_CONSULTAS, "listar_apenas_ativos")
            params = {}

        with engine.connect() as conexao:
            usuarios = [dict(r) for r in conexao.execute(text(query), params).mappings()]

        return {"total": len(usuarios), "usuarios": usuarios}
```

> Este processador usa `engine` (banco interno do Nexus) diretamente.
> Para ERP Firebird use `gerenciador_conexoes` — veja seção [Multi-banco](#multi-banco-erp-firebird).

## 5. `template.html`

```html
{% extends "base.html" %}

{% block conteudo %}
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-valor">{{ total }}</div>
    <div class="kpi-label">Usuários</div>
  </div>
</div>

{% if usuarios %}
<table>
  <thead>
    <tr><th>Nome</th><th>E-mail</th><th>WhatsApp</th><th>Departamento</th></tr>
  </thead>
  <tbody>
    {% for u in usuarios %}
    <tr>
      <td><strong>{{ u.nome }}</strong></td>
      <td>{{ u.email or "—" }}</td>
      <td>{{ u.whatsapp_numero or "—" }}</td>
      <td>{{ u.departamento or "—" }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p style="color:#9ca3af;font-style:italic">Nenhum usuário encontrado.</p>
{% endif %}
{% endblock %}
```

## 6. Registre em `app/rotas/relatorios.py`

```python
from app.relatorios.resumo_usuarios.processador import ProcessadorResumoUsuarios

PROCESSADORES = {
    # ... existentes ...
    "resumo_usuarios": {
        "classe": ProcessadorResumoUsuarios,
        "titulo": "Resumo de Usuários",
        "subtitulo": "Usuários cadastrados no sistema",
    },
}
```

## 7. Sincronize e teste

```bash
curl -X POST http://localhost:8000/sincronizar

# JSON
curl -X POST http://localhost:8000/relatorios/resumo_usuarios/solicitar \
  -H "Content-Type: application/json" -d '{}'

# HTML (abrir no browser)
curl http://localhost:8000/relatorios/resumo_usuarios/solicitar?formato=html

# PDF download
curl -O relatorio.pdf \
  "http://localhost:8000/relatorios/resumo_usuarios/solicitar?formato=pdf"
```

---

## Tópicos avançados

### Parâmetros de data — três padrões

Escolha o padrão conforme o tipo de relatório:

---

#### Padrão A — Datas obrigatórias (relatório histórico)

Adequado quando o usuário precisa definir explicitamente o período — ex: relatório de vendas mensal.

`config.json`:
```json
{
  "parametros": [
    { "nome": "data_inicio", "tipo": "date", "obrigatorio": true,  "rotulo": "Data de início (AAAA-MM-DD)" },
    { "nome": "data_fim",    "tipo": "date", "obrigatorio": true,  "rotulo": "Data de fim (AAAA-MM-DD)" }
  ]
}
```

`validar()`:
```python
from datetime import datetime

@staticmethod
def validar(parametros: dict) -> tuple[bool, str]:
    for campo in ("data_inicio", "data_fim"):
        valor = parametros.get(campo)
        if not valor:
            return False, f"'{campo}' é obrigatório (AAAA-MM-DD)"
        try:
            datetime.strptime(str(valor), "%Y-%m-%d")
        except ValueError:
            return False, f"'{campo}' deve estar no formato AAAA-MM-DD"
    if parametros["data_inicio"] > parametros["data_fim"]:
        return False, "'data_inicio' não pode ser posterior a 'data_fim'"
    return True, ""
```

Chamada:
```bash
curl -X POST http://localhost:8000/relatorios/meu_relatorio/solicitar \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"data_inicio": "2025-01-01", "data_fim": "2025-01-31"}}'
```

---

#### Padrão B — Datas opcionais com default calculado (relatório executivo)

Adequado quando há um período padrão conveniente — ex: "mês atual" ou "últimos 30 dias".

`config.json`:
```json
{
  "parametros": [
    { "nome": "data_inicio", "tipo": "date", "obrigatorio": false, "padrao": null, "rotulo": "Início (AAAA-MM-DD). Padrão: 1º dia do mês atual." },
    { "nome": "data_fim",    "tipo": "date", "obrigatorio": false, "padrao": null, "rotulo": "Fim (AAAA-MM-DD). Padrão: hoje." }
  ]
}
```

`validar()`:
```python
@staticmethod
def validar(parametros: dict) -> tuple[bool, str]:
    for campo in ("data_inicio", "data_fim"):
        valor = parametros.get(campo)
        if valor:
            try:
                datetime.strptime(str(valor), "%Y-%m-%d")
            except ValueError:
                return False, f"'{campo}' deve estar no formato AAAA-MM-DD"
    return True, ""
```

`buscar_dados()`:
```python
from datetime import date

@staticmethod
def buscar_dados(parametros: dict) -> dict:
    hoje = date.today()
    data_inicio = parametros.get("data_inicio") or hoje.replace(day=1).isoformat()
    data_fim    = parametros.get("data_fim")    or hoje.isoformat()
    ...
```

---

#### Padrão C — Dia útil anterior automático (relatório diário agendado)

Adequado para relatórios que rodam toda manhã via N8N sem parâmetros.
O processador calcula sozinho o dia útil anterior (seg → sex, seg → sex, feriados não tratados automaticamente).

`config.json`:
```json
{
  "parametros": [
    { "nome": "data_inicio", "tipo": "date", "obrigatorio": false, "padrao": null, "rotulo": "Data (AAAA-MM-DD). Padrão: dia útil anterior." },
    { "nome": "data_fim",    "tipo": "date", "obrigatorio": false, "padrao": null, "rotulo": "Data fim. Padrão: igual a data_inicio (mesmo dia)." }
  ]
}
```

`processador.py`:
```python
from datetime import date, timedelta

def _dia_util_anterior(referencia: date | None = None) -> date:
    d = (referencia or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:   # 5=sábado, 6=domingo
        d -= timedelta(days=1)
    return d

@staticmethod
def buscar_dados(parametros: dict) -> dict:
    data_inicio = parametros.get("data_inicio") or _dia_util_anterior().isoformat()
    data_fim    = parametros.get("data_fim")    or data_inicio   # mesmo dia por padrão

    dados = gerenciador_conexoes.executar(
        conexao=CONEXAO_ERP,
        query=carregar_query(ARQUIVO_CONSULTAS, "minha_query"),
        parametros={"data_inicio": data_inicio, "data_fim": data_fim, "cod_empresa": 1},
    )
    return {"dados": dados, "periodo": f"{data_inicio} a {data_fim}"}
```

Agendamento no N8N: chamar sem body `{}` — o processador resolve o período sozinho.

---

### Data de evento vs data de pedido (Firebird ERP)

Em relatórios que cruzam pedidos (`ARQES13`) com cargas (`VD_CARGA`) existem duas datas:

| Campo | Tabela | Quando usar |
|---|---|---|
| `p.DATA` | `ARQES13` | Data em que o pedido foi feito — relatórios comerciais/vendas |
| `c.DT_SAIDA` | `VD_CARGA` | Data em que a carga saiu do estoque — relatórios operacionais/logísticos |

Para relatório diário de cargas expedidas: filtrar por `c.DT_SAIDA`.
Para relatório de pedidos por período: filtrar por `p.DATA`.

```sql
-- name: cargas_expedidas
-- Filtra pela data de saida da carga (operacional)
SELECT ...
FROM VD_CARGA c
JOIN ...
WHERE c.DT_SAIDA >= :data_inicio
  AND c.DT_SAIDA <= :data_fim
  AND c.cod_empresa = :cod_empresa

-- name: pedidos_por_periodo
-- Filtra pela data do pedido (comercial)
SELECT ...
FROM ARQES13 p
WHERE p.DATA >= :data_inicio
  AND p.DATA <= :data_fim
  AND p.cod_empresa = :cod_empresa
```

---

### Multi-banco (ERP Firebird)

Para relatórios que buscam dados do ERP Firebird:

```python
from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "erp_firebird"

@staticmethod
def buscar_dados(parametros: dict) -> dict:
    dados = gerenciador_conexoes.executar(
        conexao=CONEXAO_ERP,
        query=carregar_query(ARQUIVO_CONSULTAS, "minha_query"),
        parametros={
            "data_inicio": parametros["data_inicio"],
            "data_fim":    parametros["data_fim"],
            "cod_empresa": parametros.get("cod_empresa", 1),
        },
    )
    return {"total": len(dados), "dados": dados}
```

A conexão `erp_firebird` deve estar cadastrada em `conexoes_bd`. Verificar:

```bash
curl http://localhost:8000/conexoes/erp_firebird/testar
```

**Limitações Firebird a observar no SQL:**

| Problema | Causa | Solução |
|---|---|---|
| `UnicodeEncodeError cp1252` | Comentário `--` com Unicode (`═`,`—`,`ã`) | Usar só ASCII nos comentários |
| `invalid ORDER BY clause` em UNION | Alias de coluna não aceito no ORDER BY | Usar posição: `ORDER BY 1, 5, 6` |
| `SELECT 1` inválido | Firebird exige FROM | `SELECT 1 FROM RDB$DATABASE` |
| Parâmetros | Sintaxe SQLAlchemy | `:nome_param` (dois-pontos, sem espaço) |

---

### Relatório combinando ERP + banco interno

Quando o relatório precisa de dados do ERP e também do banco interno do Nexus (ex: buscar pedidos no Firebird e metas/config no PostgreSQL):

```python
from app.bd import engine
from app.core.gerenciador_conexoes import gerenciador_conexoes
from sqlalchemy import text

@staticmethod
def buscar_dados(parametros: dict) -> dict:
    # 1. ERP Firebird
    pedidos = gerenciador_conexoes.executar(
        conexao="erp_firebird",
        query=carregar_query(ARQUIVO_CONSULTAS, "buscar_pedidos"),
        parametros={"data_inicio": parametros["data_inicio"]},
    )

    # 2. Configurações no banco interno do Nexus (PostgreSQL)
    with engine.connect() as conn:
        config = [dict(r) for r in conn.execute(
            text("SELECT * FROM minha_tabela_config WHERE cod_empresa = :cod"),
            {"cod": parametros.get("cod_empresa", 1)},
        ).mappings()]

    return {"pedidos": pedidos, "config": config}
```

---

## Resumo

| Arquivo | Função |
|---|---|
| `config.json` | Metadados e declaração de parâmetros |
| `consultas.sql` | Queries com `-- name:` (ASCII-only nos comentários) |
| `processador.py` | `validar()` + `buscar_dados()` |
| `template.html` | Jinja2 `{% extends "base.html" %}` |

Registrar em `PROCESSADORES` em `app/rotas/relatorios.py` é o único toque em código existente.
Chamar `POST /sincronizar` após criar a pasta faz o banco reconhecer o novo relatório.

**Padrão de data a escolher:**

| Tipo de relatório | Padrão |
|---|---|
| Histórico (usuário define período) | A — datas obrigatórias |
| Executivo (período corrente como default) | B — datas opcionais com default calculado |
| Diário agendado (sem interação) | C — dia útil anterior automático |
