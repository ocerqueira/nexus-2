# Guia — Adicionar uma conexão de banco externo

**Problema**: Você precisa cadastrar uma nova conexão de banco de dados (PostgreSQL, Firebird ou MySQL) no catálogo do Nexus para que relatórios e alertas possam consultá-la.

---

## 1. Via API REST (recomendado)

A forma mais simples é usar o endpoint `POST /conexoes`. A senha é criptografada automaticamente:

```bash
curl -X POST http://localhost:8000/conexoes \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sua-api-key" \
  -d '{
    "nome": "erp_unidade_sp",
    "tipo": "firebird",
    "host": "192.168.1.10",
    "porta": 3050,
    "banco": "/dados/erp/ERP_SP.FDB",
    "usuario": "SYSDBA",
    "senha": "masterkey",
    "observacoes": "ERP da unidade São Paulo"
  }'
```

Resposta: `{"status": "criada", "id": 1}`

## 2. Via Painel Admin

Acesse `http://localhost:8000/admin`, vá na aba **Conexões** e preencha o formulário. A senha é criptografada automaticamente ao salvar.

## 3. Via SQL direto (avançado)

Se preferir inserir manualmente no banco, criptografe a senha primeiro:

```bash
uv run python -c "
from app.core.criptografia import criptografar
print(criptografar('sua-senha-aqui'))
"
```

Depois insira no banco:

```sql
INSERT INTO conexoes_bd (nome, tipo, host, porta, banco, usuario, senha_criptografada, observacoes)
VALUES (
  'erp_unidade_sp',
  'firebird',
  '192.168.1.10',
  3050,
  '/dados/erp/ERP_SP.FDB',
  'SYSDBA',
  '<valor-criptografado>',
  'ERP da unidade São Paulo — Firebird 2.5, multiempresa'
);
```

Campos obrigatórios: `nome`, `tipo`, `host`, `porta`, `banco`, `usuario`, `senha_criptografada`.

## 4. Tipos suportados

| Tipo | Driver SQLAlchemy | Porta padrão |
|------|-------------------|--------------|
| `postgres` | `psycopg` | 5432 |
| `firebird` | `firebird` | 3050 |
| `mysql` | `mysqlconnector` | 3306 |

Os tipos são validados pela constraint `chk_conexoes_tipo` no banco.

## 5. Teste a conexão

Use o script Python:

```bash
uv run python -c "
from app.core.gerenciador_conexoes import gerenciador_conexoes
resultado = gerenciador_conexoes.testar_conexao('erp_unidade_sp')
print(resultado)
"
```

Resposta esperada em caso de sucesso:

```json
{"status": "ok", "mensagem": "Conexão validada com sucesso"}
```

## 6. (Opcional) Vincule a um grupo

Se quiser que a conexão apareça em relatórios filtrados por grupo:

```sql
-- Crie o grupo se não existir
INSERT INTO grupos_conexoes (nome, descricao)
VALUES ('unidades_erp', 'Todas as unidades do ERP');

-- Vincule a conexão ao grupo
INSERT INTO grupos_conexoes_itens (grupo_id, conexao_id)
SELECT g.id, c.id
FROM grupos_conexoes g, conexoes_bd c
WHERE g.nome = 'unidades_erp' AND c.nome = 'erp_unidade_sp';
```

## 7. Limpe o cache

Se a aplicação já estava rodando, limpe o cache de conexões para forçar a releitura:

```bash
# Via API
curl -X POST http://localhost:8000/admin/conexoes/{id}/limpar-cache

# Ou via painel admin: clique no botão "Limpar Cache" na linha da conexão
```

---

**Ver também**:
- [Referência — Banco de dados](../referencia/banco-de-dados.md) — esquema da tabela `conexoes_bd`
- [Explicação — Modelo de segurança](../explicacao/modelo-de-seguranca.md) — detalhes da criptografia
