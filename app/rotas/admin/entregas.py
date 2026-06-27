import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ._base import engine, templates, text, _formatar_datetime, _ENTREGAS_POR_PAGINA, _HIST_POR_PAGINA

router = APIRouter()


def _entregas_db(status: str = "", canal: str = "", busca: str = "",
                  pagina: int = 1) -> tuple[list[dict], int]:
    filtros = ["1=1"]
    params: dict = {"lim": _ENTREGAS_POR_PAGINA, "off": (pagina - 1) * _ENTREGAS_POR_PAGINA}
    if status:
        filtros.append("d.status = :status")
        params["status"] = status
    if canal:
        filtros.append("d.canal = :canal")
        params["canal"] = canal
    if busca:
        filtros.append("(al.nome ILIKE :b OR rel.nome ILIKE :b OR u.nome ILIKE :b OR d.destino ILIKE :b)")
        params["b"] = f"%{busca}%"
    where = " AND ".join(filtros)
    with engine.connect() as c:
        total = c.execute(text(f"""
            SELECT COUNT(*) FROM entregas d
            LEFT JOIN alertas al ON al.id = d.alerta_id
            LEFT JOIN relatorios rel ON rel.id = d.relatorio_id
            LEFT JOIN usuarios u ON u.id = d.usuario_id
            WHERE {where}
        """), params).scalar() or 0
        rows = c.execute(text(f"""
            SELECT d.id, d.canal, d.destino, d.status, d.tentativas,
                   d.enviar_apos, d.criado_em, d.ultimo_erro,
                   al.nome AS alerta_nome, rel.nome AS relatorio_nome,
                   u.nome AS usuario_nome
            FROM entregas d
            LEFT JOIN alertas al ON al.id = d.alerta_id
            LEFT JOIN relatorios rel ON rel.id = d.relatorio_id
            LEFT JOIN usuarios u ON u.id = d.usuario_id
            WHERE {where}
            ORDER BY d.criado_em DESC
            LIMIT :lim OFFSET :off
        """), params).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        d["criado_em_fmt"] = _formatar_datetime(d["criado_em"])
        d["enviar_apos_fmt"] = _formatar_datetime(d.get("enviar_apos"))
        d["recurso_nome"] = d.get("alerta_nome") or d.get("relatorio_nome") or "—"
        d["recurso_tipo"] = "alerta" if d.get("alerta_nome") else ("relatorio" if d.get("relatorio_nome") else "—")
        err = str(d.get("ultimo_erro") or "")
        d["erro_resumo"] = (err[:60] + "…") if len(err) > 60 else err
        result.append(d)
    return result, total


def _historico_db(tipo: str = "", status: str = "", busca: str = "",
                  periodo: str = "", pagina: int = 1) -> tuple[list[dict], int]:
    filtros = ["1=1"]
    params: dict = {"lim": _HIST_POR_PAGINA, "off": (pagina - 1) * _HIST_POR_PAGINA}
    if tipo:
        filtros.append("h.tipo_recurso = :tipo")
        params["tipo"] = tipo
    if status:
        filtros.append("h.status = :status")
        params["status"] = status
    if busca:
        filtros.append("h.recurso_nome ILIKE :busca")
        params["busca"] = f"%{busca}%"
    if periodo == "hoje":
        filtros.append("h.criado_em >= CURRENT_DATE")
    elif periodo == "semana":
        filtros.append("h.criado_em >= NOW() - INTERVAL '7 days'")
    elif periodo == "mes":
        filtros.append("h.criado_em >= NOW() - INTERVAL '30 days'")
    where = " AND ".join(filtros)
    with engine.connect() as c:
        total = c.execute(text(f"SELECT COUNT(*) FROM historico h WHERE {where}"), params).scalar() or 0
        rows = c.execute(text(f"""
            SELECT h.id, h.tipo_recurso, h.recurso_nome, h.tipo_solicitacao,
                   h.status, h.mensagem_erro, h.parametros, h.tamanho_arquivo,
                   h.hash_arquivo, h.enviado_para, h.criado_em, u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            WHERE {where} ORDER BY h.criado_em DESC LIMIT :lim OFFSET :off
        """), params).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        d["criado_em_fmt"] = _formatar_datetime(d["criado_em"])
        d["criado_em_date"] = d["criado_em"].strftime("%d/%m/%Y") if d.get("criado_em") else "—"
        err = str(d.get("mensagem_erro") or "")
        d["erro_resumo"] = (err[:80] + "…") if err else ""
        result.append(d)
    return result, total


@router.get("/entregas", response_class=HTMLResponse)
def admin_entregas_view(request: Request,
                         status: str = Query(""),
                         canal: str = Query(""),
                         busca: str = Query(""),
                         pagina: int = Query(1, ge=1)):
    registros, total = _entregas_db(status, canal, busca, pagina)
    return templates.TemplateResponse(request, "admin/entregas.html", {
        "registros": registros, "total": total,
        "status": status, "canal": canal, "busca": busca,
        "pagina": pagina,
        # -(-total // limit) = divisão inteira com arredondamento para cima (teto)
        "total_paginas": max(1, -(-total // _ENTREGAS_POR_PAGINA)),
    })


@router.get("/historico", response_class=HTMLResponse)
def admin_historico(request: Request,
                    tipo: str = Query(""),
                    status: str = Query(""),
                    busca: str = Query(""),
                    periodo: str = Query(""),
                    pagina: int = Query(1, ge=1)):
    registros, total = _historico_db(tipo, status, busca, periodo, pagina)
    return templates.TemplateResponse(request, "admin/historico.html", {
        "registros": registros, "total": total,
        "tipo": tipo, "status": status, "busca": busca, "periodo": periodo,
        "pagina": pagina, "total_paginas": max(1, -(-total // _HIST_POR_PAGINA)),
        "msg": "", "msg_tipo": "",
    })


@router.get("/historico/{registro_id}/detalhe", response_class=HTMLResponse)
def admin_historico_detalhe(request: Request, registro_id: int):
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT h.*, u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            WHERE h.id = :id
        """), {"id": registro_id}).mappings().first()
    if not row:
        return HTMLResponse("")
    h = dict(row)
    h["criado_em_fmt"] = _formatar_datetime(h.get("criado_em"))
    try:
        h["parametros_fmt"] = json.dumps(h["parametros"], ensure_ascii=False, indent=2) if h.get("parametros") else ""
    except Exception:
        h["parametros_fmt"] = str(h.get("parametros", ""))
    return templates.TemplateResponse(request, "admin/historico_detalhe.html", {"h": h})
