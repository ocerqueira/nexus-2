"""
Orquestrador de alertas.
Junta filesystem (lógica) + banco (config) + renderização + destinatários.

Esta é a peça central que torna o sistema agnóstico:
- Novo alerta = nova pasta, sem mexer aqui.
- N8N consome o payload de saída sem precisar saber lógica de cada alerta.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.bd import engine
from app.core.renderizador_mensagens import (
    detectar_capacidades_alerta,
    renderizar_mensagens_consolidadas,
    renderizar_mensagens_individuais,
)

logger = logging.getLogger(__name__)


class AlertaNaoEncontrado(Exception):
    """Alerta não existe no banco ou está inativo/removido."""

    pass


class AlertaEmCooldown(Exception):
    """Alerta não pode disparar agora (ainda em período de cooldown)."""

    pass


def _buscar_alerta_no_banco(nome_alerta: str) -> dict:
    """
    Busca dados do alerta no banco e suas condições ativas.
    Lança AlertaNaoEncontrado se não existe ou está removido.
    """
    with engine.connect() as conexao:
        # Buscar alerta
        resultado = (
            conexao.execute(
                text("""
                SELECT id, nome, titulo, descricao, severidade, status
                FROM alertas
                WHERE nome = :nome AND status = 'ativo'
            """),
                {"nome": nome_alerta},
            )
            .mappings()
            .first()
        )

        if not resultado:
            raise AlertaNaoEncontrado(
                f"Alerta '{nome_alerta}' não encontrado ou inativo"
            )

        alerta = dict(resultado)

        # Buscar condições ativas
        condicoes = (
            conexao.execute(
                text("""
                SELECT id, nome, destinatarios, canais,
                       cooldown_minutos, ultimo_disparo
                FROM alertas_condicoes
                WHERE alerta_id = :alerta_id AND ativo = TRUE
            """),
                {"alerta_id": alerta["id"]},
            )
            .mappings()
            .all()
        )

        alerta["condicoes"] = [dict(c) for c in condicoes]

    return alerta


def _verificar_cooldown(condicoes: list[dict], forcar: bool = False) -> dict:
    """
    Verifica se as condições estão em cooldown.

    Returns:
        {"em_cooldown": bool, "tempo_restante_min": int ou None}
    """
    if forcar:
        return {"em_cooldown": False, "tempo_restante_min": None}

    agora = datetime.now()

    for condicao in condicoes:
        if condicao["ultimo_disparo"] is None:
            # Nunca disparou, pode disparar
            continue

        ultimo = condicao["ultimo_disparo"]
        # Remove timezone para comparar (banco vem com TZ, agora vem sem)
        if ultimo.tzinfo is not None:
            ultimo = ultimo.replace(tzinfo=None)

        cooldown = condicao["cooldown_minutos"]
        proximo_permitido = ultimo + timedelta(minutes=cooldown)

        if agora < proximo_permitido:
            tempo_restante = (proximo_permitido - agora).total_seconds() / 60
            return {
                "em_cooldown": True,
                "tempo_restante_min": int(tempo_restante),
            }

    return {"em_cooldown": False, "tempo_restante_min": None}


def _buscar_destinatarios_fixos(condicoes: list[dict]) -> list[dict]:
    """
    Resolve os destinatários fixos (do banco) buscando dados de contato.

    Args:
        condicoes: Lista de condições do alerta com campo 'destinatarios' (JSONB)

    Returns:
        Lista de dicts com nome, whatsapp, email dos destinatários.
    """
    # Extrair todos os usuario_ids únicos das condições
    usuario_ids = set()
    for condicao in condicoes:
        destinatarios = condicao.get("destinatarios") or []
        for dest in destinatarios:
            if "usuario_id" in dest:
                usuario_ids.add(dest["usuario_id"])

    if not usuario_ids:
        return []

    with engine.connect() as conexao:
        resultado = (
            conexao.execute(
                text("""
                SELECT id, nome, email, whatsapp_numero
                FROM usuarios
                WHERE id = ANY(:ids) AND ativo = TRUE
            """),
                {"ids": list(usuario_ids)},
            )
            .mappings()
            .all()
        )

    return [
        {
            "id": linha["id"],
            "nome": linha["nome"],
            "email": linha["email"],
            "whatsapp": linha["whatsapp_numero"],
        }
        for linha in resultado
    ]


def _consolidar_canais(condicoes: list[dict]) -> list[str]:
    """Coleta todos os canais únicos das condições."""
    todos_canais = set()
    for condicao in condicoes:
        canais = condicao.get("canais") or []
        todos_canais.update(canais)
    return sorted(todos_canais)


def _atualizar_ultimo_disparo(condicoes: list[dict]) -> None:
    """Atualiza ultimo_disparo nas condições disparadas."""
    if not condicoes:
        return

    ids = [c["id"] for c in condicoes]
    agora = datetime.now()

    with engine.begin() as conexao:
        conexao.execute(
            text("""
                UPDATE alertas_condicoes
                SET ultimo_disparo = :agora
                WHERE id = ANY(:ids)
            """),
            {"agora": agora, "ids": ids},
        )

    logger.info(f"Atualizado ultimo_disparo de {len(ids)} condição(ões)")


def _registrar_historico(
    alerta: dict,
    resultado_processador: dict,
    canais: list[str],
    destinatarios: list[dict],
) -> None:
    """Registra o disparo no histórico para auditoria."""
    with engine.begin() as conexao:
        conexao.execute(
            text("""
                INSERT INTO historico (
                    tipo_recurso, recurso_id, recurso_nome,
                    tipo_solicitacao, status,
                    enviado_para, parametros
                ) VALUES (
                    'alerta', :recurso_id, :recurso_nome,
                    'alerta_automatico', 'sucesso',
                    :enviado_para, :parametros
                )
            """),
            {
                "recurso_id": alerta["id"],
                "recurso_nome": alerta["nome"],
                "enviado_para": {
                    "canais": canais,
                    "destinatarios": [d["nome"] for d in destinatarios],
                },
                "parametros": {
                    "total_encontrado": resultado_processador.get("total", 0),
                },
            },
        )


def orquestrar_alerta(
    nome_alerta: str,
    parametros: dict,
    processador_classe: type,
    forcar: bool = False,
) -> dict[str, Any]:
    """
    Orquestra um alerta completo: do banco até a renderização.

    Args:
        nome_alerta: Nome técnico do alerta
        parametros: Parâmetros recebidos da API
        processador_classe: Classe do processador específico
        forcar: Se True, ignora cooldown

    Returns:
        Payload completo pronto para o N8N.
    """
    # 1. Buscar dados do alerta no banco
    alerta = _buscar_alerta_no_banco(nome_alerta)

    # 2. Verificar cooldown
    status_cooldown = _verificar_cooldown(alerta["condicoes"], forcar=forcar)

    if status_cooldown["em_cooldown"]:
        logger.info(
            f"Alerta '{nome_alerta}' em cooldown "
            f"({status_cooldown['tempo_restante_min']} min restantes)"
        )
        return {
            "alerta": {
                "id": alerta["id"],
                "nome": alerta["nome"],
                "titulo": alerta["titulo"],
                "severidade": alerta["severidade"],
            },
            "deve_notificar": False,
            "motivo": "em_cooldown",
            "tempo_restante_min": status_cooldown["tempo_restante_min"],
        }

    # 3. Validar parâmetros
    processador = processador_classe()
    valido, erro = processador.validar(parametros)
    if not valido:
        return {
            "alerta": {
                "id": alerta["id"],
                "nome": alerta["nome"],
                "titulo": alerta["titulo"],
            },
            "deve_notificar": False,
            "motivo": "parametros_invalidos",
            "erro": erro,
        }

    # 4. Executar verificação (chama o processador específico)
    resultado_processador = processador.verificar(parametros)

    # 5. Sem dados? Não notifica
    if not resultado_processador.get("encontrou_dados"):
        return {
            "alerta": {
                "id": alerta["id"],
                "nome": alerta["nome"],
                "titulo": alerta["titulo"],
                "severidade": alerta["severidade"],
            },
            "deve_notificar": False,
            "motivo": "sem_dados",
            "resumo": resultado_processador.get("resumo", ""),
        }

    # 6. Detectar capacidades (que mensagens o alerta sabe renderizar)
    capacidades = detectar_capacidades_alerta(nome_alerta)

    # 7. Montar contexto para os templates
    contexto = {
        "titulo": alerta["titulo"],
        "severidade": alerta["severidade"],
        "descricao": alerta["descricao"],
        "total": resultado_processador.get("total", 0),
        "dados": resultado_processador.get("dados", []),
        "resumo": resultado_processador.get("resumo", ""),
    }

    # 8. Renderizar mensagens consolidadas
    mensagens_consolidadas = {}
    if capacidades["tem_consolidado"]:
        mensagens_consolidadas = renderizar_mensagens_consolidadas(
            nome_alerta, contexto
        )

    # 9. Renderizar mensagens individuais (uma por linha)
    grupos_individuais = []
    if capacidades["tem_individual"]:
        for linha in resultado_processador.get("dados", []):
            mensagens = renderizar_mensagens_individuais(nome_alerta, contexto, linha)
            if mensagens:
                grupos_individuais.append(
                    {
                        "dados_linha": linha,
                        "mensagens": mensagens,
                    }
                )

    # 10. Buscar destinatários fixos do banco
    destinatarios = _buscar_destinatarios_fixos(alerta["condicoes"])

    # 11. Consolidar canais usados
    canais = _consolidar_canais(alerta["condicoes"])

    # 12. Atualizar ultimo_disparo (sem aguardar resposta - efeito colateral)
    _atualizar_ultimo_disparo(alerta["condicoes"])

    # 13. Registrar no histórico
    _registrar_historico(alerta, resultado_processador, canais, destinatarios)

    # 14. Montar payload final
    return {
        "alerta": {
            "id": alerta["id"],
            "nome": alerta["nome"],
            "titulo": alerta["titulo"],
            "severidade": alerta["severidade"],
        },
        "deve_notificar": True,
        "resumo": resultado_processador.get("resumo", ""),
        "total_encontrado": resultado_processador.get("total", 0),
        "canais": canais,
        "destinatarios": destinatarios,
        "mensagens_consolidadas": mensagens_consolidadas,
        "grupos_individuais": grupos_individuais,
        "dados": resultado_processador.get("dados", []),
    }
