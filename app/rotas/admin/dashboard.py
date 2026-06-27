from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ._base import engine, templates, text, _fmt_dt, _recursos_lista

router = APIRouter()


@router.get("/recursos", response_class=HTMLResponse)
def admin_recursos(tipo_recurso: str = Query("relatorio")):
    rows = _recursos_lista(tipo_recurso)
    return "".join(f'<option value="{r["id"]}">{r["titulo"]}</option>' for r in rows)


@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    with engine.connect() as c:
        n_rel = c.execute(text("SELECT COUNT(*) FROM relatorios WHERE status='ativo'")).scalar() or 0
        n_ale = c.execute(text("SELECT COUNT(*) FROM alertas WHERE status='ativo'")).scalar() or 0
        n_usr = c.execute(text("SELECT COUNT(*) FROM usuarios WHERE ativo=TRUE")).scalar() or 0
        n_age = c.execute(text("SELECT COUNT(*) FROM agendamentos WHERE ativo=TRUE")).scalar() or 0
        n_desp_pendentes = c.execute(text("SELECT COUNT(*) FROM despachos WHERE status='pendente'")).scalar() or 0
        n_desp_falhos = c.execute(text("SELECT COUNT(*) FROM despachos WHERE status='falho'")).scalar() or 0
        rows = c.execute(text("""
            SELECT h.tipo_recurso, h.recurso_nome, h.status, h.mensagem_erro, h.criado_em,
                   u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            ORDER BY h.criado_em DESC LIMIT 15
        """)).mappings().all()

    hist = []
    for h in rows:
        d = dict(h)
        d["criado_em_fmt"] = _fmt_dt(d["criado_em"])
        err = str(d.get("mensagem_erro") or "")
        d["erro_resumo"] = (err[:70] + "…") if err else ""
        hist.append(d)

    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "n_rel": n_rel, "n_ale": n_ale, "n_usr": n_usr, "n_age": n_age,
        "n_desp_pendentes": n_desp_pendentes, "n_desp_falhos": n_desp_falhos,
        "hist": hist,
    })
