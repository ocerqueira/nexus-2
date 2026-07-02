# Guia — Gerar um relatório em PDF

**Problema**: Você precisa gerar um documento PDF a partir de um relatório do Nexus.

---

## 1. Escolha o relatório

Liste os relatórios disponíveis:

```bash
curl http://localhost:8000/relatorios
```

Exemplo de resposta:

```json
{
  "total": 2,
  "relatorios": [
    {"nome": "teste_conexoes", "titulo": "Teste de Conexões", "subtitulo": "Catálogo de conexões cadastradas no Nexus"},
    {"nome": "resumo_usuarios", "titulo": "Resumo de Usuários", "subtitulo": "Usuários cadastrados no sistema"}
  ]
}
```

## 2. Solicite o PDF

Use o endpoint `POST /relatorios/{nome}/solicitar` com o parâmetro `formato=pdf`:

```bash
curl -X POST "http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=pdf" \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"apenas_ativas": true}}' \
  --output relatorio.pdf
```

Parâmetros disponíveis na query string:

| Parâmetro | Valores | Padrão |
|-----------|---------|--------|
| `formato` | `json`, `html`, `pdf` | `json` |

O body da requisição (`parametros`) é opcional e depende dos parâmetros que o relatório aceita. Consulte o `config.json` de cada relatório para ver o que ele suporta.

## 3. Com parâmetros customizados

Exemplo filtrando por tipo de banco:

```bash
curl -X POST "http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=pdf" \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"apenas_ativas": false, "tipo_banco": "firebird"}}' \
  --output conexoes_firebird.pdf
```

## 4. Sem parâmetros (usa padrões)

```bash
curl -X POST "http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=pdf" \
  -H "Content-Type: application/json" \
  -d '{}' \
  --output relatorio.pdf
```

Cada processador define seus próprios valores padrão quando o parâmetro não é informado. No caso de `teste_conexoes`, o padrão é `apenas_ativas: true`.

## 5. Formatos alternativos

### JSON (dados estruturados)

```bash
curl -X POST "http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=json" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### HTML (para visualização)

Acesse no navegador:

```
http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=html
```

Ou com `curl`:

```bash
curl -X POST "http://localhost:8000/relatorios/teste_conexoes/solicitar?formato=html" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 6. Erros comuns

### 404 — Relatório não encontrado

A pasta `app/relatorios/{nome}/` não existe, falta o `config.json`, ou o `processador.py` não tem uma classe começando com `Processador`. Confira o log de startup — o sincronizador avisa pastas com contrato quebrado.

### 400 — Parâmetros inválidos

O processador rejeitou os parâmetros. Verifique os tipos e valores permitidos no `config.json` do relatório.

### 400 — Formato inválido

Use um dos formatos: `json`, `html`, `pdf`.

### 500 — Erro interno

Geralmente falha na query SQL. Verifique os logs da aplicação.

---

**Ver também**:
- [Referência — API Rotas](../referencia/api-rotas.md)
- [Tutorial — Criando um novo relatório](../tutoriais/criando-novo-relatorio.md)
