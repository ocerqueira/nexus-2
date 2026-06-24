"""
Rotas de gerenciamento de conexões a bancos externos.
Senhas nunca retornam nas respostas — armazenadas criptografadas (Fernet).
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.bd import engine
from app.core.criptografia import criptografar
from app.core.gerenciador_conexoes import gerenciador_conexoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conexoes", tags=["conexoes"])


# =============================================================================
# Schemas
# =============================================================================


class CriarConexao(BaseModel):
    """
    Conexão a banco de dados externo (ERP, legado, etc).

    A senha é **criptografada automaticamente** antes de salvar — nunca fica em texto puro.
    Respostas de listagem nunca retornam a senha.

    - **nome**: identificador único interno, ex: `erp_principal`, `filial_sp`
    - **tipo**: `firebird` | `postgres` | `mysql`
    - **banco**: para Firebird, caminho do arquivo `.fdb` no servidor; para Postgres/MySQL, nome do database
    - **porta**: Firebird=3050, Postgres=5432, MySQL=3306
    """

    nome: str = Field(
        ...,
        max_length=100,
        description="Identificador único, ex: erp_principal, filial_sp",
        examples=["erp_principal"],
    )
    tipo: str = Field(
        ...,
        pattern="^(firebird|postgres|mysql)$",
        description="Tipo do banco: `firebird` | `postgres` | `mysql`",
    )
    host: str = Field(..., max_length=255, description="IP ou hostname do servidor", examples=["192.168.1.10"])
    porta: int = Field(..., description="Porta: Firebird=3050, Postgres=5432, MySQL=3306", examples=[3050])
    banco: str = Field(
        ...,
        max_length=500,
        description="Firebird: caminho do .fdb no servidor. Postgres/MySQL: nome do database.",
        examples=["/dados/empresa.fdb"],
    )
    usuario: str = Field(..., max_length=100, examples=["SYSDBA"])
    senha: str = Field(..., description="Senha em texto puro — será criptografada antes de salvar")
    observacoes: str | None = Field(None, description="Anotações livres (versão, finalidade, etc)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "nome": "erp_principal",
                "tipo": "firebird",
                "host": "192.168.1.10",
                "porta": 3050,
                "banco": "/dados/empresa.fdb",
                "usuario": "SYSDBA",
                "senha": "masterkey",
                "observacoes": "ERP principal - Firebird 5.0",
            }
        }
    }


class AtualizarConexao(BaseModel):
    """Atualização parcial — envie apenas os campos que deseja alterar. Se enviar `senha`, será recriptografada."""

    nome: str | None = Field(None, max_length=100)
    host: str | None = Field(None, max_length=255)
    porta: int | None = None
    banco: str | None = Field(None, max_length=500)
    usuario: str | None = Field(None, max_length=100)
    senha: str | None = Field(None, description="Nova senha em texto puro — será recriptografada")
    observacoes: str | None = None
    ativo: bool | None = Field(None, description="false = desativa conexão (soft delete)")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
def listar_conexoes(
    tipo: str | None = Query(None, pattern="^(firebird|postgres|mysql)$"),
    ativo: bool = Query(True),
) -> dict:
    consulta = """
        SELECT id, nome, tipo, host, porta, banco, usuario,
               observacoes, ativo, criado_em, atualizado_em
        FROM conexoes_bd WHERE 1=1
    """
    params: dict = {}

    if ativo is not None:
        consulta += " AND ativo = :ativo"
        params["ativo"] = ativo
    if tipo:
        consulta += " AND tipo = :tipo"
        params["tipo"] = tipo

    consulta += " ORDER BY nome"

    with engine.connect() as conexao:
        resultado = conexao.execute(text(consulta), params).mappings().all()

    return {"total": len(resultado), "conexoes": [dict(r) for r in resultado]}


@router.get("/{conexao_id}")
def obter_conexao(conexao_id: int) -> dict:
    """Retorna conexão sem a senha."""
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("""
                    SELECT id, nome, tipo, host, porta, banco, usuario,
                           observacoes, ativo, criado_em, atualizado_em
                    FROM conexoes_bd WHERE id = :id
                """),
                {"id": conexao_id},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(status_code=404, detail=f"Conexão {conexao_id} não encontrada")

    return dict(linha)


@router.post("", status_code=201)
def criar_conexao(dados: CriarConexao) -> dict:
    senha_criptografada = criptografar(dados.senha)

    try:
        with engine.begin() as conexao:
            resultado = conexao.execute(
                text("""
                    INSERT INTO conexoes_bd (
                        nome, tipo, host, porta, banco,
                        usuario, senha_criptografada, observacoes
                    ) VALUES (
                        :nome, :tipo, :host, :porta, :banco,
                        :usuario, :senha_criptografada, :observacoes
                    )
                    RETURNING id
                """),
                {
                    "nome": dados.nome,
                    "tipo": dados.tipo,
                    "host": dados.host,
                    "porta": dados.porta,
                    "banco": dados.banco,
                    "usuario": dados.usuario,
                    "senha_criptografada": senha_criptografada,
                    "observacoes": dados.observacoes,
                },
            )
            novo_id = resultado.scalar()
    except Exception as erro:
        if "conexoes_bd_nome_key" in str(erro):
            raise HTTPException(
                status_code=409, detail=f"Conexão '{dados.nome}' já existe"
            )
        raise

    logger.info(f"Conexão {novo_id} criada: {dados.nome} ({dados.tipo})")
    return {"status": "criada", "id": novo_id}


@router.patch("/{conexao_id}")
def atualizar_conexao(conexao_id: int, dados: AtualizarConexao) -> dict:
    atualizacoes = dados.model_dump(exclude_unset=True)

    if not atualizacoes:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Criptografa senha se enviada
    if "senha" in atualizacoes:
        atualizacoes["senha_criptografada"] = criptografar(atualizacoes.pop("senha"))

    set_clausulas = [f"{campo} = :{campo}" for campo in atualizacoes]
    set_clausulas.append("atualizado_em = NOW()")

    params = {**atualizacoes, "id": conexao_id}
    sql = f"UPDATE conexoes_bd SET {', '.join(set_clausulas)} WHERE id = :id"

    with engine.begin() as conexao:
        resultado = conexao.execute(text(sql), params)

    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Conexão {conexao_id} não encontrada")

    logger.info(f"Conexão {conexao_id} atualizada")
    return {"status": "atualizada", "id": conexao_id}


@router.get("/{conexao_id}/testar")
def testar_conexao(conexao_id: int) -> dict:
    """Testa se a conexão está acessível executando SELECT 1."""
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("SELECT nome FROM conexoes_bd WHERE id = :id AND ativo = TRUE"),
                {"id": conexao_id},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(status_code=404, detail=f"Conexão {conexao_id} não encontrada")

    resultado = gerenciador_conexoes.testar_conexao(linha["nome"])

    if resultado["status"] == "erro":
        raise HTTPException(status_code=502, detail=resultado["mensagem"])

    return resultado


@router.post("/{conexao_id}/limpar-cache")
def limpar_cache_conexao(conexao_id: int) -> dict:
    """Limpa cache em memória de uma conexão (necessário após alterar senha/host)."""
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("SELECT nome FROM conexoes_bd WHERE id = :id"),
                {"id": conexao_id},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(status_code=404, detail=f"Conexão {conexao_id} não encontrada")

    gerenciador_conexoes.limpar_cache(linha["nome"])
    logger.info(f"Cache limpo para conexão {conexao_id} ({linha['nome']})")
    return {"status": "cache_limpo", "conexao": linha["nome"]}


@router.delete("/{conexao_id}")
def desativar_conexao(conexao_id: int) -> dict:
    """Soft delete — marca ativo = FALSE."""
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("""
                UPDATE conexoes_bd SET ativo = FALSE, atualizado_em = NOW()
                WHERE id = :id AND ativo = TRUE
            """),
            {"id": conexao_id},
        )

    if resultado.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Conexão {conexao_id} não encontrada ou já inativa",
        )

    logger.info(f"Conexão {conexao_id} desativada")
    return {"status": "desativada", "id": conexao_id}
