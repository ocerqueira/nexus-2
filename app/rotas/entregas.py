"""
Rotas de entregas.

GET  /entregas/pendentes    — N8N polling: busca entregas prontas para envio
PATCH /entregas/{id}/status — N8N callback: atualiza status após envio/falha
GET  /entregas              — Admin: listagem com filtros
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.bd import engine

_UTC = ZoneInfo("UTC")
_TZ_SP = ZoneInfo("America/Sao_Paulo")
_CAMPOS_DT = ("enviar_apos", "enviado_em", "criado_em")


def _para_iso_local(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(_TZ_SP).isoformat()


def _converter_dt(row: dict) -> dict:
    for campo in _CAMPOS_DT:
        if campo in row:
            row[campo] = _para_iso_local(row[campo])
    return row

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entregas", tags=["entregas"])


# ─────────────────────────────────────────────────────────────────────────────
# N8N: polling de pendentes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pendentes")
def listar_pendentes(
    limite: int = Query(50, ge=1, le=200, description="Máximo de entregas a retornar por chamada"),
    canal:  str | None = Query(None, description="Filtrar por canal: whatsapp | email"),
    incluir_retry: bool = Query(False, description="Se True, inclui falhos com menos de 3 tentativas nas últimas 24h"),
) -> dict:
    """
    Retorna entregas prontas para envio.

    Retorna: status='pendente' com enviar_apos <= NOW() (ou NULL).
    Com incluir_retry=true: também retorna status='falhou' com tentativas < 3
    e criado nas últimas 24h (re-fila automática de falhas transitórias).
    """
    filtro_canal = "AND canal = :canal" if canal else ""
    filtro_retry = """
        OR (
            d.status = 'falhou'
            AND d.tentativas < 3
            AND d.criado_em > NOW() - INTERVAL '24 hours'
        )
    """ if incluir_retry else ""

    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT
                d.id,
                d.canal,
                d.destino,
                d.payload,
                d.status         AS status_atual,
                d.tentativas,
                d.enviar_apos,
                d.criado_em,
                d.acao_requerida,
                a.nome  AS alerta_nome,
                r.nome  AS relatorio_nome
            FROM entregas d
            LEFT JOIN alertas    a ON a.id = d.alerta_id
            LEFT JOIN relatorios r ON r.id = d.relatorio_id
            WHERE (
                (d.status = 'pendente' AND (d.enviar_apos IS NULL OR d.enviar_apos <= NOW()))
                {filtro_retry}
            )
            {filtro_canal}
            ORDER BY d.criado_em ASC
            LIMIT :limite
        """), {"limite": limite, "canal": canal}).mappings().all()

    return {
        "total": len(rows),
        "entregas": [_converter_dt(dict(r)) for r in rows],
    }


# ─────────────────────────────────────────────────────────────────────────────
# N8N: callback de status
# ─────────────────────────────────────────────────────────────────────────────

class AtualizarStatusBody(BaseModel):
    status:      str
    erro:        str | None = None
    tentativas:  int | None = None


@router.patch("/{entrega_id}/status")
def atualizar_status(
    entrega_id: int,
    body: AtualizarStatusBody,
) -> dict:
    """
    Atualiza status de uma entrega após tentativa de envio pelo N8N.

    Status válidos: enviado | falhou | confirmado | cancelado
    """
    status_validos = {"enviado", "falhou", "confirmado", "cancelado"}
    if body.status not in status_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido. Use: {sorted(status_validos)}",
        )

    with engine.connect() as c:
        existe = c.execute(
            text("SELECT id FROM entregas WHERE id = :id"),
            {"id": entrega_id},
        ).scalar()

    if not existe:
        raise HTTPException(status_code=404, detail=f"Entrega {entrega_id} não encontrada")

    agora = datetime.utcnow()
    campos = {"id": entrega_id, "status": body.status, "agora": agora}
    sets = ["status = :status"]

    if body.status == "enviado":
        sets.append("enviado_em = :agora")
        sets.append("ultimo_erro = NULL")

    if body.erro is not None:
        sets.append("ultimo_erro = :erro")
        campos["erro"] = body.erro

    if body.tentativas is not None:
        sets.append("tentativas = :tentativas")
        campos["tentativas"] = body.tentativas

    with engine.begin() as c:
        c.execute(
            text(f"UPDATE entregas SET {', '.join(sets)} WHERE id = :id"),
            campos,
        )

    logger.info(f"Entrega {entrega_id} → {body.status}")
    return {"id": entrega_id, "status": body.status}


# ─────────────────────────────────────────────────────────────────────────────
# Admin: listagem com filtros
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def listar_entregas(
    status:        str | None = Query(None),
    canal:         str | None = Query(None),
    alerta_nome:   str | None = Query(None),
    relatorio_nome: str | None = Query(None),
    pagina:        int = Query(1, ge=1),
    por_pagina:    int = Query(25, ge=1, le=100),
) -> dict:
    """Lista entregas com filtros e paginação para o admin panel."""
    filtros = []
    params: dict = {"limite": por_pagina, "offset": (pagina - 1) * por_pagina}

    if status:
        filtros.append("d.status = :status")
        params["status"] = status
    if canal:
        filtros.append("d.canal = :canal")
        params["canal"] = canal
    if alerta_nome:
        filtros.append("a.nome = :alerta_nome")
        params["alerta_nome"] = alerta_nome
    if relatorio_nome:
        filtros.append("r.nome = :relatorio_nome")
        params["relatorio_nome"] = relatorio_nome

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    with engine.connect() as c:
        total = c.execute(text(f"""
            SELECT COUNT(*) FROM entregas d
            LEFT JOIN alertas    a ON a.id = d.alerta_id
            LEFT JOIN relatorios r ON r.id = d.relatorio_id
            {where}
        """), params).scalar()

        rows = c.execute(text(f"""
            SELECT
                d.id, d.canal, d.destino, d.status,
                d.tentativas, d.ultimo_erro,
                d.enviar_apos, d.enviado_em, d.criado_em,
                d.acao_requerida,
                u.nome  AS destinatario_nome,
                a.nome  AS alerta_nome,
                r.nome  AS relatorio_nome
            FROM entregas d
            LEFT JOIN usuarios   u ON u.id = d.usuario_id
            LEFT JOIN alertas    a ON a.id = d.alerta_id
            LEFT JOIN relatorios r ON r.id = d.relatorio_id
            {where}
            ORDER BY d.criado_em DESC
            LIMIT :limite OFFSET :offset
        """), params).mappings().all()

    return {
        "total":    total,
        "pagina":   pagina,
        "por_pagina": por_pagina,
        "entregas": [_converter_dt(dict(r)) for r in rows],
    }
