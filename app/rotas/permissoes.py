"""
Rotas de gerenciamento de permissões.
Hard delete: revogar = DELETE (sem soft delete).
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/permissoes", tags=["permissoes"])


# =============================================================================
# Schemas
# =============================================================================


class CriarPermissao(BaseModel):
    """
    Concede acesso de um usuário a um relatório ou alerta específico.

    - **usuario_id**: ID do usuário (obtido em `GET /usuarios`)
    - **tipo_recurso**: `relatorio` ou `alerta`
    - **recurso_id**: ID do recurso — obtido em `GET /relatorios` ou `GET /alertas`
    - **pode_solicitar**: usuário pode pedir o relatório/alerta sob demanda
    - **pode_agendar**: usuário pode criar agendamentos automáticos
    - **limite_diario**: máximo de solicitações por dia (rate limit)

    Cada combinação (usuario + tipo + recurso) é única — tentativa duplicada retorna 409.
    """

    usuario_id: int = Field(..., description="ID do usuário (GET /usuarios)")
    tipo_recurso: str = Field(
        ...,
        pattern="^(relatorio|alerta)$",
        description="`relatorio` ou `alerta`",
    )
    recurso_id: int = Field(
        ...,
        description="ID do recurso — obtido em GET /relatorios ou GET /alertas",
    )
    pode_solicitar: bool = Field(True, description="Pode solicitar sob demanda")
    pode_agendar: bool = Field(False, description="Pode criar agendamentos automáticos")
    limite_diario: int = Field(10, ge=1, description="Máximo de solicitações por dia")

    model_config = {
        "json_schema_extra": {
            "example": {
                "usuario_id": 1,
                "tipo_recurso": "relatorio",
                "recurso_id": 1,
                "pode_solicitar": True,
                "pode_agendar": True,
                "limite_diario": 10,
            }
        }
    }


class AtualizarPermissao(BaseModel):
    """Atualização parcial — envie apenas os campos que deseja alterar."""

    pode_solicitar: bool | None = None
    pode_agendar: bool | None = None
    limite_diario: int | None = Field(None, ge=1, description="Novo limite diário")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
def listar_permissoes(
    usuario_id: int | None = Query(None),
    tipo_recurso: str | None = Query(None, pattern="^(relatorio|alerta)$"),
) -> dict:
    consulta = """
        SELECT p.id, p.usuario_id, u.nome AS usuario_nome,
               p.tipo_recurso, p.recurso_id,
               p.pode_solicitar, p.pode_agendar, p.limite_diario,
               p.criado_em
        FROM permissoes p
        JOIN usuarios u ON u.id = p.usuario_id
        WHERE 1=1
    """
    params: dict = {}

    if usuario_id is not None:
        consulta += " AND p.usuario_id = :usuario_id"
        params["usuario_id"] = usuario_id
    if tipo_recurso:
        consulta += " AND p.tipo_recurso = :tipo_recurso"
        params["tipo_recurso"] = tipo_recurso

    consulta += " ORDER BY u.nome, p.tipo_recurso, p.recurso_id"

    with engine.connect() as conexao:
        resultado = conexao.execute(text(consulta), params).mappings().all()

    return {"total": len(resultado), "permissoes": [dict(r) for r in resultado]}


@router.get("/verificar")
def verificar_permissao(
    usuario_id: int = Query(...),
    tipo_recurso: str = Query(..., pattern="^(relatorio|alerta)$"),
    recurso_id: int = Query(...),
) -> dict:
    """Verifica se usuário tem permissão para recurso específico — endpoint para n8n."""
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("""
                    SELECT id, pode_solicitar, pode_agendar, limite_diario
                    FROM permissoes
                    WHERE usuario_id = :usuario_id
                      AND tipo_recurso = :tipo_recurso
                      AND recurso_id = :recurso_id
                """),
                {
                    "usuario_id": usuario_id,
                    "tipo_recurso": tipo_recurso,
                    "recurso_id": recurso_id,
                },
            )
            .mappings()
            .first()
        )

    if not linha:
        return {
            "tem_permissao": False,
            "pode_solicitar": False,
            "pode_agendar": False,
            "limite_diario": 0,
        }

    return {
        "tem_permissao": True,
        "id": linha["id"],
        "pode_solicitar": linha["pode_solicitar"],
        "pode_agendar": linha["pode_agendar"],
        "limite_diario": linha["limite_diario"],
    }


@router.get("/{permissao_id}")
def obter_permissao(permissao_id: int) -> dict:
    with engine.connect() as conexao:
        linha = (
            conexao.execute(
                text("""
                    SELECT p.id, p.usuario_id, u.nome AS usuario_nome,
                           p.tipo_recurso, p.recurso_id,
                           p.pode_solicitar, p.pode_agendar, p.limite_diario,
                           p.criado_em
                    FROM permissoes p
                    JOIN usuarios u ON u.id = p.usuario_id
                    WHERE p.id = :id
                """),
                {"id": permissao_id},
            )
            .mappings()
            .first()
        )

    if not linha:
        raise HTTPException(status_code=404, detail=f"Permissão {permissao_id} não encontrada")

    return dict(linha)


@router.post("", status_code=201)
def criar_permissao(dados: CriarPermissao) -> dict:
    try:
        with engine.begin() as conexao:
            resultado = conexao.execute(
                text("""
                    INSERT INTO permissoes (
                        usuario_id, tipo_recurso, recurso_id,
                        pode_solicitar, pode_agendar, limite_diario
                    ) VALUES (
                        :usuario_id, :tipo_recurso, :recurso_id,
                        :pode_solicitar, :pode_agendar, :limite_diario
                    )
                    RETURNING id
                """),
                dados.model_dump(),
            )
            novo_id = resultado.scalar()
    except Exception as erro:
        if "uq_permissoes" in str(erro):
            raise HTTPException(
                status_code=409,
                detail=f"Permissão já existe para usuario_id={dados.usuario_id}, "
                       f"{dados.tipo_recurso} recurso_id={dados.recurso_id}",
            )
        if "usuarios_id_fkey" in str(erro) or 'fk' in str(erro).lower():
            raise HTTPException(status_code=404, detail=f"Usuário {dados.usuario_id} não encontrado")
        raise

    logger.info(
        f"Permissão {novo_id} criada: usuario={dados.usuario_id} "
        f"{dados.tipo_recurso} recurso={dados.recurso_id}"
    )
    return {"status": "criada", "id": novo_id}


@router.patch("/{permissao_id}")
def atualizar_permissao(permissao_id: int, dados: AtualizarPermissao) -> dict:
    atualizacoes = dados.model_dump(exclude_unset=True)

    if not atualizacoes:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    set_clausulas = [f"{campo} = :{campo}" for campo in atualizacoes]
    params = {**atualizacoes, "id": permissao_id}
    sql = f"UPDATE permissoes SET {', '.join(set_clausulas)} WHERE id = :id"

    with engine.begin() as conexao:
        resultado = conexao.execute(text(sql), params)

    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Permissão {permissao_id} não encontrada")

    logger.info(f"Permissão {permissao_id} atualizada")
    return {"status": "atualizada", "id": permissao_id}


@router.delete("/{permissao_id}")
def revogar_permissao(permissao_id: int) -> dict:
    """Hard delete — permissão removida permanentemente."""
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("DELETE FROM permissoes WHERE id = :id"),
            {"id": permissao_id},
        )

    if resultado.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Permissão {permissao_id} não encontrada")

    logger.info(f"Permissão {permissao_id} revogada")
    return {"status": "revogada", "id": permissao_id}
