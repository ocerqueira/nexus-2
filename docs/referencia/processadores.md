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

### Registro — automático

Não há registro manual. O Nexus descobre o processador pela convenção:

1. Pasta `app/relatorios/{nome}/` com `config.json` e `processador.py`
2. Dentro do `processador.py`, uma classe cujo nome **começa com `Processador`** (ex: `ProcessadorPedidosPorVendedor`)

A descoberta é feita por `app/core/processadores.py` (`carregar_processador`). Título e subtítulo vêm do `config.json`.

No startup, o sincronizador valida o contrato de cada pasta (classe existe? tem `validar` + `buscar_dados`?) e loga um *warning* para pastas quebradas — o erro aparece no boot, não no primeiro disparo.

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
| `fingerprint` | Salvo em `historico.hash_arquivo` para auditoria. A deduplicação real é **por item**: o orquestrador calcula SHA256 de cada linha de `dados` e controla cooldown em `alertas_itens_notificados`. |
| `contatos_setores` | Mesclados nos destinatários da notificação. Duplicatas por WhatsApp são removidas. |
| `grupos_por_destinatario` | Cada grupo `{destinatario: {...}, itens: [...]}` vira um destinatário dinâmico que recebe apenas os itens do seu grupo. |
| Qualquer outro | Disponível no contexto dos templates Jinja2 via `{{ campo }}`. |

Se `encontrou_dados` for `False`, o orquestrador não renderiza mensagens nem notifica — retorna `motivo: sem_dados`.

### Registro — automático

Igual aos relatórios: pasta em `app/alertas/{nome}/` + classe `Processador*` em `processador.py`. Contrato exigido: `validar(parametros)` + `verificar(parametros)`. O sincronizador valida no startup e loga *warning* se a pasta estiver quebrada.

---

## Validação de contatos (core)

Telefones e emails que entram na fila de entregas são **validados pelo core** (`app/core/entregas_comum.py`) — destino inválido gera *warning* no log e a entrega daquele canal é pulada:

```python
from app.core.entregas_comum import normalizar_whatsapp, validar_email

normalizar_whatsapp("+55 (17) 99999-0000")  # → "5517999990000"
normalizar_whatsapp("17 99999-0000")        # → "5517999990000" (DDI 55 adicionado)
normalizar_whatsapp("999")                  # → None (inválido)
validar_email("  Joao@Empresa.COM ")        # → "joao@empresa.com"
```

`normalizar_whatsapp` aceita formatos variados (com máscara, DDI, prefixo 0) e devolve o formato exigido pela Evolution API: só dígitos com DDI 55 (12-13 dígitos). Use no processador ao extrair telefones do ERP para `contatos_setores` — o core valida de novo na entrega, mas normalizar cedo evita perder o destinatário por dedup errado.

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

#### `itens_comprimento_por_carga`
- **Classe**: `ProcessadorItensComprimentoPorCarga`
- **Conexão**: `REPLICA_TERRA` (Firebird)
- **Parâmetros**: `data_inicio` (padrão: dia útil anterior), `data_fim` (padrão: igual a `data_inicio`), `cod_empresa` (padrão 1)
- **Filtro**: `VD_CARGA.DT_SAIDA` (data de saída da carga)
- **Output**: itens de telha/SBX com comprimento excedente consolidados por carga, com NROCARGA, NOME_CARGA, pedido, item, cliente, vendedor e metragem

---

### Alertas

#### `item_comprimento_excedente`
- **Classe**: `ProcessadorItemComprimentoExcedente`
- **Conexão**: `REPLICA_TERRA` (Firebird)
- **Parâmetros**: `data_inicio` (padrão: 30 dias atrás), `cod_empresa` (padrão 1)
- **Output**: itens de telha/SBX com comprimento excedente, estatísticas por origem de medida, fingerprint SHA256 para deduplicação
- **Dedup**: SHA256 de `(PEDIDO, SEQCARGA, ORIGEM_MEDIDA)` — não renotifica se dados não mudaram
- **Destinatários dinâmicos**: `contatos_setores` (vendedor + assistente do pedido via `ARQCAD.fone1/fone2`)