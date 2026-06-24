# Explicação — Renderização de mensagens

## O problema

Um sistema de alertas precisa gerar mensagens em múltiplos canais (e-mail, WhatsApp), em múltiplos modos (consolidado = uma mensagem com todos os dados; individual = uma mensagem por registro), e cada alerta pode ter necessidades diferentes de formatação.

Hardcodar a renderização no motor de alertas criaria um sistema rígido — cada novo alerta exigiria modificar o orquestrador.

## A solução

O Nexus usa **templates Jinja2 opcionais** no filesystem. O orquestrador detecta quais templates existem e renderiza apenas os disponíveis.

### Estrutura de arquivos

```
app/alertas/conexoes_inativas/
  mensagens/
    whatsapp_consolidado.txt        ← template WhatsApp (modo consolidado)
    email_consolidado_assunto.txt   ← assunto do e-mail consolidado
    email_consolidado_html.html     ← corpo HTML do e-mail consolidado
    whatsapp_individual.txt         ← (opcional) WhatsApp por registro
    email_individual_assunto.txt    ← (opcional) assunto por registro
    email_individual_html.html      ← (opcional) HTML por registro
```

### Detecção de capacidades

A função `detectar_capacidades_alerta()` inspeciona o filesystem:

```python
def detectar_capacidades_alerta(nome_alerta: str) -> dict:
    return {
        "tem_consolidado": True/False,   # Existe pelo menos 1 template consolidado
        "tem_individual": True/False,    # Existe pelo menos 1 template individual
        "canais_consolidado": [...],     # ["whatsapp", "email"]
        "canais_individual": [...],
    }
```

Se um arquivo não existe, aquela capacidade simplesmente não aparece no payload. Não há erro, não há fallback — é ausência intencional.

### Resolução de templates

O Jinja2 é configurado com `FileSystemLoader` apontando para a pasta `mensagens/` do alerta. Isso isola cada alerta: um template nunca interfere no outro.

### Contexto passado aos templates

**Modo consolidado**:
```python
contexto = {
    "titulo": "Conexões Inativas Detectadas",
    "severidade": "aviso",
    "descricao": "...",
    "total": 3,
    "dados": [{...}, {...}, {...}],   # todas as linhas
    "resumo": "3 conexões inativas detectadas",
    "data_geracao": "22/06/2026 às 14:30",
}
```

O template itera sobre `dados` com `{% for conexao in dados %}`.

**Modo individual**:
```python
# Para cada linha do resultado:
contexto = {
    **contexto_base,         # mesmo do consolidado
    **linha,                 # campos da linha específica (id, nome, tipo, etc)
    "data_geracao": "...",
}
```

O template acessa `{{ nome }}`, `{{ tipo }}` diretamente, sem precisar de um loop.

### Renderização

A função `renderizar_mensagens_consolidadas()` tenta renderizar cada template consolidado. Se um arquivo existe e o Jinja2 consegue compilar, o resultado é adicionado ao dict de saída:

```python
resultado = {}
# whatsapp
whatsapp = _renderizar_arquivo(pasta, "whatsapp_consolidado.txt", False, contexto)
if whatsapp:
    resultado["whatsapp"] = whatsapp
# email assunto
assunto = _renderizar_arquivo(pasta, "email_consolidado_assunto.txt", False, contexto)
if assunto:
    resultado["email_assunto"] = assunto
# email html
html = _renderizar_arquivo(pasta, "email_consolidado_html.html", True, contexto)
if html:
    resultado["email_html"] = html
```

### Autoescape

Templates `.html` têm autoescape ativado (proteção contra XSS). Templates `.txt` não têm — Markdown do WhatsApp não deve ser escapado.

## Fluxo completo

```
Orquestrador
  │
  ├─ detectar_capacidades_alerta("conexoes_inativas")
  │   └─ Retorna: tem_consolidado=True, canais=["whatsapp","email"]
  │
  ├─ renderizar_mensagens_consolidadas("conexoes_inativas", contexto)
  │   ├─ Tenta whatsapp_consolidado.txt → ✅ renderizado
  │   ├─ Tenta email_consolidado_assunto.txt → ✅ renderizado
  │   └─ Tenta email_consolidado_html.html → ✅ renderizado
  │
  └─ renderizar_mensagens_individuais("conexoes_inativas", contexto, linha)
      └─ Para cada uma das 3 linhas do resultado:
          ├─ Tenta whatsapp_individual.txt → ❌ não existe → pula
          ├─ Tenta email_individual_assunto.txt → ❌ não existe → pula
          └─ Tenta email_individual_html.html → ❌ não existe → pula
```

## Por que templates opcionais?

- **Simplicidade**: Um alerta simples (só WhatsApp) não precisa criar 6 arquivos, só 1
- **Extensibilidade**: Adicionar um novo canal (ex: Slack, SMS) é só adicionar um arquivo de template — zero mudanças no código
- **Descoberta**: O N8N pode inspecionar o payload e decidir quais canais usar baseado no que está disponível
