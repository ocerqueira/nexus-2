# Modelo de Alerta

Pasta base para criar novos alertas. Copie, renomeie e adapte.

## Estrutura de arquivos

```
nome_do_alerta/
├── __init__.py               # vazio (obrigatório para Python package)
├── config.json               # metadados: título, severidade, parâmetros
├── consultas.sql             # queries nomeadas (Firebird + PostgreSQL)
├── processador.py            # lógica: validar() + verificar()
├── LEIAME.md
└── mensagens/
    ├── email_consolidado_assunto.txt    # subject do email (1 por execução)
    ├── email_consolidado_html.html      # corpo HTML (todos os dados)
    ├── email_individual_assunto.txt     # subject por ocorrência
    ├── email_individual_html.html       # corpo HTML por ocorrência
    ├── whatsapp_consolidado.txt         # mensagem WA (resumo geral)
    └── whatsapp_individual.txt          # mensagem WA por ocorrência
```

## Como copiar e adaptar (passo a passo)

```bash
# 1. Copia a pasta
cp -r app/alertas/_modelo_alerta app/alertas/nome_do_alerta

# 2. Edita config.json: título, descrição, severidade, parâmetros

# 3. Edita consultas.sql: adapta as queries para o domínio real

# 4. Edita processador.py:
#    - Renomeia a classe: ProcessadorModeloAlerta → ProcessadorNomeDoAlerta
#    - Ajusta CONEXAO_ERP e CONEXAO_METAS
#    - Adapta verificar() com a lógica real

# 5. Edita os templates de mensagem com os campos reais
```

---

## Fluxo de dados

```
orquestrador
    │
    ├─ validar(parametros)          → (bool, str)
    │                                 retorna False se parâmetro inválido
    │
    └─ verificar(parametros)        → dict
           │
           ├─ query Firebird (ERP)   → pd.DataFrame df
           ├─ query PostgreSQL (opt) → pd.DataFrame df_config
           ├─ join cross-DB          → df merged
           ├─ cálculos pandas
           ├─ fingerprint SHA-256
           └─ retorna payload dict
                   │
                   └─ orquestrador decide:
                         encontrou_dados=False → não notifica
                         encontrou_dados=True  → renderiza templates + envia
```

---

## Chaves obrigatórias no retorno de verificar()

| Chave | Tipo | Descrição |
|---|---|---|
| `encontrou_dados` | bool | Se `False`, orquestrador para aqui — nenhuma notificação é enviada |
| `total` | int | Quantidade de registros |
| `resumo` | str | Texto curto (aparece em logs e no subject do email) |
| `dados` | list[dict] | Registros individuais — iterados nos templates Jinja com `{% for item in dados %}` |

## Chaves opcionais consumidas pelo orquestrador

| Chave | Tipo | Descrição |
|---|---|---|
| `contatos_setores` | list | Destinatários dinâmicos: `[{"nome", "whatsapp", "email", "setor"}]`. Mesclados aos fixos (`alertas_destinatarios`), dedup por whatsapp. Normalize o fone com `normalizar_whatsapp()`. |
| `grupos_por_destinatario` | list | `[{"destinatario": {...}, "itens": [...]}]` — cada destinatário recebe SÓ os itens do grupo dele (ex: vendedor recebe só os pedidos dele). |
| `fingerprint` | str | Auditoria (`historico.hash_arquivo`). A dedup real é **por item** — ver seção Fingerprint. |

## Chaves livres (viram variáveis Jinja nos templates)

| Chave | Tipo | Descrição |
|---|---|---|
| `estatisticas` | dict | Métricas agregadas — usadas diretamente nos cards dos templates |
| `estatisticas_por_grupo` | list | Agrupamento secundário para a tabela de resumo |
| qualquer outra | — | Disponível no template como `{{ nome_da_chave }}` |

---

## Pandas: padrões e armadilhas

### Normalizar colunas (sempre faça isso logo após criar o DataFrame)
```python
df.columns = [c.lower() for c in df.columns]
# Firebird retorna UPPERCASE — sem isso, df["valor"] não encontra "VALOR"
```

### Converter numéricos (nunca confie no tipo vindo do banco)
```python
df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
# errors="coerce" transforma strings não-numéricas em NaN
# .fillna(0) evita NaN se espalhando nos cálculos
```

### Converter datas
```python
df["data"] = pd.to_datetime(df["data"], errors="coerce")
df["data_fmt"] = df["data"].dt.strftime("%d/%m/%Y").fillna("N/D")
```

### Groupby com múltiplas agregações
```python
df_grupo = (
    df.groupby("cod_categoria")
    .agg(
        total       = ("cod_categoria", "count"),
        valor_total = ("valor", "sum"),
        valor_max   = ("valor", "max"),
        valor_medio = ("valor", "mean"),
    )
    .reset_index()                          # transforma o índice em coluna normal
)
df_grupo["valor_medio"] = df_grupo["valor_medio"].round(2)
grupos = df_grupo.to_dict("records")        # lista de dicts para o template
```

### Filtrar com condição em múltiplas colunas
```python
df = df[
    (df["valor"] > df["limite"]) &
    (df["situacao"] == 2)
]
```

### nunique() para contar distintos
```python
pedidos_unicos    = df["pedido"].nunique()
vendedores_unicos = df["cod_vendedor"].nunique()
```

### nlargest() para Top N
```python
top3 = df.nlargest(3, "valor")[["nome", "valor", "meta"]].to_dict("records")
```

### clip() para evitar negativos em excedentes
```python
df["excedente"] = (df["valor"] - df["limite"]).clip(lower=0)
```

### where() para cálculos condicionais (evita divisão por zero)
```python
df["pct"] = (
    (df["valor"] / df["meta"] * 100)
    .where(df["meta"] > 0, other=0)
    .round(1)
)
```

---

## Join cross-database (Firebird + PostgreSQL com pandas)

O banco não faz o JOIN — você faz em Python com `df.merge()`.

```python
# 1. Busca do Firebird
linhas_erp = gerenciador_conexoes.executar(conexao=CONEXAO_ERP, query=..., parametros=...)
df_erp = pd.DataFrame(linhas_erp)
df_erp.columns = [c.lower() for c in df_erp.columns]

# 2. Busca do PostgreSQL
linhas_pg = gerenciador_conexoes.executar(conexao=CONEXAO_METAS, query=..., parametros=...)
df_pg = pd.DataFrame(linhas_pg)
df_pg.columns = [c.lower() for c in df_pg.columns]

# 3. Merge (como um LEFT JOIN SQL)
df = df_erp.merge(
    df_pg[["cod_categoria", "limite", "descricao"]],  # só as colunas necessárias
    on="cod_categoria",
    how="left",   # mantém todos os registros do ERP, mesmo sem match
)
df["limite"] = df["limite"].fillna(0)  # coluna da direita pode ser NaN nos left-only
```

**Quando usar `how`:**
- `how="left"` — mantém todos do ERP, preenche NaN onde não há match
- `how="inner"` — só linhas com match em ambos (descarta sem correspondência)
- `how="outer"` — mantém tudo de ambos (raro em alertas)

---

## Fingerprint e cooldown (deduplicação POR ITEM)

Você **não precisa implementar dedup** — o orquestrador faz sozinho:

1. Para cada linha de `dados`, calcula SHA-256 da linha inteira
2. Consulta `alertas_itens_notificados`: item já notificado dentro do `cooldown_minutos`? → pula só ele
3. Item novo (ou com qualquer valor alterado) → dispara na hora
4. Cooldown só conta quando alguma entrega foi criada de fato (sem destinatário / rate limit / sem template → não trava)

Consequência prática: **mudança em qualquer campo da linha = item "novo"**. Se sua
query retorna campos voláteis (timestamp de consulta, contadores), remova-os do
SELECT ou o dedup nunca vai segurar nada.

O `fingerprint` que você retorna no payload é só auditoria (`historico.hash_arquivo`):

```python
chaves = sorted(
    (str(row.get("pedido", "")), str(row.get("cod_produto", "")))
    for row in df.to_dict("records")
)
fingerprint = hashlib.sha256(json.dumps(chaves).encode()).hexdigest()
```

`?forcar=true` na API ignora cooldown e dedup (testes manuais).

---

## Agrupado vs Individual (modo_mensagem)

O modo é **por destinatário fixo**, configurado em `alertas_destinatarios.modo_mensagem`
(Admin Panel). Destinatários dinâmicos (`contatos_setores`) são sempre `individual`.

| Modo | Comportamento | Template usado |
|---|---|---|
| `individual` (padrão) | 1 entrega por item novo — campos do item viram variáveis Jinja direto (`{{ pedido }}`, não `{{ item.pedido }}`) | `whatsapp_individual.txt`, `email_individual_*` |
| `agrupado` | 1 entrega com todos os itens novos — itere `{% for item in dados %}` | `whatsapp_consolidado.txt`, `email_consolidado_*` |

Canal por destinatário (`canais`: whatsapp/email/sms) também vem de `alertas_destinatarios`.
Template inexistente para (canal, modo) → entrega daquele canal é pulada com warning.

---

## O que o orquestrador faz por você (não reimplemente)

| Recurso | Como funciona |
|---|---|
| **Dedup + cooldown por item** | Automático sobre `dados` (ver seção Fingerprint) |
| **Destinatários fixos** | `alertas_destinatarios` via Admin Panel — merge com os dinâmicos, dedup por whatsapp |
| **Validação de contatos** | Todo destino passa por `normalizar_whatsapp`/`validar_email` do core antes de entrar na fila — inválido é pulado com warning |
| **Rate limit** | `limite_hora`/`limite_dia` por (destinatário × alerta), configurado no admin |
| **Janela de silêncio** | Usuário com silêncio ativo → entrega criada com `enviar_apos` = fim da janela |
| **Modo teste** | Configuração global redireciona TODAS as entregas para número/email de teste |
| **Fila de entregas** | Claim atômico pelo n8n (sem envio duplicado), retry automático (3× em 24h), purga de antigas |
| **Tokens dinâmicos** | Parâmetros com `{{hoje}}`, `{{ontem}}`, `{{mes_anterior_inicio}}`... resolvidos antes de chegar no processador |
| **Histórico** | Cada disparo registrado em `historico` com total de entregas |

---

## Banco auxiliar opcional (com fallback)

Quando o PostgreSQL `nexus_metas` é opcional (o alerta funciona sem ele):

```python
df_config = pd.DataFrame()
try:
    linhas = gerenciador_conexoes.executar(conexao=CONEXAO_METAS, query=..., parametros=...)
    df_config = pd.DataFrame(linhas)
    if not df_config.empty:
        df_config.columns = [c.lower() for c in df_config.columns]
except Exception:
    logger.warning("nexus_metas indisponível — alerta sem configurações de limite")
    # continua sem os dados auxiliares
```

Quando é obrigatório: remova o try/except e deixe a exceção subir.

---

## Firebird: sintaxe específica

```sql
-- LIMIT → ROWS (Firebird não tem LIMIT)
SELECT * FROM tabela ROWS 1;
SELECT * FROM tabela ROWS 10 TO 20;  -- paginação

-- Filtro por ano/mês
WHERE EXTRACT(YEAR FROM data) = :ano AND EXTRACT(MONTH FROM data) = :mes

-- Diferença de dias
WHERE DATEDIFF(DAY, data, CURRENT_DATE) <= 30

-- Cast explícito
CAST(campo AS DECIMAL(15,2))
CAST(campo AS VARCHAR(50))

-- Concatenação
campo1 || ' - ' || campo2

-- Parâmetros nomeados com dois-pontos
WHERE cod_empresa = :cod_empresa AND data >= :data_inicio
```

## PostgreSQL (nexus_metas): sintaxe

```sql
-- Parâmetros com %(nome)s (psycopg2)
WHERE cod_empresa = %(cod_empresa)s

-- Lista Python com ANY
WHERE cod_categoria = ANY(%(lista)s)

-- Busca case-insensitive
WHERE nome ILIKE %(nome)s   -- passa '%valor%' no parâmetro

-- Booleanos sem aspas
WHERE ativo = TRUE

-- Intervalo de datas
WHERE criado_em >= NOW() - INTERVAL '30 days'
```

---

## Severidade: cores nos templates de email

| Valor | Cor header | Cor card |
|---|---|---|
| `critico` | `#ef4444` (vermelho) | `border-left: #ef4444` |
| `alto` | `#f97316` (laranja) | `border-left: #f97316` |
| `medio` | `#f59e0b` (amarelo) | `border-left: #f59e0b` |
| `baixo` | `#10b981` (verde) | `border-left: #10b981` |

Troque apenas a cor no CSS do `email_consolidado_html.html`.

---

## Checklist ao criar novo alerta

- [ ] Renomeou a pasta (sem underscore inicial)
- [ ] Atualizou `config.json` (titulo, descricao, severidade, **cooldown_minutos**, parametros)
- [ ] Adaptou `consultas.sql` com as queries reais (sem campos voláteis no SELECT — quebram o dedup)
- [ ] Renomeou a classe no `processador.py` (mantendo o prefixo `Processador`)
- [ ] Ajustou `CONEXAO_ERP` e `CONEXAO_METAS` se necessário
- [ ] Adaptou `verificar()` com a condição real do alerta
- [ ] Telefones do ERP passando por `normalizar_whatsapp()` antes de ir pra `contatos_setores`
- [ ] Atualizou as colunas nas tabelas dos templates HTML
- [ ] Subiu a aplicação e conferiu o log: sem warning de contrato para a sua pasta
- [ ] Testou com `?forcar=true` e depois com dados reais antes de agendar
