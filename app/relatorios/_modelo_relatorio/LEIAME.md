# Modelo de Relatório

Pasta base para criar novos relatórios. Copie, renomeie e adapte.

## Estrutura de arquivos

```
nome_do_relatorio/
├── __init__.py       # vazio (obrigatório para Python package)
├── config.json       # metadados: título, categoria, parâmetros
├── consultas.sql     # queries nomeadas (Firebird + PostgreSQL)
├── processador.py    # lógica: validar() + buscar_dados()
├── template.html     # layout do relatório (Jinja2, extends base.html)
└── LEIAME.md
```

## Como copiar e adaptar (passo a passo)

```bash
# 1. Copia a pasta
cp -r app/relatorios/_modelo_relatorio app/relatorios/nome_do_relatorio

# 2. Edita config.json: título, categoria, parâmetros

# 3. Edita consultas.sql: adapta as 3 queries para o domínio real

# 4. Edita processador.py:
#    - Renomeia a classe: ProcessadorModeloRelatorio → ProcessadorNomeDoRelatorio
#    - Ajusta CONEXAO_ERP e CONEXAO_METAS
#    - Adapta buscar_dados() com a lógica real

# 5. Edita template.html: ajusta colunas das tabelas e campos dos cards
```

---

## Fluxo de dados

```
rota HTTP (POST /relatorios/nome_do_relatorio/solicitar)
    │
    ├─ validar(parametros)        → (bool, str)
    │
    └─ buscar_dados(parametros)   → dict (payload)
           │
           ├─ query Firebird (dados principais)
           ├─ query Firebird (série temporal)     [opcional]
           ├─ query PostgreSQL (metas/config)     [opcional, com fallback]
           ├─ join cross-DB com pandas
           ├─ cálculos derivados (atingimento, excedente...)
           ├─ agrupamentos (groupby + agg)
           ├─ top N (nlargest)
           ├─ gráficos matplotlib → base64 PNG
           └─ retorna payload dict
                   │
                   └─ renderizador injeta no template.html (Jinja2)
                          │
                          └─ PDF via WeasyPrint / HTML via resposta HTTP
```

---

## Chaves do payload (usadas no template.html)

| Chave | Tipo | Descrição |
|---|---|---|
| `total` | int | Total de registros |
| `periodo` | str | `"MM/YYYY"` para exibição |
| `resumo` | str | **Consumida pelo orquestrador**: texto do WhatsApp (caption do PDF ou mensagem inteira no formato `resumo_texto`) |
| `registros` | list[dict] | Linhas detalhadas (tabela completa) |
| `grupos` | list[dict] | Agrupamento por categoria |
| `top5` | list[dict] | Top 5 por valor |
| `resumo_global` | dict | KPIs: valor_total, meta_total, atingimento_global_pct, etc. |
| `grafico_barras` | str\|None | data URI base64 PNG |
| `grafico_tendencia` | str\|None | data URI base64 PNG |
| `grafico_pizza` | str\|None | data URI base64 PNG |
| `grafico_agrupado` | str\|None | data URI base64 PNG |

Variáveis injetadas pelo renderizador (sempre disponíveis no template):
- `titulo`, `subtitulo`, `data_geracao`

---

## O que o sistema faz por você (não reimplemente)

| Recurso | Como funciona |
|---|---|
| **Formatos de saída** | O mesmo `buscar_dados()` serve `?formato=json` (dados), `html` (página), `pdf` (download) e `base64` — você só escreve o template |
| **Entrega automática** | `?notificar=true` → orquestrador gera o PDF, cria entregas para os destinatários e o n8n envia (WhatsApp documento/resumo, email com anexo) |
| **Destinatários em 3 camadas** | Fixos (`relatorios_destinatarios`), extras do agendamento, criador do agendamento — resolvidos e deduplicados pelo orquestrador |
| **`modo_execucao: por_destinatario`** | 1 execução por destinatário aplicando o `filtro_parametros` dele (ex: cada gerente recebe o PDF da filial dele) — configure no `config.json` + admin |
| **`grupos_por_destinatario`** | Alternativa dinâmica: o próprio `buscar_dados()` retorna grupos (contrato documentado no `config.json` desta pasta) — 1 PDF filtrado por destinatário vindo da query |
| **`formato_whatsapp`** | Por destinatário: `documento` (PDF anexo com `resumo` de caption) ou `resumo_texto` (só o texto de `resumo`) |
| **Tokens dinâmicos** | Parâmetros com `{{hoje}}`, `{{ontem}}`, `{{mes_anterior_inicio}}`, `{{semana_atual_inicio}}`... resolvidos antes do processador (lista completa: `GET /relatorios/{nome}/config`) |
| **Validação de contatos** | Telefones normalizados para o formato Evolution API e emails validados pelo core — destino inválido é pulado com warning |
| **Compressão de PDF** | Ghostscript comprime o PDF antes da entrega (se instalado) |
| **Janela de silêncio / modo teste** | Silêncio adia a entrega (`enviar_apos`); modo teste redireciona tudo para o contato de teste |
| **Fila robusta** | Claim atômico (sem envio duplicado), retry 3× em 24h, purga de entregas antigas |
| **Agendamento** | `POST /agendamentos` com frequência diária/semanal/mensal/intervalo, fuso por agendamento |

---

## Pandas: padrões e receitas

### Normalizar colunas (sempre — Firebird retorna UPPERCASE)
```python
df.columns = [c.lower() for c in df.columns]
```

### Converter numéricos (nunca confie no tipo do banco)
```python
df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
# errors="coerce" → strings não-numéricas viram NaN → .fillna(0) resolve
```

### Groupby com múltiplas agregações
```python
df_grupos = (
    df.groupby("cod_categoria")
    .agg(
        qtd         = ("cod_categoria", "count"),
        valor_total = ("valor", "sum"),
        valor_medio = ("valor", "mean"),
        valor_max   = ("valor", "max"),
        meta_total  = ("meta",  "sum"),
    )
    .reset_index()                              # transforma índice em coluna normal
)
df_grupos["valor_medio"] = df_grupos["valor_medio"].round(2)
grupos = df_grupos.sort_values("valor_total", ascending=False).to_dict("records")
```

### Cálculo de atingimento (sem divisão por zero)
```python
import numpy as np

df["atingimento_pct"] = np.where(
    df["meta"] > 0,                         # condição
    (df["valor"] / df["meta"] * 100).round(1),  # se True
    0.0,                                    # se False (meta = 0)
)
```

### Top N
```python
top5 = df.nlargest(5, "valor")[["nome", "valor", "meta"]].to_dict("records")
```

### Filtro por enum/lista
```python
# Coluna que pode ser NaN → use isin seguro
df = df[df["status"].isin(["ativo", "pendente"])]

# Excluir valores nulos também
df = df[df["valor"].notna() & (df["valor"] > 0)]
```

### Série temporal: garantir continuidade de dias
```python
# Se quiser mostrar dias sem venda como 0 (não pular no gráfico)
todos_os_dias = pd.DataFrame({"dia": range(1, 32)})
df_serie = todos_os_dias.merge(df_serie, on="dia", how="left").fillna(0)
```

---

## Join cross-database (Firebird + PostgreSQL com pandas)

O Nexus não conecta os dois bancos em uma query — o join acontece em Python.

```python
# 1. Dados do ERP (Firebird)
df_erp = pd.DataFrame(gerenciador_conexoes.executar(conexao=CONEXAO_ERP, query=..., parametros=...))
df_erp.columns = [c.lower() for c in df_erp.columns]

# 2. Metas do nexus_metas (PostgreSQL)
df_metas = pd.DataFrame(gerenciador_conexoes.executar(conexao=CONEXAO_METAS, query=..., parametros=...))
df_metas.columns = [c.lower() for c in df_metas.columns]

# 3. Merge como LEFT JOIN (mantém todos os registros do ERP)
df = df_erp.merge(
    df_metas[["cod_vendedor", "meta_valor"]],   # só as colunas necessárias
    on="cod_vendedor",
    how="left",
)
df["meta_valor"] = df["meta_valor"].fillna(0)   # sem match → 0
```

**Chave de join pode ser composta:**
```python
df = df_erp.merge(
    df_metas,
    on=["cod_empresa", "cod_vendedor", "mes", "ano"],
    how="left",
    suffixes=("", "_meta"),         # resolve conflito de nomes de coluna
)
```

---

## Gráficos matplotlib

### Por que base64?
O PDF é gerado pelo WeasyPrint, que não acessa o filesystem em tempo de render.
Embedar os gráficos como data URI `data:image/png;base64,...` resolve isso.

### Padrão de função
```python
def _figura_para_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)   # IMPORTANTE: libera memória
    return f"data:image/png;base64,{b64}"
```

### Sempre feche a figura após salvar
`plt.close(fig)` é obrigatório em ambiente de servidor.
Sem isso, figuras acumulam em memória a cada requisição.

### Barras horizontais (ranking)
```python
df = df.sort_values("valor", ascending=True)   # crescente = maior fica no topo
fig, ax = plt.subplots(figsize=(10, max(5, len(df) * 0.55)))
ax.barh(df["nome"], df["valor"], color="#2563eb", edgecolor="white", height=0.6)
```

### Linha com preenchimento (tendência)
```python
ax.fill_between(x, y, alpha=0.12, color="#2563eb")   # área sombreada
ax.plot(x, y, marker="o", linewidth=2, color="#2563eb", markersize=5)
```

### Pizza com agrupamento de fatias pequenas
```python
total = df["valor"].sum()
df["pct"] = df["valor"] / total * 100
grandes = df[df["pct"] >= 3]
outros  = df[df["pct"] <  3]
# agrupa "Outros" numa fatia única
```

### Barras agrupadas (realizado x meta)
```python
x = np.arange(len(categorias))
largura = 0.38
ax.bar(x - largura/2, realizados, largura, label="Realizado", color="#2563eb")
ax.bar(x + largura/2, metas,      largura, label="Meta",      color="#6b7280", alpha=0.55)
```

### Anotação no último ponto (linha)
```python
ax.annotate(
    f"R$ {y[-1]:,.0f}",
    xy=(x[-1], y[-1]),
    xytext=(5, 5), textcoords="offset points",
    fontsize=8, fontweight="bold", color="#2563eb",
)
```

---

## Template HTML (Jinja2)

### Herança obrigatória
```html
{% extends "base.html" %}
{% block estilos_extras %}...{% endblock %}
{% block conteudo %}...{% endblock %}
```

### Estado vazio (sempre trate)
```html
{% if total == 0 %}
<div class="sem-dados">Nenhum dado para o período {{ periodo }}.</div>
{% else %}
  ... conteúdo normal ...
{% endif %}
```

### Formatar moeda
```html
R$ {{ "{:,.0f}".format(valor) }}       <!-- sem decimais: R$ 1.234 -->
R$ {{ "{:,.2f}".format(valor) }}       <!-- com decimais: R$ 1.234,56 -->
```

### Badge de status condicional
```html
{% if r.atingimento_pct >= 100 %}
  <span class="badge badge-sucesso">{{ r.atingimento_pct }}%</span>
{% elif r.atingimento_pct >= 80 %}
  <span class="badge badge-aviso">{{ r.atingimento_pct }}%</span>
{% else %}
  <span class="badge badge-erro">{{ r.atingimento_pct }}%</span>
{% endif %}
```

### Verificar se chave existe antes de usar
```html
{% if r.meta is defined and r.meta > 0 %}
  <td>R$ {{ "{:,.0f}".format(r.meta) }}</td>
{% endif %}
```

### Loop com índice
```html
{% for r in top5 %}
  <td>{{ loop.index }}º</td>   <!-- 1º, 2º, 3º... -->
{% endfor %}
```

### min() no template (barra de progresso)
```html
<!-- Limita largura da barra a 100% mesmo quando atingimento > 100% -->
style="width: {{ [r.atingimento_pct, 100] | min }}%"
```

### Gráfico embutido
```html
{% if grafico_tendencia %}
<div class="grafico-wrap">
  <img src="{{ grafico_tendencia }}" alt="Tendência">
  <div class="grafico-legenda">Figura 1 — Tendência em {{ periodo }}</div>
</div>
{% endif %}
```

---

## Banco auxiliar opcional (com fallback)

Quando o PostgreSQL é opcional (relatório funciona sem metas):

```python
df_metas = pd.DataFrame()
try:
    linhas = gerenciador_conexoes.executar(
        conexao=CONEXAO_METAS, query=..., parametros=...
    )
    df_metas = pd.DataFrame(linhas)
    if not df_metas.empty:
        df_metas.columns = [c.lower() for c in df_metas.columns]
except Exception:
    logger.warning("nexus_metas indisponível — relatório sem metas")
```

Se o banco auxiliar for obrigatório: remova o try/except.

---

## Firebird: sintaxe específica

```sql
-- Sem LIMIT — use ROWS
SELECT * FROM tabela ROWS 10;
SELECT * FROM tabela ROWS 10 TO 20;    -- paginação

-- Ano/mês
WHERE EXTRACT(YEAR FROM data) = :ano AND EXTRACT(MONTH FROM data) = :mes

-- Diferença de dias
WHERE DATEDIFF(DAY, data, CURRENT_DATE) <= 30

-- Window function (só Firebird 3+)
COUNT(DISTINCT pedido) OVER (PARTITION BY cod_vendedor)

-- Parâmetros: dois-pontos
WHERE cod_empresa = :cod_empresa
```

## PostgreSQL (nexus_metas): sintaxe

```sql
-- Parâmetros: %(nome)s
WHERE cod_empresa = %(cod_empresa)s AND ano = %(ano)s AND mes = %(mes)s

-- Lista Python
WHERE cod_categoria = ANY(%(lista_cats)s)

-- Booleano
WHERE ativo = TRUE

-- Intervalo relativo
WHERE criado_em >= NOW() - INTERVAL '30 days'
```

---

## Checklist ao criar novo relatório

- [ ] Renomeou a pasta (sem underscore inicial)
- [ ] Atualizou `config.json` (titulo, subtitulo, categoria, modo_execucao, parametros)
- [ ] Adaptou as 3 queries em `consultas.sql` para o domínio real
- [ ] Renomeou a classe no `processador.py` (mantendo o prefixo `Processador`)
- [ ] Ajustou `CONEXAO_ERP` e `CONEXAO_METAS` se necessário
- [ ] Adaptou `buscar_dados()`: colunas, joins, agrupamentos, gráficos
- [ ] Payload retorna `resumo` (texto do WhatsApp na entrega)
- [ ] Adaptou `template.html`: campos das tabelas, colunas dos cards
- [ ] Subiu a aplicação e conferiu o log: sem warning de contrato para a sua pasta
- [ ] Testou `?formato=html` no navegador, depois `?formato=pdf`
- [ ] Testou entrega com `?notificar=true` em modo teste antes de agendar
- [ ] Verificou que `plt.close(fig)` está sendo chamado em todos os gráficos
