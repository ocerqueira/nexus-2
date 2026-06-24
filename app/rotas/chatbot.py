"""
Rotas de sessão do chatbot WhatsApp.
Persiste estado entre mensagens para navegação por menus.
"""

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class EstadoSessao(BaseModel):
    etapa: str = "idle"
    recurso_tipo: str | None = None
    recurso_nome: str | None = None
    parametros: dict = {}


@router.get("/sessao/{numero}")
def obter_sessao(numero: str) -> dict:
    with engine.connect() as conexao:
        row = conexao.execute(
            text("""
                SELECT etapa, recurso_tipo, recurso_nome, parametros
                FROM chatbot_sessoes WHERE numero = :numero
            """),
            {"numero": numero},
        ).mappings().first()

    if not row:
        return {"numero": numero, "etapa": "idle", "recurso_tipo": None, "recurso_nome": None, "parametros": {}}

    return {
        "numero": numero,
        "etapa": row["etapa"],
        "recurso_tipo": row["recurso_tipo"],
        "recurso_nome": row["recurso_nome"],
        "parametros": row["parametros"] or {},
    }


@router.put("/sessao/{numero}")
def atualizar_sessao(numero: str, estado: EstadoSessao) -> dict:
    with engine.begin() as conexao:
        conexao.execute(
            text("""
                INSERT INTO chatbot_sessoes (numero, etapa, recurso_tipo, recurso_nome, parametros, atualizado_em)
                VALUES (:numero, :etapa, :recurso_tipo, :recurso_nome, :parametros::jsonb, NOW())
                ON CONFLICT (numero) DO UPDATE SET
                    etapa = EXCLUDED.etapa,
                    recurso_tipo = EXCLUDED.recurso_tipo,
                    recurso_nome = EXCLUDED.recurso_nome,
                    parametros = EXCLUDED.parametros,
                    atualizado_em = NOW()
            """),
            {
                "numero": numero,
                "etapa": estado.etapa,
                "recurso_tipo": estado.recurso_tipo,
                "recurso_nome": estado.recurso_nome,
                "parametros": json.dumps(estado.parametros, ensure_ascii=False),
            },
        )
    return {"numero": numero, "etapa": estado.etapa}


@router.delete("/sessao/{numero}")
def limpar_sessao(numero: str) -> dict:
    with engine.begin() as conexao:
        conexao.execute(
            text("DELETE FROM chatbot_sessoes WHERE numero = :numero"),
            {"numero": numero},
        )
    return {"numero": numero, "etapa": "idle"}
