# Referência — Processadores

Processadores são classes Python que encapsulam a lógica de um relatório ou alerta. Eles são o ponto de extensão principal do Nexus.

---

## Processador de relatório

### Interface

```python
class ProcessadorRelatorio:
    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        """Valida parâmetros recebidos da API."""
        ...

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        """Executa queries e retorna dados para renderização."""
        ...
```

### `validar(parametros) → tuple[bool, str]`

Recebe o dict `parametros` do corpo da requisição. Retorna `(True, "")` se válido, ou `(False, "mensagem de erro")` se inválido.

O método deve validar:
- Tipos dos parâmetros (boolean, string, int)
- Valores permitidos (enums)
- Parâmetros obrigatórios (se houver)

### `buscar_dados(parametros) → dict[str, Any]`

Recebe o mesmo dict `parametros` (já validado). Retorna um dict com os dados que serão passados ao template Jinja2.

O dict de retorno deve conter pelo menos:
- `total`: número de registros (usado nos cards de resumo)
- Uma chave com a lista de dados (ex: `conexoes`, `usuarios`)

### Registro

O processador deve ser registrado no dicionário `PROCESSADORES` em `app/rotas/relatorios.py`:

```python
PROCESSADORES = {
    "nome_do_relatorio": {
        "classe": MinhaClasseProcessador,
        "titulo": "Título Visível",
        "subtitulo": "Subtítulo opcional",
    },
}
```

---

## Processador de alerta

### Interface

```python
class ProcessadorAlerta:
    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        """Valida parâmetros recebidos da API."""
        ...

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        """Executa a verificação e retorna os dados encontrados."""
        ...
```

### `verificar(parametros) → dict[str, Any]`

Diferente do `buscar_dados` do relatório, o `verificar` retorna um dict com a chave obrigatória `encontrou_dados`:

```python
return {
    # --- Obrigatórios ---
    "encontrou_dados": True,       # bool: se há algo para notificar
    "total": 3,                    # int: quantidade de registros
    "resumo": "3 conexões...",     # str: descrição curta
    "dados": [{...}, {...}],       # list[dict]: dados para templates

    # --- Opcionais (orquestrador processa se presentes) ---
    "fingerprint": "sha256hex...", # str: hash para deduplicação
    "contatos_setores": [          # list[dict]: destinatários dinâmicos
        {
            "nome": "João Vendedor",
            "whatsapp": "5517999991111",
            "email": None,
            "setor": "Vendas",
        }
    ],
    # Qualquer outro campo extra fica disponível no contexto Jinja2
    "estatisticas": {...},
    "limites": {...},
}
```

**Comportamento por campo opcional:**

| Campo | Efeito quando presente |
|---|---|
| `fingerprint` | Orquestrador compara com último `hash_arquivo` no `historico`. Se igual → `motivo: dados_sem_alteracao`, não notifica. |
| `contatos_setores` | Mesclados nos destinatários da notificação. Duplicatas por WhatsApp são removidas. |
| Qualquer outro | Disponível no contexto dos templates Jinja2 via `{{ campo }}`. |

Se `encontrou_dados` for `False`, o orquestrador não renderiza mensagens nem notifica — retorna `motivo: sem_dados`.

### Registro

O processador deve ser registrado no dicionário `PROCESSADORES` em `app/rotas/alertas.py`:

```python
from app.alertas.conexoes_inativas.processador import ProcessadorConexoesInativas

PROCESSADORES = {
    "conexoes_inativas": ProcessadorConexoesInativas,
}
```

Diferente dos relatórios, o valor é a classe diretamente (não um dict com metadados). Os metadados vêm do `config.json` e do banco.

---

## Convenções de arquivos

Cada processador vive em sua própria pasta dentro de `app/relatorios/` ou `app/alertas/`:

```
app/
  relatorios/
    teste_conexoes/
      __init__.py          (vazio)
      config.json          (metadados)
      consultas.sql        (queries com -- name:)
      processador.py       (classe Python)
      template.html        (template Jinja2)
  alertas/
    conexoes_inativas/
      __init__.py          (vazio)
      config.json          (metadados)
      consultas.sql        (queries com -- name:)
      processador.py       (classe Python)
      mensagens/
        whatsapp_consolidado.txt
        email_consolidado_assunto.txt
        email_consolidado_html.html
```

---

## Processadores existentes

### Relatórios

#### `teste_conexoes`
- **Classe**: `ProcessadorTesteConexoes`
- **Conexão**: `nexus_proprio` (banco interno)
- **Parâmetros**: `apenas_ativas` (bool), `tipo_banco` (string)

#### `dashboard_conexoes`
- **Classe**: `ProcessadorDashboardConexoes`
- **Conexão**: `nexus_proprio` (banco interno)
- **Parâmetros**: `apenas_ativas` (bool), `tipo_banco` (string)
- **Output**: gráficos (barras agrupadas + pizza/donut) com matplotlib, tabela de conexões

#### `desempenho_vendas`
- **Classe**: `ProcessadorDesempenhoVendas`
- **Conexão**: `REPLICA_TERRA` (Firebird — vendas) + `testes` (PostgreSQL — metas)
- **Parâmetros**: `cod_empresa` (int, padrão 1), `ano` (int, padrão 2026), `mes` (int, padrão 7)
- **Output**: gráfico vendas vs meta, gráfico de tendência diária, ranking de vendedores

#### `pedidos_por_vendedor`
- **Classe**: `ProcessadorPedidosPorVendedor`
- **Conexão**: `REPLICA_TERRA` (Firebird)
- **Parâmetros**: `data_inicio` (obrigatório), `data_fim` (obrigatório), `cod_empresa` (padrão 1)
- **Output**: ranking de vendedores com ticket médio, gráfico horizontal top 15, top 5 produtos por vendedor

#### `itens_comprimento_por_carga`
- **Classe**: `ProcessadorItensComprimentoPorCarga`
- **Conexão**: `REPLICA_TERRA` (Firebird)
- **Parâmetros**: `data_inicio` (padrão: dia útil anterior), `data_fim` (padrão: igual a `data_inicio`), `cod_empresa` (padrão 1)
- **Filtro**: `VD_CARGA.DT_SAIDA` (data de saída da carga)
- **Output**: itens de telha/SBX com comprimento excedente consolidados por carga, com NROCARGA, NOME_CARGA, pedido, item, cliente, vendedor e metragem

---

### Alertas

#### `conexoes_inativas`
- **Classe**: `ProcessadorConexoesInativas`
- **Conexão**: `nexus_proprio`
- **Parâmetros**: `incluir_observacoes` (bool, padrão `false`)

#### `item_comprimento_excedente`
- **Classe**: `ProcessadorItemComprimentoExcedente`
- **Conexão**: `REPLICA_TERRA` (Firebird)
- **Parâmetros**: `data_inicio` (padrão: 30 dias atrás), `cod_empresa` (padrão 1)
- **Output**: itens de telha/SBX com comprimento excedente, estatísticas por origem de medida, fingerprint SHA256 para deduplicação
- **Dedup**: SHA256 de `(PEDIDO, SEQCARGA, ORIGEM_MEDIDA)` — não renotifica se dados não mudaram
- **Destinatários dinâmicos**: `contatos_setores` (vendedor + assistente do pedido via `ARQCAD.fone1/fone2`)