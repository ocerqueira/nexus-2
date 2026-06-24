# Tutorial — Primeira execução

**Objetivo**: Subir o Nexus pela primeira vez com Docker, configurar o `.env` e verificar que o sistema está funcionando.

**Duração esperada**: 10 minutos

**Pré-requisitos**: Docker e Docker Compose instalados.

---

## 1. Clone o projeto e entre na pasta

```bash
git clone <repositorio> nexus-2
cd nexus-2
```

## 2. Suba o banco de dados

O Nexus usa PostgreSQL. O `docker-compose.yml` já contém a definição:

```bash
docker compose up -d postgres
```

Aguarde o healthcheck ficar saudável (cerca de 10 segundos):

```bash
docker compose ps
```

Você deve ver o container `nexus-postgres` com status `healthy`.

## 3. Configure o arquivo `.env`

Crie um arquivo `.env` na raiz do projeto:

```bash
# .env
AMBIENTE=desenvolvimento
DEBUG=true

# URL do banco de dados interno (PostgreSQL do Docker)
DATABASE_URL=postgresql+psycopg://nexus_admin:nexus_dev_2024@localhost:55432/nexus

# Chave de criptografia (gere uma nova com o comando abaixo)
CHAVE_CRIPTOGRAFIA=<sua-chave-aqui>
```

Para gerar a chave de criptografia:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copie o valor gerado para `CHAVE_CRIPTOGRAFIA`.

## 4. Instale as dependências

```bash
uv sync
```

Isso instala todas as dependências listadas no `pyproject.toml`, incluindo FastAPI, SQLAlchemy, Jinja2 e WeasyPrint.

## 5. Execute o Nexus

```bash
uv run uvicorn main:app --reload --port 8000
```

Você verá logs como:

```
INFO | Iniciando Nexus...
INFO | Garantindo estrutura do banco (3 arquivo(s) SQL)...
INFO | Executando: 001_estrutura_inicial.sql
INFO | Executando: 002_chatbot_sessoes.sql
INFO | Executando: 003_timezone_agendamentos.sql
INFO | Estrutura do banco garantida.
INFO | Sincronizando filesystem com banco...
INFO | Relatórios: 5 ativos | +5 novos
INFO | Alertas: 2 ativos | +2 novos
INFO | Nexus pronto para receber requisições.
```

## 6. Verifique o health check

Acesse `http://localhost:8000/saude` no navegador ou use `curl`:

```bash
curl http://localhost:8000/saude
```

Resposta esperada:

```json
{
  "status": "ok",
  "servico": "nexus",
  "versao": "0.1.0",
  "ambiente": "desenvolvimento",
  "componentes": {
    "api": "ok",
    "banco_dados": "ok"
  }
}
```

## 7. Teste os endpoints de relatório e alerta

Liste os relatórios disponíveis:

```bash
curl http://localhost:8000/relatorios
```

Liste os alertas disponíveis:

```bash
curl http://localhost:8000/alertas
```

## Próximos passos

- [Criar um novo relatório](criando-novo-relatorio.md)
- [Adicionar uma conexão de banco externo](../guias-de-instrucao/adicionar-conexao.md)
- [Entender a arquitetura](../explicacao/arquitetura.md)
