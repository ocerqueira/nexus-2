"""
Rotas de gerenciamento de usuários.
CRUD completo + busca por número WhatsApp (útil para n8n).
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


# =============================================================================
# Schemas
# =============================================================================


class CriarUsuario(BaseModel):
    """
    Cadastro de usuário do sistema.

    - **identificador**: chave única — use o número WhatsApp, email ou login AD
    - **origem**: `manual` (cadastro direto) | `whatsapp` | `ad_sync`
    - **whatsapp_numero**: número com DDI+DDD, ex: `5511999990001` (sem + ou espaços)
    """

    identificador: str = Field(
        ...,
        max_length=255,
        description="Chave única do usuário: número WhatsApp, email ou login AD",
        examples=["5511999990001"],
    )
    nome: str = Field(..., max_length=200, examples=["Lucas Cerqueira"])
    origem: str = Field(
        "manual",
        pattern="^(manual|whatsapp|ad_sync)$",
        description="`manual` | `whatsapp` | `ad_sync`",
    )
    email: str | None = Field(None, max_length=255, examples=["lucas@empresa.com"])
    telefone: str | None = Field(None, max_length=20, examples=["5511999990001"])
    whatsapp_numero: str | None = Field(
        None,
        max_length=20,
        description="Número com DDI+DDD sem espaços ou símbolos, ex: 5511999990001",
        examples=["5511999990001"],
    )
    departamento: str | None = Field(None, max_length=100, examples=["TI"])
    cargo: str | None = Field(None, max_length=100, examples=["Analista"])
    gestor_id: int | None = Field(None, description="ID do usuário gestor (opcional)")
    metadados: dict | None = Field(None, description="Campos extras livres (JSON)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "identificador": "5511999990001",
                "nome": "Lucas Cerqueira",
                "origem": "whatsapp",
                "whatsapp_numero": "5511999990001",
                "departamento": "TI",
            }
        }
    }


class AtualizarUsuario(BaseModel):
    """Atualização parcial — envie apenas os campos que deseja alterar."""

    nome: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=255)
    telefone: str | None = Field(None, max_length=20)
    whatsapp_numero: str | None = Field(None, max_length=20)
    departamento: str | None = Field(None, max_length=100)
    cargo: str | None = Field(None, max_length=100)
    gestor_id: int | None = None
    metadados: dict | None = None
    ativo: bool | None = Field(None, description="false = desativa usuário (soft delete)")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
def listar_usuarios(
    ativo: bool = Query(True),
    origem: str | None = Query(None, pattern="^(manual|whatsapp|ad_sync)$"),
) -> dict:
    consulta = """
        SELECT id, identificador, origem, nome, email, telefone,
               whatsapp_numero, departamento, cargo, gestor_id,
               ativo, criado_em, atualizado_em
        FROM usuarios WHERE 1=1
    """
    params: dict = {}

    if ativo is not None:
        consulta += " AND ativo = :ativo"
        params["ativo"] = ativo
    if origem:
        consulta += " AND origem = :origem"
        params["origem"] = origem

    consulta += " ORDER BY nome"

    with engine.connect() as conexao:
        resultado = conexao.execute(text(consulta), params).mappings().all()

    return {"total": len(resultado), "usuarios": [dict(r) for r in resultado]}


@router.get("/whatsapp/{numero}")
def buscar_por_whatsapp(numero: str) -> dict:
    """Busca usuário pelo número WhatsApp — endpoint principal para n8n."""
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("""
                    SELECT id, identificador, origem, nome, email, telefone,
                           whatsapp_numero, departamento, cargo, gestor_id,
                           ativo, criado_em, atualizado_em
                    FROM usuarios
                    WHERE whatsapp_numero = :numero AND ativo = TRUE
                """),
                {"numero": numero},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(
            status_code=404, detail=f"Usuário com WhatsApp '{numero}' não encontrado"
        )

    return dict(linha)


@router.get("/{usuario_id}")
def obter_usuario(usuario_id: int) -> dict:
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("""
                    SELECT id, identificador, origem, nome, email, telefone,
                           whatsapp_numero, departamento, cargo, gestor_id,
                           ativo, metadados, ultimo_sync, criado_em, atualizado_em
                    FROM usuarios WHERE id = :id
                """),
                {"id": usuario_id},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(status_code=404, detail=f"Usuário {usuario_id} não encontrado")

    return dict(linha)


@router.post("", status_code=201)
def criar_usuario(dados: CriarUsuario) -> dict:
    try:
        with engine.begin() as conexao:
            resultado = conexao.execute(
                text("""
                    INSERT INTO usuarios (
                        identificador, origem, nome, email, telefone,
                        whatsapp_numero, departamento, cargo, gestor_id, metadados
                    ) VALUES (
                        :identificador, :origem, :nome, :email, :telefone,
                        :whatsapp_numero, :departamento, :cargo, :gestor_id, :metadados
                    )
                    RETURNING id
                """),
                dados.model_dump(),
            )
            novo_id = resultado.scalar()
    except Exception as erro:
        if "usuarios_identificador_key" in str(erro):
            raise HTTPException(
                status_code=409,
                detail=f"Identificador '{dados.identificador}' já existe",
            )
        raise

    logger.info(f"Usuário {novo_id} criado: {dados.nome}")
    return {"status": "criado", "id": novo_id}


@router.patch("/{usuario_id}")
def atualizar_usuario(usuario_id: int, dados: AtualizarUsuario) -> dict:
    atualizacoes = dados.model_dump(exclude_unset=True)

    if not atualizacoes:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    set_clausulas = [f"{campo} = :{campo}" for campo in atualizacoes]
    set_clausulas.append("atualizado_em = NOW()")

    params = {**atualizacoes, "id": usuario_id}
    sql = f"UPDATE usuarios SET {', '.join(set_clausulas)} WHERE id = :id"

    with engine.begin() as conexao:
        resultado = conexao.execute(text(sql), params)

    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Usuário {usuario_id} não encontrado")

    logger.info(f"Usuário {usuario_id} atualizado")
    return {"status": "atualizado", "id": usuario_id}


@router.delete("/{usuario_id}")
def desativar_usuario(usuario_id: int) -> dict:
    """Soft delete — marca ativo = FALSE."""
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("""
                UPDATE usuarios SET ativo = FALSE, atualizado_em = NOW()
                WHERE id = :id AND ativo = TRUE
            """),
            {"id": usuario_id},
        )

    if resultado.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário {usuario_id} não encontrado ou já inativo",
        )

    logger.info(f"Usuário {usuario_id} desativado")
    return {"status": "desativado", "id": usuario_id}
