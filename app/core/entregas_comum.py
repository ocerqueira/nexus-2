"""
Helpers de entrega compartilhados pelos orquestradores de alertas e relatórios.

Concentra o que os dois fluxos fazem de forma idêntica: modo teste, janela de
silêncio, resolução de destino por canal, inserção de entregas e atualização
do histórico. Corrigir aqui corrige nos dois fluxos.
"""

import json
import logging
import re
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)

TZ_LOCAL = ZoneInfo("America/Sao_Paulo")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ─────────────────────────────────────────────────────────────────────────────
# Validação de contatos
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_whatsapp(valor: Any) -> str | None:
    """
    Normaliza telefone para o formato aceito pela Evolution API:
    somente dígitos, com DDI 55 — ex: 5517999990000 (12-13 dígitos).

    Aceita formatos variados de entrada: '+55 (17) 99999-0000', '017 99999-0000',
    '17999990000', '55 17 99999 0000'. Retorna None se não der para normalizar.
    """
    if not valor:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    # Prefixo de operadora/tronco: '017...' → '17...'
    digitos = digitos.lstrip("0")
    if not digitos:
        return None

    # DDD + número (8 ou 9 dígitos) → prefixa DDI
    if len(digitos) in (10, 11):
        digitos = "55" + digitos

    # ponytail: só Brasil (DDI 55). Números internacionais → None; ampliar aqui se precisar.
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return digitos
    return None


def validar_email(valor: Any) -> str | None:
    """Retorna email normalizado (strip + lowercase) ou None se inválido."""
    if not valor:
        return None
    email = str(valor).strip().lower()
    return email if _EMAIL_RE.match(email) else None


def obter_modo_teste() -> tuple[bool, str | None, str | None]:
    """
    Retorna (modo_teste_ativo, email_teste, whatsapp_teste) das configurações do banco.
    Em caso de falha (banco inacessível, tabela inexistente), retorna False
    para não bloquear envios em produção.
    """
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


def calcular_enviar_apos(dest: dict) -> datetime | None:
    """
    Se o destinatário tem janela de silêncio ativa e agora está dentro dela,
    retorna o próximo timestamp após o fim da janela (entrega agendada).
    Janela pode cruzar meia-noite (ex: 22:00 → 06:00).
    """
    if not dest.get("silencio_ativo"):
        return None

    inicio: time | None = dest.get("silencio_inicio")
    fim: time | None    = dest.get("silencio_fim")
    if not inicio or not fim:
        return None

    agora = datetime.now(TZ_LOCAL)
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


def destino_canal(dest: dict, canal: str) -> str | None:
    """
    Resolve e valida o endereço de destino conforme o canal.
    WhatsApp sai normalizado para o formato da Evolution API (55DDNNNNNNNNN).
    Retorna None se o contato for inválido — o chamador deve pular a entrega.
    """
    if canal == "whatsapp":
        bruto = dest.get("whatsapp_numero") or dest.get("whatsapp")
        destino = normalizar_whatsapp(bruto)
        if bruto and not destino:
            logger.warning(f"WhatsApp inválido para '{dest.get('nome')}': {bruto!r}")
        return destino
    if canal == "email":
        bruto = dest.get("email")
        destino = validar_email(bruto)
        if bruto and not destino:
            logger.warning(f"Email inválido para '{dest.get('nome')}': {bruto!r}")
        return destino
    return None


def inserir_entrega(
    historico_id: int | None,
    dest: dict,
    canal: str,
    payload: dict,
    *,
    alerta_id: int | None = None,
    relatorio_id: int | None = None,
    status: str = "pendente",
    enviar_apos: datetime | None = None,
) -> int:
    """Insere uma entrega na fila. Exatamente um de alerta_id/relatorio_id deve ser passado."""
    with engine.begin() as c:
        row = c.execute(text("""
            INSERT INTO entregas
                (historico_id, alerta_id, relatorio_id, usuario_id, canal, destino, payload, status, enviar_apos)
            VALUES
                (:hid, :aid, :rid, :uid, :canal, :destino, :payload, :status, :enviar_apos)
            RETURNING id
        """), {
            "hid": historico_id,
            "aid": alerta_id,
            "rid": relatorio_id,
            "uid": dest.get("usuario_id"),
            "canal": canal,
            "destino": destino_canal(dest, canal) or "",
            "payload": json.dumps(payload, ensure_ascii=False),
            "status": status,
            "enviar_apos": enviar_apos,
        }).scalar()
    return row


def atualizar_historico_total(historico_id: int | None, total_entregas: int) -> None:
    """Grava o total real de entregas no histórico (registrado com 0 antes da criação)."""
    if not historico_id:
        return
    try:
        with engine.begin() as c:
            c.execute(text("""
                UPDATE historico
                SET parametros = COALESCE(parametros, '{}'::jsonb) || jsonb_build_object('total_entregas', :total)
                WHERE id = :id
            """), {"total": total_entregas, "id": historico_id})
    except Exception as e:
        logger.error(f"Erro ao atualizar total no histórico {historico_id}: {e}")
