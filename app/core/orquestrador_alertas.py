"""
Orquestrador de alertas.
Junta filesystem (lógica) + banco (config/destinatários) + renderização + despachos.

Fluxo:
  1. Buscar alerta no banco
  2. Verificar cooldown global (alertas.ultimo_disparo)
  3. Executar processador
  4. Por item: verificar fingerprint + cooldown granular (alertas_itens_notificados)
  5. Buscar destinatários fixos (alertas_destinatarios)
  6. Merge com destinatários dinâmicos do processador (grupos_por_destinatario)
  7. Para cada (item × destinatário × canal): checar rate limit, janela silêncio, renderizar
  8. Inserir despachos no banco
  9. Atualizar fingerprints + ultimo_disparo
 10. Registrar histórico
"""

import hashlib
import json
import logging
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.bd import engine
from app.core.renderizador_mensagens import renderizar_despacho
from app.core.resolvedor_parametros import resolver_tokens

logger = logging.getLogger(__name__)

_TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


class AlertaNaoEncontrado(Exception):
    pass


class AlertaEmCooldown(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Banco: leitura
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_alerta_no_banco(nome: str) -> dict:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT id, nome, titulo, descricao, severidade, status,
                   cooldown_minutos, ultimo_disparo
            FROM alertas
            WHERE nome = :nome AND status = 'ativo'
        """), {"nome": nome}).mappings().first()

    if not row:
        raise AlertaNaoEncontrado(f"Alerta '{nome}' não encontrado ou inativo")
    return dict(row)


def _buscar_destinatarios(alerta_id: int) -> list[dict]:
    """Retorna destinatários fixos do alerta com dados de contato."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT
                ad.modo_mensagem,
                ad.canais,
                ad.limite_hora,
                ad.limite_dia,
                u.id            AS usuario_id,
                u.nome,
                u.email,
                u.whatsapp_numero,
                u.silencio_ativo,
                u.silencio_inicio,
                u.silencio_fim
            FROM alertas_destinatarios ad
            JOIN usuarios u ON u.id = ad.usuario_id
            WHERE ad.alerta_id = :aid AND ad.ativo = TRUE AND u.ativo = TRUE
        """), {"aid": alerta_id}).mappings().all()
    return [dict(r) for r in rows]


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
# Cooldown global
# ─────────────────────────────────────────────────────────────────────────────

def _em_cooldown_global(alerta: dict) -> tuple[bool, int]:
    """Retorna (em_cooldown, minutos_restantes)."""
    ultimo = alerta.get("ultimo_disparo")
    if not ultimo:
        return False, 0
    if ultimo.tzinfo:
        ultimo = ultimo.replace(tzinfo=None)
    proximo = ultimo + timedelta(minutes=alerta["cooldown_minutos"])
    agora = datetime.now()
    if agora < proximo:
        return True, int((proximo - agora).total_seconds() / 60)
    return False, 0


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint por item
# ─────────────────────────────────────────────────────────────────────────────

def _fingerprint_item(linha: dict) -> str:
    """SHA256 de todos os campos da linha ordenados. Inclui valores para detectar mudanças."""
    conteudo = json.dumps(dict(sorted(linha.items())), ensure_ascii=False, default=str)
    return hashlib.sha256(conteudo.encode()).hexdigest()


def _fingerprint_global(dados: list[dict]) -> str:
    """SHA256 do conjunto inteiro (para alertas sistêmicos sem item)."""
    conteudo = json.dumps(
        [dict(sorted(r.items())) for r in sorted(dados, key=lambda x: json.dumps(x, default=str))],
        ensure_ascii=False, default=str,
    )
    return hashlib.sha256(conteudo.encode()).hexdigest()


def _itens_em_cooldown(alerta_id: int, fingerprints: list[str], cooldown_min: int) -> set[str]:
    """Retorna subset de fingerprints que ainda estão em cooldown."""
    if not fingerprints:
        return set()
    limite = datetime.now() - timedelta(minutes=cooldown_min)
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT item_fingerprint
            FROM alertas_itens_notificados
            WHERE alerta_id = :aid
              AND item_fingerprint = ANY(:fps)
              AND ultimo_disparo > :limite
        """), {"aid": alerta_id, "fps": fingerprints, "limite": limite}).scalars().all()
    return set(rows)


def _atualizar_fingerprints(alerta_id: int, fingerprints: list[str]) -> None:
    if not fingerprints:
        return
    agora = datetime.now()
    with engine.begin() as c:
        for fp in fingerprints:
            c.execute(text("""
                INSERT INTO alertas_itens_notificados
                    (alerta_id, item_fingerprint, primeiro_disparo, ultimo_disparo, total_disparos)
                VALUES (:aid, :fp, :agora, :agora, 1)
                ON CONFLICT (alerta_id, item_fingerprint) DO UPDATE
                    SET ultimo_disparo = :agora,
                        total_disparos = alertas_itens_notificados.total_disparos + 1
            """), {"aid": alerta_id, "fp": fp, "agora": agora})


def _atualizar_ultimo_disparo_alerta(alerta_id: int) -> None:
    with engine.begin() as c:
        c.execute(text(
            "UPDATE alertas SET ultimo_disparo = NOW() WHERE id = :id"
        ), {"id": alerta_id})


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit
# ─────────────────────────────────────────────────────────────────────────────

def _rate_limit_excedido(dest: dict, alerta_id: int, canal: str) -> bool:
    limite_hora = dest.get("limite_hora")
    limite_dia  = dest.get("limite_dia")
    if not limite_hora and not limite_dia:
        return False

    usuario_id = dest.get("usuario_id")
    if not usuario_id:
        return False

    with engine.connect() as c:
        if limite_hora:
            count_hora = c.execute(text("""
                SELECT COUNT(*) FROM despachos
                WHERE usuario_id = :uid AND alerta_id = :aid AND canal = :canal
                  AND criado_em > NOW() - INTERVAL '1 hour'
                  AND status != 'cancelado'
            """), {"uid": usuario_id, "aid": alerta_id, "canal": canal}).scalar()
            if count_hora >= limite_hora:
                return True

        if limite_dia:
            count_dia = c.execute(text("""
                SELECT COUNT(*) FROM despachos
                WHERE usuario_id = :uid AND alerta_id = :aid AND canal = :canal
                  AND criado_em > NOW() - INTERVAL '24 hours'
                  AND status != 'cancelado'
            """), {"uid": usuario_id, "aid": alerta_id, "canal": canal}).scalar()
            if count_dia >= limite_dia:
                return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Janela de silêncio
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_enviar_apos(dest: dict) -> datetime | None:
    """
    Se destinatário tem janela de silêncio ativa e agora está dentro dela,
    retorna o próximo timestamp após o fim da janela.
    """
    if not dest.get("silencio_ativo"):
        return None

    inicio: time | None = dest.get("silencio_inicio")
    fim: time | None    = dest.get("silencio_fim")
    if not inicio or not fim:
        return None

    agora = datetime.now(_TZ_LOCAL)
    agora_time = agora.time()

    # Janela pode cruzar meia-noite (ex: 22:00 → 06:00)
    if inicio <= fim:
        em_janela = inicio <= agora_time < fim
    else:
        em_janela = agora_time >= inicio or agora_time < fim

    if not em_janela:
        return None

    # Calcula próximo fim da janela
    fim_hoje = agora.replace(hour=fim.hour, minute=fim.minute, second=0, microsecond=0)
    if fim_hoje <= agora:
        fim_hoje += timedelta(days=1)

    return fim_hoje.replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Destinatários dinâmicos
# ─────────────────────────────────────────────────────────────────────────────

def _merge_destinatarios_dinamicos(
    dest_fixos: list[dict],
    grupos_por_destinatario: list[dict],
    contatos_setores: list[dict],
) -> list[dict]:
    """
    Combina destinatários fixos com dinâmicos (do processador).
    Dedup por whatsapp_numero. Dinâmicos herdam modo_mensagem='individual'
    e não têm rate limit próprio (vêm do ERP, não do admin).
    """
    vistos: set[str] = set()
    resultado: list[dict] = []

    def _chave(d: dict) -> str:
        return d.get("whatsapp_numero") or d.get("whatsapp") or str(d.get("usuario_id", ""))

    for d in dest_fixos:
        k = _chave(d)
        if k and k not in vistos:
            vistos.add(k)
            resultado.append(d)

    # grupos_por_destinatario: novo contrato do processador
    for grupo in grupos_por_destinatario:
        cont = grupo.get("destinatario", {})
        k = cont.get("whatsapp") or str(cont.get("id", ""))
        if k and k not in vistos:
            vistos.add(k)
            resultado.append({
                "usuario_id":      cont.get("id"),
                "nome":            cont.get("nome", ""),
                "email":           cont.get("email"),
                "whatsapp_numero": cont.get("whatsapp"),
                "silencio_ativo":  False,
                "silencio_inicio": None,
                "silencio_fim":    None,
                "canais":          ["whatsapp"],
                "modo_mensagem":   "individual",
                "limite_hora":     None,
                "limite_dia":      None,
                "_itens_grupo":    grupo.get("itens", []),
            })

    # contatos_setores: contrato legado
    for cont in contatos_setores:
        k = cont.get("whatsapp") or str(cont.get("id", ""))
        if k and k not in vistos:
            vistos.add(k)
            resultado.append({
                "usuario_id":      None,
                "nome":            cont.get("nome", ""),
                "email":           cont.get("email"),
                "whatsapp_numero": cont.get("whatsapp"),
                "silencio_ativo":  False,
                "silencio_inicio": None,
                "silencio_fim":    None,
                "canais":          ["whatsapp"],
                "modo_mensagem":   "individual",
                "limite_hora":     None,
                "limite_dia":      None,
            })

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Despachos
# ─────────────────────────────────────────────────────────────────────────────

def _destino_canal(dest: dict, canal: str) -> str | None:
    if canal == "whatsapp":
        return dest.get("whatsapp_numero") or dest.get("whatsapp")
    if canal == "email":
        return dest.get("email")
    return None


def _inserir_despacho(
    historico_id: int | None,
    alerta_id: int,
    dest: dict,
    canal: str,
    payload: dict,
    status: str = "pendente",
    enviar_apos: datetime | None = None,
) -> int:
    usuario_id = dest.get("usuario_id")
    destino = _destino_canal(dest, canal)

    with engine.begin() as c:
        row = c.execute(text("""
            INSERT INTO despachos
                (historico_id, alerta_id, usuario_id, canal, destino, payload, status, enviar_apos)
            VALUES
                (:hid, :aid, :uid, :canal, :destino, :payload, :status, :enviar_apos)
            RETURNING id
        """), {
            "hid": historico_id,
            "aid": alerta_id,
            "uid": usuario_id,
            "canal": canal,
            "destino": destino or "",
            "payload": json.dumps(payload, ensure_ascii=False),
            "status": status,
            "enviar_apos": enviar_apos,
        }).scalar()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Histórico
# ─────────────────────────────────────────────────────────────────────────────

def _registrar_historico(alerta: dict, resultado: dict, total_despachos: int) -> int | None:
    try:
        with engine.begin() as c:
            row = c.execute(text("""
                INSERT INTO historico (
                    tipo_recurso, recurso_id, recurso_nome,
                    tipo_solicitacao, status, parametros, hash_arquivo
                ) VALUES (
                    'alerta', :rid, :rnome,
                    'alerta_automatico', 'sucesso',
                    :params, :hash
                ) RETURNING id
            """), {
                "rid":    alerta["id"],
                "rnome":  alerta["nome"],
                "params": json.dumps({"total_encontrado": resultado.get("total", 0),
                                      "total_despachos": total_despachos}),
                "hash":   resultado.get("fingerprint"),
            }).scalar()
        return row
    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def orquestrar_alerta(
    nome_alerta: str,
    parametros: dict,
    processador_classe: type,
    forcar: bool = False,
) -> dict[str, Any]:
    # 1. Buscar alerta
    alerta = _buscar_alerta_no_banco(nome_alerta)

    # 2. Cooldown global
    em_cooldown, restante = _em_cooldown_global(alerta)
    if em_cooldown and not forcar:
        logger.info(f"Alerta '{nome_alerta}' em cooldown global ({restante} min)")
        return {
            "alerta": _info_alerta(alerta),
            "deve_notificar": False,
            "motivo": "em_cooldown",
            "tempo_restante_min": restante,
        }

    # 3. Validar + executar processador
    parametros = resolver_tokens(parametros)
    processador = processador_classe()
    valido, erro = processador.validar(parametros)
    if not valido:
        return {
            "alerta": _info_alerta(alerta),
            "deve_notificar": False,
            "motivo": "parametros_invalidos",
            "erro": erro,
        }

    resultado = processador.verificar(parametros)

    if not resultado.get("encontrou_dados"):
        return {
            "alerta": _info_alerta(alerta),
            "deve_notificar": False,
            "motivo": "sem_dados",
            "resumo": resultado.get("resumo", ""),
        }

    dados = resultado.get("dados", [])

    # 4. Fingerprint + cooldown por item
    tem_itens = bool(dados)
    if tem_itens:
        fps_dados = [(linha, _fingerprint_item(linha)) for linha in dados]
        if not forcar:
            em_cooldown_fps = _itens_em_cooldown(
                alerta["id"],
                [fp for _, fp in fps_dados],
                alerta["cooldown_minutos"],
            )
            itens_a_notificar = [(linha, fp) for linha, fp in fps_dados if fp not in em_cooldown_fps]
        else:
            itens_a_notificar = fps_dados
    else:
        # Alerta sistêmico: fingerprint do estado global
        fp_global = _fingerprint_global(dados) if not dados else _fingerprint_item(dados[0])
        if not forcar:
            em_cd = _itens_em_cooldown(alerta["id"], [fp_global], alerta["cooldown_minutos"])
            itens_a_notificar = [] if em_cd else [(None, fp_global)]
        else:
            itens_a_notificar = [(None, fp_global)]

    if not itens_a_notificar:
        return {
            "alerta": _info_alerta(alerta),
            "deve_notificar": False,
            "motivo": "todos_itens_em_cooldown",
            "resumo": resultado.get("resumo", ""),
        }

    # 5. Destinatários: fixos + dinâmicos do processador
    dest_fixos = _buscar_destinatarios(alerta["id"])
    todos_dests = _merge_destinatarios_dinamicos(
        dest_fixos,
        resultado.get("grupos_por_destinatario", []),
        resultado.get("contatos_setores", []),
    )

    # 6. Modo teste
    modo_teste, test_email, test_whatsapp = _get_modo_teste()
    if modo_teste:
        logger.warning(f"[MODO TESTE] '{nome_alerta}': substituindo {len(todos_dests)} destinatário(s)")
        todos_dests = [{
            "usuario_id": None, "nome": "[TESTE]",
            "email": test_email, "whatsapp_numero": test_whatsapp,
            "silencio_ativo": False, "silencio_inicio": None, "silencio_fim": None,
            "canais": ["whatsapp"], "modo_mensagem": "individual",
            "limite_hora": None, "limite_dia": None,
        }]

    # 7. Contexto base para templates
    contexto_base = {
        **resultado,
        "titulo":    alerta["titulo"],
        "severidade": alerta["severidade"],
        "descricao": alerta["descricao"],
        "total":     resultado.get("total", 0),
        "dados":     dados,
        "resumo":    resultado.get("resumo", ""),
    }

    # 8. Montar e inserir despachos
    despachos_criados: list[dict] = []
    fps_disparados: list[str] = []

    # Registrar histórico antes para ter historico_id
    historico_id = _registrar_historico(alerta, resultado, 0)

    for dest in todos_dests:
        modo = dest.get("modo_mensagem", "individual")
        canais = dest.get("canais") or ["whatsapp"]

        for canal in canais:
            destino = _destino_canal(dest, canal)
            if not destino:
                continue

            if _rate_limit_excedido(dest, alerta["id"], canal):
                despachos_criados.append({
                    "status": "bloqueado_rate_limit",
                    "canal": canal,
                    "destino": destino,
                    "destinatario": dest.get("nome"),
                })
                continue

            enviar_apos = _calcular_enviar_apos(dest)

            if modo == "agrupado":
                # Um despacho com todos os itens a notificar
                linhas = [l for l, _ in itens_a_notificar if l is not None]
                ctx = {**contexto_base, "dados": linhas, "total": len(linhas)}
                payload = renderizar_despacho(nome_alerta, canal, "agrupado", ctx)
                if payload:
                    did = _inserir_despacho(historico_id, alerta["id"], dest, canal, payload, enviar_apos=enviar_apos)
                    despachos_criados.append({
                        "id": did, "status": "pendente" if not enviar_apos else "pendente",
                        "canal": canal, "destino": destino,
                        "destinatario": dest.get("nome"),
                        "enviar_apos": enviar_apos.isoformat() if enviar_apos else None,
                    })
            else:
                # individual: um despacho por item
                for linha, fp in itens_a_notificar:
                    ctx_linha = linha or {}
                    payload = renderizar_despacho(nome_alerta, canal, "individual", contexto_base, ctx_linha)
                    if payload:
                        did = _inserir_despacho(historico_id, alerta["id"], dest, canal, payload, enviar_apos=enviar_apos)
                        despachos_criados.append({
                            "id": did, "status": "pendente",
                            "canal": canal, "destino": destino,
                            "destinatario": dest.get("nome"),
                            "enviar_apos": enviar_apos.isoformat() if enviar_apos else None,
                        })
                        if fp not in fps_disparados:
                            fps_disparados.append(fp)

    # Para modo agrupado, registrar todos os fps
    if any(d.get("modo_mensagem") == "agrupado" for d in todos_dests):
        fps_disparados = [fp for _, fp in itens_a_notificar]

    # 9. Atualizar fingerprints + ultimo_disparo
    _atualizar_fingerprints(alerta["id"], list(set(fps_disparados)))
    _atualizar_ultimo_disparo_alerta(alerta["id"])

    pendentes = [d for d in despachos_criados if d.get("status") == "pendente"]
    bloqueados = [d for d in despachos_criados if d.get("status") == "bloqueado_rate_limit"]

    return {
        "alerta": _info_alerta(alerta),
        "deve_notificar": bool(pendentes),
        "resumo": resultado.get("resumo", ""),
        "total_encontrado": len(dados),
        "itens_notificados": len(itens_a_notificar),
        "despachos": pendentes,
        "despachos_bloqueados_rate_limit": len(bloqueados),
        "historico_id": historico_id,
    }


def _info_alerta(alerta: dict) -> dict:
    return {
        "id":         alerta["id"],
        "nome":       alerta["nome"],
        "titulo":     alerta["titulo"],
        "severidade": alerta["severidade"],
    }
