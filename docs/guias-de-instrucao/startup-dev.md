# Guia — Startup completo do ambiente de desenvolvimento

**Objetivo**: Subir o Nexus localmente do zero e validar todo o fluxo — conexões, relatórios em todos os formatos, despachos e agendamentos.

Pré-requisito: Docker instalado e rodando.

---

## 1. Subir o ambiente

```bash
docker compose -f docker-compose.dev.yml up -d
```

Isso sobe três serviços:

| Container | Porta host | O que é |
|---|---|---|
| `nexus-api-dev` | 8099 | API Nexus |
| `nexus-postgres-dev` | 5433 | Banco interno do Nexus |
| `nexus-postgres-metas-dev` | 5434 | Banco de metas por vendedor (seed automático) |

Aguarde os healthchecks — o nexus só inicia após os dois postgres estarem prontos.

## 2. Verificar saúde

```bash
curl http://localhost:8099/saude
```

Resposta esperada:

```json
{
  "status": "ok",
  "componentes": { "api": "ok", "banco_dados": "ok" }
}
```

Se `banco_dados` estiver `"erro"`, aguarde mais alguns segundos e tente novamente.

---

## 3. Cadastrar conexões de banco

As conexões ficam na tabela `conexoes_bd` e são necessárias antes de executar qualquer relatório.
A API Key do ambiente dev é `nexus-redecorp-2024`.

### 3.1 Banco interno (obrigatório para `teste_conexoes` e `dashboard_conexoes`)

```bash
curl -X POST http://localhost:8099/conexoes \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "nexus_proprio",
    "tipo": "postgres",
    "host": "postgres",
    "porta": 5432,
    "banco": "nexus",
    "usuario": "nexus_admin",
    "senha": "local123",
    "observacoes": "Banco interno do Nexus (dev)"
  }'
```

### 3.2 ERP Firebird (obrigatório para `pedidos_por_vendedor`, `itens_comprimento_por_carga`, `desempenho_vendas`)

```bash
curl -X POST http://localhost:8099/conexoes \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "REPLICA_TERRA",
    "tipo": "firebird",
    "host": "host.docker.internal",
    "porta": 3050,
    "banco": "C:\\Users\\lucas\\Documents\\auditoria\\ERP.FDB",
    "usuario": "SYSDBA",
    "senha": "masterkey",
    "observacoes": "ERP Firebird local"
  }'
```

> `host.docker.internal` resolve para a máquina host — o Firebird precisa estar rodando localmente na porta 3050.

### 3.3 Banco de metas (obrigatório para `desempenho_vendas`)

```bash
curl -X POST http://localhost:8099/conexoes \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "nexus_metas",
    "tipo": "postgres",
    "host": "postgres-metas",
    "porta": 5432,
    "banco": "nexus_metas",
    "usuario": "metas_admin",
    "senha": "metas123",
    "observacoes": "Metas por vendedor (dev)"
  }'
```

Verificar se as três foram criadas:

```bash
curl http://localhost:8099/conexoes -H "X-Api-Key: nexus-redecorp-2024"
```

### Mapa conexão → relatório

| Conexão | Relatórios que dependem |
|---|---|
| `nexus_proprio` | `teste_conexoes`, `dashboard_conexoes` |
| `REPLICA_TERRA` | `pedidos_por_vendedor`, `itens_comprimento_por_carga`, `desempenho_vendas` |
| `nexus_metas` | `desempenho_vendas` |

---

## 4. Criar usuário para testes de despacho

Despachos precisam de um usuário com `whatsapp_numero` ou `email` preenchido.

```bash
curl -X POST http://localhost:8099/usuarios \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "identificador": "5544999990001",
    "nome": "Teste Dev",
    "email": "dev@nexus.local",
    "whatsapp_numero": "5544999990001"
  }'
```

Anote o `id` retornado — será usado nos passos de despacho e agendamento.

---

## 5. Testar relatórios

Liste os relatórios disponíveis:

```bash
curl http://localhost:8099/relatorios -H "X-Api-Key: nexus-redecorp-2024"
```

### Formatos disponíveis

Todos os relatórios aceitam `?formato=json|html|pdf|base64`.

#### JSON — dados estruturados

```bash
curl -X POST "http://localhost:8099/relatorios/teste_conexoes/solicitar?formato=json" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### HTML — visualização no browser

```bash
curl -X POST "http://localhost:8099/relatorios/teste_conexoes/solicitar?formato=html" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{}' -o relatorio.html
```

#### PDF — documento para download

```bash
curl -X POST "http://localhost:8099/relatorios/teste_conexoes/solicitar?formato=pdf" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{}' -o relatorio.pdf
```

#### base64 — PDF embutido em JSON (usado pelo N8N para email)

```bash
curl -X POST "http://localhost:8099/relatorios/teste_conexoes/solicitar?formato=base64" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Relatórios com parâmetros obrigatórios

#### `pedidos_por_vendedor`

```bash
curl -X POST "http://localhost:8099/relatorios/pedidos_por_vendedor/solicitar?formato=json" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"data_inicio": "2025-01-01", "data_fim": "2025-01-31"}}'
```

#### `desempenho_vendas` (multi-banco: Firebird + PostgreSQL)

```bash
curl -X POST "http://localhost:8099/relatorios/desempenho_vendas/solicitar?formato=json" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"cod_empresa": 1, "ano": 2025, "mes": 1}}'
```

#### `itens_comprimento_por_carga`

```bash
curl -X POST "http://localhost:8099/relatorios/itens_comprimento_por_carga/solicitar?formato=json" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{"parametros": {"data_inicio": "2025-01-01", "data_fim": "2025-06-30"}}'
```

---

## 6. Fluxo de despacho (simular o N8N)

O despacho é o mecanismo de entrega multicanal. O Nexus cria os registros; o N8N (ou qualquer consumidor) pollar a fila e executa o envio real.

### 6.1 Solicitar relatório com notificação

Adicione `?notificar=true&usuario_id=1` à URL:

```bash
curl -X POST "http://localhost:8099/relatorios/teste_conexoes/solicitar?formato=json&notificar=true&usuario_id=1" \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{}'
```

A resposta inclui o bloco `"despachos"` com os registros criados:

```json
{
  "status": "sucesso",
  "despachos": {
    "total_destinatarios": 1,
    "despachos": [
      { "id": 1, "status": "pendente", "canal": "whatsapp", "destino": "5544999990001" }
    ]
  }
}
```

### 6.2 Pollar despachos pendentes (endpoint do N8N)

```bash
curl "http://localhost:8099/despachos/pendentes" \
  -H "X-Api-Key: nexus-redecorp-2024"
```

O payload de cada despacho WhatsApp tem:

```json
{
  "canal": "whatsapp",
  "destino": "5544999990001",
  "payload": {
    "tipo": "pdf",
    "text": "Documento"
  },
  "relatorio_nome": "teste_conexoes"
}
```

O N8N usa `relatorio_nome` + `GET /relatorios/{nome}/solicitar?formato=pdf` para buscar o PDF e enviar via Evolution API.

### 6.3 Filtrar por canal

```bash
# Só WhatsApp
curl "http://localhost:8099/despachos/pendentes?canal=whatsapp" -H "X-Api-Key: nexus-redecorp-2024"

# Só email
curl "http://localhost:8099/despachos/pendentes?canal=email" -H "X-Api-Key: nexus-redecorp-2024"
```

### 6.4 Marcar como enviado (callback do N8N)

```bash
curl -X PATCH http://localhost:8099/despachos/1/status \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{"status": "enviado", "tentativas": 1}'
```

Status válidos: `enviado` | `falhou` | `confirmado` | `cancelado`

### 6.5 Registrar falha

```bash
curl -X PATCH http://localhost:8099/despachos/1/status \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{"status": "falhou", "erro": "Evolution API timeout", "tentativas": 1}'
```

### 6.6 Consultar histórico de despachos (admin)

```bash
# Todos
curl "http://localhost:8099/despachos" -H "X-Api-Key: nexus-redecorp-2024"

# Filtrar por status
curl "http://localhost:8099/despachos?status=enviado" -H "X-Api-Key: nexus-redecorp-2024"

# Filtrar por canal + relatório
curl "http://localhost:8099/despachos?canal=whatsapp&relatorio_nome=teste_conexoes" \
  -H "X-Api-Key: nexus-redecorp-2024"
```

---

## 7. Fluxo de agendamento (simular o N8N)

### 7.1 Criar agendamento

Consulte `GET /relatorios` para obter o `id` do relatório e `GET /usuarios` para o `id` do usuário.

#### Diário às 8h

```bash
curl -X POST http://localhost:8099/agendamentos \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": 1,
    "tipo_recurso": "relatorio",
    "recurso_id": 4,
    "frequencia": "diaria",
    "horarios": [{"hora": 8, "minuto": 0}],
    "canais": ["whatsapp"],
    "parametros": {}
  }'
```

#### Semanal toda segunda às 7h30 (só dias úteis)

```bash
curl -X POST http://localhost:8099/agendamentos \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": 1,
    "tipo_recurso": "relatorio",
    "recurso_id": 4,
    "frequencia": "semanal",
    "dia_semana": 1,
    "horarios": [{"hora": 7, "minuto": 30}],
    "apenas_dias_uteis": true,
    "canais": ["whatsapp"],
    "parametros": {}
  }'
```

#### A cada 10 minutos (útil para alertas)

```bash
curl -X POST http://localhost:8099/agendamentos \
  -H "X-Api-Key: nexus-redecorp-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "usuario_id": 1,
    "tipo_recurso": "relatorio",
    "recurso_id": 4,
    "frequencia": "intervalo",
    "intervalo_minutos": 10,
    "canais": ["whatsapp"],
    "parametros": {}
  }'
```

### 7.2 Pollar próximas execuções (endpoint do N8N — chama a cada minuto)

```bash
curl http://localhost:8099/agendamentos/proximas-execucoes \
  -H "X-Api-Key: nexus-redecorp-2024"
```

Retorna agendamentos cujo `proximo_envio` já passou. O N8N processa cada um e depois chama:

### 7.3 Marcar como executado (N8N chama após processar)

```bash
curl -X POST http://localhost:8099/agendamentos/1/marcar-executado \
  -H "X-Api-Key: nexus-redecorp-2024"
```

Isso atualiza `ultimo_envio` e recalcula `proximo_envio` automaticamente.

---

## 8. Testar modo de envio por email

Para despachos com canal `email`, o payload contém o PDF em base64. Primeiro configure um destinatário com email e canal `email` na tabela `relatorios_destinatarios`, ou passe `usuario_id` de um usuário com email cadastrado.

O despacho gerado terá:

```json
{
  "canal": "email",
  "destino": "dev@nexus.local",
  "payload": {
    "assunto": "Relatório: Teste Dev",
    "pdf_base64": "<base64>",
    "resumo": "..."
  }
}
```

---

## 9. Swagger UI

Todos os endpoints com documentação interativa:

```
http://localhost:8099/docs
```

Use o botão **Authorize** no topo e informe `nexus-redecorp-2024` como API Key.

---

## 10. Derrubar o ambiente

```bash
# Para os containers (preserva volumes/dados)
docker compose -f docker-compose.dev.yml down

# Para e apaga tudo (banco zerado no próximo up)
docker compose -f docker-compose.dev.yml down -v
```

---

**Ver também**:
- [Criando novo relatório](../tutoriais/criando-novo-relatorio.md)
- [Referência — API Rotas](../referencia/api-rotas.md)
- [Arquitetura — dispatch de alertas](../arquitetura-alertas-dispatch.md)
