# Tutorial — Criando um novo alerta

**Objetivo**: Criar um alerta completo com `config.json`, `consultas.sql`, `processador.py` e templates de mensagens.

**Pré-requisitos**: Nexus em execução (veja [Primeira execução](primeira-execucao.md)).

---

## Cenário

Vamos criar `conexoes_sem_grupo`, que detecta conexões no Nexus sem grupo lógico definido.

## 1. Crie a pasta

```bash
mkdir -p app/alertas/conexoes_sem_grupo/mensagens
```

## 2. `config.json`

```json
{
  "titulo": "Conexões sem Grupo",
  "descricao": "Detecta conexões de banco que não estão vinculadas a nenhum grupo lógico",
  "severidade": "aviso",
  "parametros": []
}
```

## 3. `consultas.sql`

```sql
-- name: verificar_conexoes_sem_grupo
SELECT c.id, c.nome, c.tipo, c.host, c.porta, c.banco
FROM conexoes_bd c
LEFT JOIN grupos_conexoes_itens gi ON gi.conexao_id = c.id
WHERE gi.conexao_id IS NULL AND c.ativo = TRUE
ORDER BY c.nome;
```

> **Atenção Firebird**: comentários `--` devem ser ASCII-only.
> O driver Firebird usa encoding cp1252 e rejeita Unicode (`═`, `—`, `ã`, `ç`) em comentários.

## 4. `processador.py`

Interface obrigatória: `validar()` e `verificar()`.

```python
"""Processador do alerta: conexoes_sem_grupo"""

from pathlib import Path
from typing import Any

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO = "nexus_proprio"


class ProcessadorConexoesSemGrupo:

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        return True, ""

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        dados = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=carregar_query(ARQUIVO_CONSULTAS, "verificar_conexoes_sem_grupo"),
            parametros={},
        )
        total = len(dados)
        resumo = (
            "Todas as conexões pertencem a grupos" if total == 0
            else f"{total} conexão(ões) ativa(s) sem grupo"
        )
        return {
            "encontrou_dados": total > 0,
            "total": total,
            "resumo": resumo,
            "dados": dados,
        }
```

> **Campos obrigatórios** no retorno de `verificar()`:
> - `encontrou_dados` (bool) — orquestrador usa para decidir se notifica
> - `total` (int) — exibido nos templates
> - `resumo` (str) — exibido no WhatsApp e email
> - `dados` (list) — linhas para o template iterar

## 5. Templates de mensagem

### `mensagens/whatsapp_consolidado.txt`

```jinja2
⚠️ *{{ titulo }}*

{% if total == 1 %}1 conexão sem grupo:{% else %}{{ total }} conexões sem grupo:{% endif %}

{% for c in dados %}
- *{{ c.nome }}* ({{ c.tipo }}) — {{ c.host }}
{% endfor %}
```

### `mensagens/email_consolidado_assunto.txt`

```jinja2
[{{ severidade | upper }}] {{ titulo }} — {{ total }} detectada(s)
```

### `mensagens/email_consolidado_html.html`

```html
<!doctype html><html lang="pt-BR">
<head><meta charset="UTF-8"><style>
  body { font-family: Arial, sans-serif; color: #333; }
  .header { background: #f59e0b; color: white; padding: 20px; border-radius: 4px; }
  table { width: 100%; border-collapse: collapse; margin-top: 15px; }
  th { background: #1f2937; color: white; padding: 10px; text-align: left; }
  td { padding: 8px 10px; border-bottom: 1px solid #e5e7eb; }
</style></head>
<body>
  <div class="header"><h1>⚠️ {{ titulo }}</h1></div>
  <p>{{ resumo }}</p>
  <table>
    <thead><tr><th>Nome</th><th>Tipo</th><th>Host</th><th>Banco</th></tr></thead>
    <tbody>
    {% for c in dados %}
    <tr><td><strong>{{ c.nome }}</strong></td><td>{{ c.tipo }}</td>
        <td>{{ c.host }}</td><td>{{ c.banco }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
</body></html>
```

## 6. Registre em `app/rotas/alertas.py`

```python
from app.alertas.conexoes_sem_grupo.processador import ProcessadorConexoesSemGrupo

PROCESSADORES = {
    "conexoes_inativas": ProcessadorConexoesInativas,
    "item_comprimento_excedente": ProcessadorItemComprimentoExcedente,
    "conexoes_sem_grupo": ProcessadorConexoesSemGrupo,
}
```

## 7. Sincronize e teste

```bash
curl -X POST http://localhost:8000/sincronizar

# Verificar sem forçar (respeita cooldown)
curl -X POST http://localhost:8000/alertas/conexoes_sem_grupo/verificar \
  -H "Content-Type: application/json" -d '{}'

# Forçar (ignora cooldown E dedup)
curl -X POST "http://localhost:8000/alertas/conexoes_sem_grupo/verificar?forcar=true" \
  -H "Content-Type: application/json" -d '{}'
```

**Resposta quando deve notificar:**
```json
{
  "deve_notificar": true,
  "total_encontrado": 3,
  "canais": ["whatsapp"],
  "destinatarios": [{"nome": "Lucas", "whatsapp": "5517981006771"}],
  "mensagens_consolidadas": {"whatsapp": "⚠️ *Conexões sem Grupo* ..."}
}
```

**Resposta quando não notifica:**
```json
{
  "deve_notificar": false,
  "motivo": "sem_dados"  // ou "em_cooldown" ou "dados_sem_alteracao"
}
```

---

## Tópicos avançados

### Parâmetros de data

Dois padrões comuns:

**Janela fixa (padrão: N dias atrás)**

```json
{
  "parametros": [
    {
      "nome": "data_inicio",
      "tipo": "date",
      "obrigatorio": false,
      "padrao": null,
      "rotulo": "Data de início (AAAA-MM-DD). Padrão: 30 dias atrás."
    }
  ]
}
```

```python
from datetime import date, timedelta

@staticmethod
def verificar(parametros: dict) -> dict:
    data_inicio = parametros.get("data_inicio") or (
        date.today() - timedelta(days=30)
    ).isoformat()

    dados = gerenciador_conexoes.executar(
        conexao=CONEXAO_ERP,
        query=carregar_query(ARQUIVO_CONSULTAS, "minha_query"),
        parametros={"data_inicio": data_inicio},
    )
    ...
```

**Dia útil anterior (alerta diário agendado)**

```python
def _dia_util_anterior() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:   # 5=sábado, 6=domingo
        d -= timedelta(days=1)
    return d

@staticmethod
def verificar(parametros: dict) -> dict:
    data_inicio = parametros.get("data_inicio") or _dia_util_anterior().isoformat()
    ...
```

Em ambos os casos: o N8N pode chamar sem parâmetros `{}` e o processador resolve o período automaticamente.

---

### ERP Firebird — padrão com `gerenciador_conexoes`

Para alertas que leem do ERP Firebird:

```python
from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "erp_firebird"

@staticmethod
def verificar(parametros: dict) -> dict:
    cod_empresa = parametros.get("cod_empresa", 1)
    data_inicio = parametros.get("data_inicio") or (
        date.today() - timedelta(days=30)
    ).isoformat()

    linhas = gerenciador_conexoes.executar(
        conexao=CONEXAO_ERP,
        query=carregar_query(ARQUIVO_CONSULTAS, "detectar_ocorrencias"),
        parametros={"cod_empresa": cod_empresa, "data_inicio": data_inicio},
    )
    ...
```

**Regras SQL para Firebird:**

| Problema | Causa | Solução |
|---|---|---|
| `UnicodeEncodeError cp1252` | Unicode em comentário `--` | ASCII-only em comentários |
| `invalid ORDER BY clause` em UNION | Alias não aceito | Usar posição: `ORDER BY 1, 3` |
| `SELECT 1` inválido | Exige FROM | `SELECT 1 FROM RDB$DATABASE` |

Query SQL exemplo:
```sql
-- name: detectar_ocorrencias
-- ASCII-only aqui: sem acentos, sem tracos especiais
SELECT
    p.PEDIDO,
    p.DATA,
    cad.NOME        AS NOME_CLIENTE,
    v.NOME          AS NOME_VENDEDOR
FROM ARQES13 p
JOIN ARQCAD cad ON cad.TIPOC = p.TIPOC AND cad.CODIC = p.CODIC
LEFT JOIN ARQCAD v ON v.TIPOC = p.TIPOV AND v.CODIC = p.CODIV
WHERE p.DATA >= :data_inicio
  AND p.COD_EMPRESA = :cod_empresa
ORDER BY p.DATA DESC
```

---

### Destinatários dinâmicos (`contatos_setores`)

Por padrão, os destinatários são fixos — cadastrados em `alertas_condicoes` no banco.
Para adicionar destinatários **dinâmicos** (ex: vendedor do pedido que gerou o alerta), retorne `contatos_setores` no payload do `verificar()`:

```python
@staticmethod
def verificar(parametros: dict) -> dict:
    linhas = gerenciador_conexoes.executar(...)
    df = pd.DataFrame(linhas)

    # Destinatários dinâmicos extraídos dos dados
    contatos_setores = []
    for _, row in df.drop_duplicates("cod_vendedor").iterrows():
        fone1 = str(row.get("telefone_vendedor", "") or "").strip()
        fone2 = str(row.get("telefone_vendedor2", "") or "").strip()
        if fone1:
            contatos_setores.append({
                "nome": str(row.get("nome_vendedor", "")),
                "setor": "Vendas",
                "whatsapp": fone1,
                "email": None,
            })
        if fone2:
            contatos_setores.append({
                "nome": str(row.get("nome_vendedor", "")) + " (ass.)",
                "setor": "Vendas",
                "whatsapp": fone2,
                "email": None,
            })

    return {
        "encontrou_dados": True,
        "total": len(df),
        "resumo": f"{len(df)} ocorrência(s) detectada(s)",
        "dados": df.to_dict("records"),
        "contatos_setores": contatos_setores,   # <-- orquestrador mescla aqui
    }
```

O orquestrador mescla `contatos_setores` com os destinatários fixos, sem duplicar WhatsApp.
Resultado: todos recebem a mesma mensagem consolidada.

**Campos aceitos em cada item de `contatos_setores`:**

| Campo | Tipo | Obrigatório |
|---|---|---|
| `nome` | str | Recomendado |
| `whatsapp` | str ou None | Pelo menos um de whatsapp/email |
| `email` | str ou None | |
| `setor` | str ou None | Opcional, aparece nos logs |

---

### Deduplicação por fingerprint

Evita renotificar quando os dados não mudaram desde o último disparo.
O orquestrador compara o `fingerprint` retornado pelo processador com o `hash_arquivo` gravado no `historico`.

```python
import hashlib
import json

@staticmethod
def verificar(parametros: dict) -> dict:
    # ... buscar dados ...

    # Fingerprint: identifica unicamente o conjunto de ocorrências
    chaves = sorted(
        (str(row.get("pedido", "")), str(row.get("seqcarga", "")), str(row.get("origem", "")))
        for row in dados
    )
    fingerprint = hashlib.sha256(json.dumps(chaves).encode()).hexdigest()

    return {
        "encontrou_dados": True,
        "total": len(dados),
        "resumo": resumo,
        "dados": dados,
        "fingerprint": fingerprint,   # orquestrador usa este campo para dedup
    }
```

**Fluxo automático:**
1. Processador retorna `fingerprint`
2. Orquestrador compara com `hash_arquivo` do último `historico` de sucesso
3. Se igual → `{"deve_notificar": false, "motivo": "dados_sem_alteracao"}`
4. Se diferente (ou primeiro disparo) → notifica, grava novo hash

`?forcar=true` bypassa cooldown **e** dedup. Útil para testes.

**Escolha das chaves de dedup:**

| Caso | Chaves recomendadas |
|---|---|
| Alertas de pedido/item | `(pedido, seqcarga, origem_medida)` |
| Alertas de conexões | `(conexao_id,)` |
| Alertas de estoque | `(cod_produto, lote)` |

Use campos que identificam unicamente a ocorrência — não use timestamps ou valores que mudam a cada execução.

---

## Resumo

| Arquivo | Função |
|---|---|
| `config.json` | Metadados e parâmetros do alerta |
| `consultas.sql` | Query de verificação com `-- name:` (ASCII-only) |
| `processador.py` | `validar()` + `verificar()` |
| `mensagens/whatsapp_consolidado.txt` | Template WhatsApp |
| `mensagens/email_consolidado_assunto.txt` | Assunto do e-mail |
| `mensagens/email_consolidado_html.html` | Corpo HTML do e-mail |

O alerta respeita automaticamente cooldown, destinatários fixos e canais configurados em `alertas_condicoes`.

**Campos opcionais que o processador pode retornar:**

| Campo | Efeito |
|---|---|
| `fingerprint` | Ativa deduplicação automática |
| `contatos_setores` | Adiciona destinatários dinâmicos à notificação |
| `limites` | Disponível no contexto Jinja2 dos templates |
| `estatisticas` | Disponível no contexto Jinja2 dos templates |
