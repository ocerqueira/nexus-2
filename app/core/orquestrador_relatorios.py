"""
Orquestrador de relatórios.
Resolve destinatários, gera PDF/resumo e cria despachos rastreáveis.

Modos de execução (relatorios.modo_execucao):
  'unico'            → 1 execução do processador → N despachos com o mesmo PDF
  'por_destinatario' → 1 execução por destinatário usando filtro_parametros → N PDFs diferentes

Fontes de destinatários (em ordem de prioridade/merge):
  1. relatorios_destinatarios  → fixos por relatório (admin configura)
  2. agendamentos_destinatarios → extras do agendamento específico
  3. usuario_id do agendamento → criador sempre recebe
  4. usuario_id avulso         → passado via parâmetro (chatbot on-demand)
"""

import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.bd import engine
from app.core.renderizador import gerar_pdf, renderizar_html

logger = logging.getLogger(__name__)

_TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


# ─────────────────────────────────────────────────────────────────────────────
# Banco: leitura
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_relatorio(nome: str) -> dict | None:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT id, nome, titulo, descricao, categoria, status, modo_execucao
            FROM relatorios
            WHERE nome = :nome AND status = 'ativo'
        """), {"nome": nome}).mappings().first()
    return dict(row) if row else None


def _buscar_destinatarios_fixos(relatorio_id: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT
                rd.canais,
                rd.formato_whatsapp,
                rd.filtro_parametros,
                u.id               AS usuario_id,
                u.nome,
                u.email,
                u.whatsapp_numero,
                u.silencio_ativo,
                u.silencio_inicio,
                u.silencio_fim
            FROM relatorios_destinatarios rd
            JOIN usuarios u ON u.id = rd.usuario_id
            WHERE rd.relatorio_id = :rid AND rd.ativo = TRUE AND u.ativo = TRUE
        """), {"rid": relatorio_id}).mappings().all()
    return [dict(r) for r in rows]


def _buscar_destinatarios_agendamento(agendamento_id: int) -> list[dict]:
    """Retorna criador do agendamento + destinatários extras."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT
                u.id               AS usuario_id,
                u.nome,
                u.email,
                u.whatsapp_numero,
                u.silencio_ativo,
                u.silencio_inicio,
                u.silencio_fim,
                a.canais
            FROM agendamentos_destinatarios a
            JOIN usuarios u ON u.id = a.usuario_id
            WHERE a.agendamento_id = :aid AND u.ativo = TRUE

            UNION

            SELECT
                u.id,
                u.nome,
                u.email,
                u.whatsapp_numero,
                u.silencio_ativo,
                u.silencio_inicio,
                u.silencio_fim,
                ag.canais
            FROM agendamentos ag
            JOIN usuarios u ON u.id = ag.usuario_id
            WHERE ag.id = :aid AND u.ativo = TRUE
        """), {"aid": agendamento_id}).mappings().all()
    return [dict(r) for r in rows]


def _buscar_usuario(usuario_id: int) -> dict | None:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT id AS usuario_id, nome, email, whatsapp_numero,
                   silencio_ativo, silencio_inicio, silencio_fim
            FROM usuarios WHERE id = :uid AND ativo = TRUE
        """), {"uid": usuario_id}).mappings().first()
    return dict(row) if row else None


def _get_modo_teste() -> tuple[bool, str | None, str | None]:
    try:
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT chave, valor FROM configuracoes "
                "WHERE chave IN ('modo_teste','test_email','test_whatsapp')"
            )).mappings().all()
        cfg = {r["chave"]: r["valor"] for r in rows}
        return cfg.get("modo_teste") == "true", cfg.get("test_email"), cfg.get("test_whatsapp")
    except Exception:
        return False, None, None


# ─────────────────────────────────────────────────────────────────────────────
# Janela de silêncio
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_enviar_apos(dest: dict) -> datetime | None:
    if not dest.get("silencio_ativo"):
        return None
    inicio: time | None = dest.get("silencio_inicio")
    fim: time | None    = dest.get("silencio_fim")
    if not inicio or not fim:
        return None

    agora = datetime.now(_TZ_LOCAL)
    agora_t = agora.time()

    if inicio <= fim:
        em_janela = inicio <= agora_t < fim
    else:
        em_janela = agora_t >= inicio or agora_t < fim

    if not em_janela:
        return None

    fim_hoje = agora.replace(hour=fim.hour, minute=fim.minute, second=0, microsecond=0)
    if fim_hoje <= agora:
        fim_hoje += timedelta(days=1)
    return fim_hoje.replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Merge de destinatários
# ─────────────────────────────────────────────────────────────────────────────

def _merge_destinatarios(
    dest_fixos: list[dict],
    dest_agendamento: list[dict],
    usuario_avulso: dict | None,
    canais_default: list[str],
) -> list[dict]:
    """Combina todas as fontes de destinatários com dedup por usuario_id."""
    vistos: set[int] = set()
    resultado: list[dict] = []

    def _adicionar(d: dict, fmt_wp: str = "documento", filtro: dict | None = None):
        uid = d.get("usuario_id")
        if uid in vistos:
            return
        if uid:
            vistos.add(uid)
        resultado.append({
            **d,
            "canais": d.get("canais") or canais_default,
            "formato_whatsapp": d.get("formato_whatsapp", fmt_wp),
            "filtro_parametros": filtro or d.get("filtro_parametros"),
        })

    for d in dest_fixos:
        _adicionar(d, d.get("formato_whatsapp", "documento"), d.get("filtro_parametros"))

    for d in dest_agendamento:
        _adicionar(d)

    if usuario_avulso:
        _adicionar(usuario_avulso)

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Histórico + despachos
# ─────────────────────────────────────────────────────────────────────────────

def _registrar_historico(relatorio: dict, parametros: dict, total_despachos: int) -> int | None:
    try:
        with engine.begin() as c:
            row = c.execute(text("""
                INSERT INTO historico (
                    tipo_recurso, recurso_id, recurso_nome,
                    tipo_solicitacao, status, parametros
                ) VALUES (
                    'relatorio', :rid, :rnome,
                    'sob_demanda', 'sucesso', :params
                ) RETURNING id
            """), {
                "rid":    relatorio["id"],
                "rnome":  relatorio["nome"],
                "params": json.dumps({**parametros, "total_despachos": total_despachos}),
            }).scalar()
        return row
    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return None


def _inserir_despacho(
    historico_id: int | None,
    relatorio_id: int,
    dest: dict,
    canal: str,
    payload: dict,
    enviar_apos: datetime | None = None,
) -> int:
    usuario_id = dest.get("usuario_id")

    if canal == "whatsapp":
        destino = dest.get("whatsapp_numero") or ""
    elif canal == "email":
        destino = dest.get("email") or ""
    else:
        destino = ""

    with engine.begin() as c:
        row = c.execute(text("""
            INSERT INTO despachos
                (historico_id, relatorio_id, usuario_id, canal, destino, payload, status, enviar_apos)
            VALUES
                (:hid, :rid, :uid, :canal, :destino, :payload, 'pendente', :enviar_apos)
            RETURNING id
        """), {
            "hid": historico_id,
            "rid": relatorio_id,
            "uid": usuario_id,
            "canal": canal,
            "destino": destino,
            "payload": json.dumps(payload, ensure_ascii=False),
            "enviar_apos": enviar_apos,
        }).scalar()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Compressão de PDF
# ─────────────────────────────────────────────────────────────────────────────

def _comprimir_pdf(pdf_bytes: bytes) -> bytes:
    """Tenta comprimir PDF com ghostscript. Retorna original se indisponível."""
    import shutil, subprocess, tempfile, os
    if not shutil.which("gs"):
        return pdf_bytes
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fin:
            fin.write(pdf_bytes)
            path_in = fin.name
        path_out = path_in.replace(".pdf", "_compressed.pdf")
        result = subprocess.run([
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",       # 150dpi — bom balanço tamanho/qualidade
            "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={path_out}", path_in,
        ], capture_output=True, timeout=30)
        if result.returncode == 0 and os.path.exists(path_out):
            compressed = open(path_out, "rb").read()
            if len(compressed) < len(pdf_bytes):
                return compressed
    except Exception as e:
        logger.warning(f"Compressão PDF falhou: {e}")
    finally:
        for p in [path_in, path_out]:
            try:
                os.unlink(p)
            except Exception:
                pass
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def orquestrar_relatorio(
    nome_relatorio: str,
    processador_classe: type,
    titulo: str,
    subtitulo: str | None,
    parametros: dict,
    agendamento_id: int | None = None,
    usuario_solicitante_id: int | None = None,
    comprimir_pdf: bool = True,
) -> dict:
    """
    Orquestra geração + dispatch de um relatório.

    Args:
        nome_relatorio:         Nome técnico do relatório
        processador_classe:     Classe do processador
        titulo / subtitulo:     Metadados para renderização
        parametros:             Parâmetros de geração
        agendamento_id:         Se veio de agendamento (opcional)
        usuario_solicitante_id: Usuário que solicitou on-demand (opcional)
        comprimir_pdf:          Se True, tenta compressão via ghostscript

    Returns:
        Dict com despachos criados e metadados.
    """
    relatorio = _buscar_relatorio(nome_relatorio)
    if not relatorio:
        return {"erro": f"Relatório '{nome_relatorio}' não encontrado ou inativo"}

    # Resolver destinatários
    dest_fixos = _buscar_destinatarios_fixos(relatorio["id"])
    dest_agendamento = _buscar_destinatarios_agendamento(agendamento_id) if agendamento_id else []
    usuario_avulso = _buscar_usuario(usuario_solicitante_id) if usuario_solicitante_id else None

    canais_default = ["whatsapp"]
    todos_dests = _merge_destinatarios(dest_fixos, dest_agendamento, usuario_avulso, canais_default)

    # Modo teste
    modo_teste, test_email, test_whatsapp = _get_modo_teste()
    if modo_teste and todos_dests:
        logger.warning(f"[MODO TESTE] '{nome_relatorio}': substituindo {len(todos_dests)} destinatário(s)")
        todos_dests = [{
            "usuario_id": None, "nome": "[TESTE]",
            "email": test_email, "whatsapp_numero": test_whatsapp,
            "canais": ["whatsapp"], "formato_whatsapp": "documento",
            "filtro_parametros": None,
            "silencio_ativo": False, "silencio_inicio": None, "silencio_fim": None,
        }]

    modo_execucao = relatorio.get("modo_execucao", "unico")
    despachos_criados: list[dict] = []

    historico_id = _registrar_historico(relatorio, parametros, 0)

    if modo_execucao == "unico":
        # Uma execução → N envios
        processador = processador_classe()
        dados = processador.buscar_dados(parametros)
        pdf_bytes = _gerar_e_comprimir(nome_relatorio, dados, titulo, subtitulo, comprimir_pdf)
        resumo = dados.get("resumo", "")

        for dest in todos_dests:
            despachos_criados.extend(_despachar_relatorio(
                historico_id, relatorio["id"], dest, pdf_bytes, resumo,
            ))

    else:
        # por_destinatario: execução separada por destinatário usando filtro_parametros
        for dest in todos_dests:
            filtro = dest.get("filtro_parametros") or {}
            params_dest = {**parametros, **filtro}

            try:
                processador = processador_classe()
                dados = processador.buscar_dados(params_dest)
                pdf_bytes = _gerar_e_comprimir(nome_relatorio, dados, titulo, subtitulo, comprimir_pdf)
                resumo = dados.get("resumo", "")
            except Exception as e:
                logger.error(f"Erro ao gerar relatório para {dest.get('nome')}: {e}")
                continue

            despachos_criados.extend(_despachar_relatorio(
                historico_id, relatorio["id"], dest, pdf_bytes, resumo,
            ))

    return {
        "relatorio": {
            "id":   relatorio["id"],
            "nome": relatorio["nome"],
        },
        "total_destinatarios": len(todos_dests),
        "despachos": [d for d in despachos_criados if d.get("status") == "pendente"],
        "historico_id": historico_id,
    }


def _gerar_e_comprimir(
    nome_relatorio: str,
    dados: dict,
    titulo: str,
    subtitulo: str | None,
    comprimir: bool,
) -> bytes:
    pdf = gerar_pdf(nome_relatorio=nome_relatorio, dados=dados, titulo=titulo, subtitulo=subtitulo)
    if comprimir:
        pdf = _comprimir_pdf(pdf)
    return pdf


def _despachar_relatorio(
    historico_id: int | None,
    relatorio_id: int,
    dest: dict,
    pdf_bytes: bytes,
    resumo: str,
) -> list[dict]:
    """Cria despachos para todos os canais de um destinatário."""
    import base64
    resultado = []
    canais = dest.get("canais") or ["whatsapp"]
    enviar_apos = _calcular_enviar_apos(dest)

    for canal in canais:
        if canal == "whatsapp":
            fmt = dest.get("formato_whatsapp", "documento")
            if fmt == "resumo_texto":
                payload = {"mensagem": resumo or "Relatório gerado. Sem resumo disponível."}
            else:
                payload = {
                    "documento_base64": base64.b64encode(pdf_bytes).decode(),
                    "mimetype": "application/pdf",
                    "caption": resumo or "",
                }
            destino = dest.get("whatsapp_numero") or ""

        elif canal == "email":
            payload = {
                "assunto": f"Relatório: {dest.get('nome', 'N/D')}",
                "pdf_base64": base64.b64encode(pdf_bytes).decode(),
                "resumo": resumo,
            }
            destino = dest.get("email") or ""

        else:
            continue

        if not destino:
            logger.warning(f"Destinatário {dest.get('nome')} sem {canal} — ignorado")
            continue

        did = _inserir_despacho(historico_id, relatorio_id, dest, canal, payload, enviar_apos)
        resultado.append({
            "id": did, "status": "pendente",
            "canal": canal, "destino": destino,
            "destinatario": dest.get("nome"),
            "enviar_apos": enviar_apos.isoformat() if enviar_apos else None,
        })

    return resultado
