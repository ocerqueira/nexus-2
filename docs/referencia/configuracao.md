# Referência — Configuração

## Variáveis de ambiente (`.env`)

O Nexus usa Pydantic Settings para carregar configurações do arquivo `.env`. Todas as variáveis são definidas na classe `Configuracoes` em `config.py`.

| Variável | Obrigatória | Padrão | Descrição |
|----------|-------------|--------|-----------|
| `AMBIENTE` | Não | `desenvolvimento` | Ambiente de execução |
| `DEBUG` | Não | `true` | Modo debug |
| `DATABASE_URL` | **Sim** | — | URL de conexão com o banco interno (formato SQLAlchemy) |
| `CHAVE_CRIPTOGRAFIA` | **Sim** | — | Chave Fernet de 44 caracteres Base64 para criptografia de senhas |
| `API_TITULO` | Não | `Nexus - Gerador de Relatórios` | Título da API na documentação OpenAPI |
| `API_VERSAO` | Não | `0.1.0` | Versão da API |
| `API_KEY` | Não | — | Chave de autenticação da API (se vazia, auth desabilitada) |
| `AD_SERVIDOR` | Não | — | URL do servidor LDAP (ex: `ldap://192.168.1.5`) |
| `AD_PORTA` | Não | `389` | Porta LDAP (389 plain, 636 LDAPS) |
| `AD_USAR_TLS` | Não | `false` | True para LDAPS na porta 636 |
| `AD_BIND_USER` | Não | — | DN completo do usuário de serviço |
| `AD_BIND_PASSWORD` | Não | — | Senha do bind LDAP |
| `AD_OU` | Não | — | OU padrão a sincronizar |

### Exemplo de `.env`

```bash
AMBIENTE=producao
DEBUG=false
DATABASE_URL=postgresql+psycopg://nexus_admin:senha_segura@db.empresa.com:5432/nexus
CHAVE_CRIPTOGRAFIA=abc123def456...=
```

---

## Conexão com banco interno (`app/bd.py`)

A engine SQLAlchemy principal é criada com os seguintes parâmetros:

```python
engine = create_engine(
    configuracoes.database_url,
    pool_pre_ping=True,   # Valida conexão antes de usar
    pool_size=5,          # Conexões mantidas no pool
    max_overflow=10,      # Conexões extras se o pool esgotar
)
```

---

## Gerenciador de conexões externas (`app/core/gerenciador_conexoes.py`)

O `GerenciadorConexoes` mantém um pool separado para cada conexão externa:

```python
novo_engine = create_engine(
    url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_recycle=3600,   # Recicla conexão após 1 hora
)
```

O gerenciador usa cache em dois níveis:
- **Cache de dados**: evita consultar a tabela `conexoes_bd` toda vez
- **Cache de engines**: reusa engines SQLAlchemy por conexão

---

## `config.json` dos relatórios e alertas

Cada pasta em `app/relatorios/` e `app/alertas/` deve conter um `config.json` com metadados.

### Schema — Relatório

```json
{
  "titulo": "string (obrigatório)",
  "descricao": "string (opcional)",
  "categoria": "string (opcional)",
  "parametros": [
    {
      "nome": "string",
      "tipo": "boolean | string | int",
      "obrigatorio": false,
      "padrao": "valor padrão",
      "rotulo": "Label amigável",
      "valores_permitidos": ["opcional", "array", "para enums"]
    }
  ]
}
```

### Schema — Alerta

```json
{
  "titulo": "string (obrigatório)",
  "descricao": "string (opcional)",
  "severidade": "info | aviso | critico",
  "parametros": [...]
}
```

---

## Docker Compose

O arquivo `docker-compose.yml` define o banco PostgreSQL:

| Configuração | Valor |
|-------------|-------|
| Imagem | `postgres:18-alpine` |
| Container | `nexus-postgres` |
| Banco | `nexus` |
| Usuário | `nexus_admin` |
| Senha | `nexus_dev_2024` |
| Porta | `55432` (host) → `5432` (container) |
| Volume | `nexus_postgres_dados` |

---

## Dependências Python (`pyproject.toml`)

| Pacote | Versão | Uso |
|--------|--------|-----|
| `fastapi[standard]` | ≥0.138.0 | Framework web |
| `sqlalchemy` | ≥2.0.51 | ORM e gerenciamento de conexões |
| `sqlalchemy-firebird` | ≥2.2.0 | Driver Firebird |
| `psycopg[binary]` | ≥3.3.4 | Driver PostgreSQL |
| `cryptography` | ≥49.0.0 | Criptografia Fernet |
| `jinja2` | ≥3.1.6 | Templates de mensagens e relatórios |
| `weasyprint` | ≥69.0 | Geração de PDF a partir de HTML |
| `matplotlib` | ≥3.10 | Gráficos em relatórios (barras, pizza, tendência) |
| `pandas` | ≥2.0 | Análise e transformação de dados |
| `ldap3` | ≥2.9 | Sincronização com Active Directory |
| `tzdata` | ≥2025.1 | Dados de timezone IANA |
| `pydantic-settings` | (transitiva) | Carregamento de `.env` |
