# Material de estudo — FastAPI, Pydantic e SQLAlchemy no Nexus

Este material cobre o básico das três bibliotecas usadas no Nexus, exatamente como elas aparecem no código do projeto. Cada conceito vem acompanhado de um trecho real do código-fonte.

---

## FastAPI

### O mínimo para uma API

```python
from fastapi import FastAPI

app = FastAPI(title="Minha API", version="0.1.0")

@app.get("/")
def raiz():
    return {"mensagem": "Olá, mundo"}
```

Arquivo real: `main.py` — o `app = FastAPI(...)` é idêntico.

### Router (organizar endpoints em arquivos separados)

```python
# app/rotas/saude.py
from fastapi import APIRouter

router = APIRouter(tags=["sistema"])

@router.get("/saude")
def verificar_saude():
    return {"status": "ok"}

# main.py — registra o router na aplicação principal
from app.rotas import saude
app.include_router(saude.router)
```

**Por que usar routers?** Cada arquivo em `app/rotas/` é um módulo independente. Se você adicionar um novo domínio (ex: `app/rotas/usuarios.py`), basta criar o router e dar `include_router` — o resto do sistema não muda.

### Prefixo no router

```python
router = APIRouter(prefix="/alertas", tags=["alertas"])
```

Todas as rotas desse router automaticamente começam com `/alertas`. Ex: `@router.get("")` vira `GET /alertas`.

### Path parameters (parâmetros na URL)

```python
@router.post("/{nome_alerta}/verificar")
def verificar_alerta(nome_alerta: str):
    # nome_alerta = "conexoes_inativas"
    ...
```

A URL `POST /alertas/conexoes_inativas/verificar` preenche `nome_alerta = "conexoes_inativas"`.

### Query parameters (parâmetros depois do `?`)

```python
from fastapi import Query

@router.post("/{nome_alerta}/verificar")
def verificar_alerta(
    nome_alerta: str,
    forcar: bool = Query(False, description="Ignora cooldown se True"),
):
    # URL: /alertas/conexoes_inativas/verificar?forcar=true
    ...
```

### Request body (corpo da requisição)

```python
from pydantic import BaseModel, Field

class RequisicaoAlerta(BaseModel):
    parametros: dict = Field(default_factory=dict)

@router.post("/{nome_alerta}/verificar")
def verificar_alerta(
    nome_alerta: str,
    requisicao: RequisicaoAlerta | None = None,
):
    params = requisicao.parametros if requisicao else {}
```

O corpo `{"parametros": {"incluir_observacoes": true}}` é validado automaticamente. Se o campo faltar, `parametros` recebe `{}` (padrão).

### HTTPException (erros HTTP)

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="Alerta não encontrado")
raise HTTPException(status_code=400, detail="Formato inválido")
raise HTTPException(status_code=500, detail=f"Erro: {erro}")
```

### Respostas especiais (HTML e PDF)

```python
from fastapi.responses import HTMLResponse, Response

# HTML
return HTMLResponse(content="<h1>Relatório</h1>")

# PDF (bytes)
return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={"Content-Disposition": "attachment; filename=relatorio.pdf"},
)
```

### Lifespan (inicialização e finalização)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    # Roda no startup
    garantir_estrutura_banco()
    sincronizar_filesystem_com_banco()
    yield
    # Roda no shutdown
    print("Encerrando...")

app = FastAPI(lifespan=ciclo_vida)
```

O código antes do `yield` roda na subida. O código depois do `yield` roda na descida.

---

## Pydantic

### BaseModel (modelos de requisição/resposta)

```python
from pydantic import BaseModel, Field

class RequisicaoRelatorio(BaseModel):
    parametros: dict = Field(default_factory=dict)

# Uso:
body = RequisicaoRelatorio(parametros={"apenas_ativas": True})
print(body.parametros)  # {"apenas_ativas": True}

# Com corpo vazio:
body = RequisicaoRelatorio()
print(body.parametros)  # {}
```

`Field(default_factory=dict)` garante que cada instância tenha seu próprio `{}`, em vez de compartilhar o mesmo objeto (armadilha clássica do Python com `default={}`).

### BaseSettings (variáveis de ambiente / .env)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Configuracoes(BaseSettings):
    ambiente: str = "desenvolvimento"
    database_url: str          # obrigatória
    chave_criptografia: str    # obrigatória

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

configuracoes = Configuracoes()  # lê .env automaticamente
```

**Funcionamento**: o Pydantic lê o arquivo `.env`, converte `CHAVE_CRIPTOGRAFIA` → `chave_criptografia` (case insensitive), e lança erro se campos obrigatórios estiverem faltando.

### Tipos compostos e opcionais

```python
parametros: dict = Field(default_factory=dict)       # dict com default
requisicao: RequisicaoAlerta | None = None            # opcional (Python 3.10+)
forcar: bool = Query(False)                           # bool com default
```

---

## SQLAlchemy

### Engine (conexão com o banco)

```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg://usuario:senha@localhost:5432/nexus",
    echo=False,           # não loga SQL
    pool_pre_ping=True,   # testa conexão antes de usar
    pool_size=5,          # 5 conexões mantidas abertas
    max_overflow=10,      # +10 extras sob demanda
)
```

Arquivo real: `app/bd.py`.

**pool_pre_ping=True** é importante: se o banco reiniciou, as conexões velhas são descartadas automaticamente.

### Executar SQL bruto (text)

```python
from sqlalchemy import text

with engine.begin() as conexao:       # begin() = transação automática
    conexao.execute(
        text("INSERT INTO relatorios (nome, titulo) VALUES (:nome, :titulo)"),
        {"nome": "novo", "titulo": "Meu Relatório"},
    )
```

**`engine.begin()`** vs **`engine.connect()`**:
- `begin()`: gerencia transação automaticamente. Se sair do `with` sem erro → commit. Se der exceção → rollback. Use para INSERT/UPDATE/DELETE.
- `connect()`: só conecta, sem transação explícita. Use para SELECT.

### Ler resultados como dicionário

```python
with engine.connect() as conexao:
    resultado = (
        conexao.execute(text("SELECT id, nome FROM alertas WHERE status = 'ativo'"))
        .mappings()                    # converte linhas para dict-like
        .all()                         # materializa todas as linhas
    )

# resultado = [{"id": 1, "nome": "conexoes_inativas"}, ...]
alertas = [dict(linha) for linha in resultado]
```

**Sem `.mappings()`**, cada linha é uma tupla (posicional). **Com `.mappings()`**, cada linha é um objeto que se comporta como dict. `dict(linha)` transforma em dict real.

### Pegar só a primeira linha

```python
resultado = (
    conexao.execute(text("SELECT * FROM alertas WHERE nome = :nome"), {"nome": "x"})
    .mappings()
    .first()   # None se não encontrou
)

if resultado:
    alerta = dict(resultado)
```

### Pegar valor escalar

```python
resultado = conexao.execute(text("SELECT 1")).scalar()
# resultado = 1
```

### Parâmetros com ANY (arrays PostgreSQL)

```python
conexao.execute(
    text("SELECT * FROM usuarios WHERE id = ANY(:ids)"),
    {"ids": [1, 2, 3]},
)
```

### Criar engine para bancos externos

O `GerenciadorConexoes` cria engines sob demanda:

```python
def _obter_engine(self, nome: str):
    if nome in self._cache_engines:
        return self._cache_engines[nome]   # reusa

    dados = self._buscar_dados_conexao(nome)  # busca no catálogo
    url = self._montar_url(dados)             # descriptografa senha, monta URL

    novo_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
        pool_recycle=3600,  # recicla conexões após 1 hora
    )
    self._cache_engines[nome] = novo_engine
    return novo_engine
```

**pool_recycle=3600**: útil para Firebird e MySQL, que podem derrubar conexões ociosas. Após 1 hora, a engine fecha e recria a conexão automaticamente.

### Executar query em engine externa

```python
engine_externo = self._obter_engine("erp_unidade_01")

with engine_externo.connect() as conn:
    resultado = conn.execute(
        text("SELECT * FROM vendas WHERE data = :data"),
        {"data": "2024-01-15"},
    )
    return [dict(linha) for linha in resultado.mappings()]
```

---

## Padrão completo: FastAPI + Pydantic + SQLAlchemy

Juntando tudo — o fluxo de um endpoint real do Nexus (`POST /alertas/{nome}/verificar`):

```python
# 1. Pydantic define o schema do body
class RequisicaoAlerta(BaseModel):
    parametros: dict = Field(default_factory=dict)

# 2. FastAPI expõe a rota
@router.post("/{nome_alerta}/verificar")
def verificar_alerta(
    nome_alerta: str,                              # path param
    requisicao: RequisicaoAlerta | None = None,     # body (opcional)
    forcar: bool = Query(False),                    # query param
):
    # 3. Descoberta automática do processador (convenção Processador* na pasta)
    processador_classe = carregar_processador("alerta", nome_alerta)
    if not processador_classe:
        raise HTTPException(status_code=404, detail=f"Alerta '{nome_alerta}' não encontrado")

    parametros = requisicao.parametros if requisicao else {}

    # 4. Busca dados no banco (via orquestrador)
    try:
        return orquestrar_alerta(nome_alerta, parametros, processador_classe, forcar)
    except AlertaNaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro))

# 5. O orquestrador usa SQLAlchemy internamente:
def _buscar_alerta_no_banco(nome_alerta: str):
    with engine.connect() as conexao:
        resultado = (
            conexao.execute(
                text("SELECT id, nome, titulo FROM alertas WHERE nome = :nome AND status = 'ativo'"),
                {"nome": nome_alerta},
            )
            .mappings()
            .first()
        )
    return dict(resultado) if resultado else None
```

---

## Resumo: o que você precisa lembrar

| Biblioteca | Para que serve no Nexus | Exemplo no código |
|-----------|------------------------|-------------------|
| **FastAPI** `APIRouter` | Organizar endpoints em arquivos | `app/rotas/saude.py`, `app/rotas/alertas.py` |
| **FastAPI** `Query` | Parâmetros de URL (`?forcar=true`) | `forcar: bool = Query(False)` |
| **FastAPI** `HTTPException` | Retornar erros HTTP (400, 404, 500) | `raise HTTPException(404, ...)` |
| **FastAPI** `lifespan` | Inicialização (banco, sync) | `main.py: ciclo_vida()` |
| **Pydantic** `BaseModel` | Validar corpo das requisições | `RequisicaoAlerta`, `RequisicaoRelatorio` |
| **Pydantic** `BaseSettings` | Carregar `.env` | `config.py: Configuracoes` |
| **SQLAlchemy** `create_engine` | Pool de conexões com o banco | `app/bd.py`, `gerenciador_conexoes.py` |
| **SQLAlchemy** `text()` | Escrever SQL com parâmetros `:nome` | Todas as queries do sistema |
| **SQLAlchemy** `.mappings().all()` | Resultados como lista de dicts | `_buscar_alerta_no_banco()` |
| **SQLAlchemy** `engine.begin()` | Transação automática | `INSERT/UPDATE` no sincronizador |
| **SQLAlchemy** `engine.connect()` | Conexão sem transação | `SELECT` no orquestrador |
