"""
Sincronizador filesystem ↔ banco.
Mantém as tabelas 'relatorios' e 'alertas' refletindo o que existe
no filesystem (pastas em app/relatorios/ e app/alertas/).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)

PASTA_RELATORIOS = Path(__file__).resolve().parent.parent / "relatorios"
PASTA_ALERTAS = Path(__file__).resolve().parent.parent / "alertas"


def _ler_config(pasta: Path) -> dict | None:
    """Lê o config.json de uma pasta de recurso."""
    arquivo_config = pasta / "config.json"

    if not arquivo_config.exists():
        logger.warning(f"config.json não encontrado em {pasta.name}, ignorando.")
        return None

    try:
        return json.loads(arquivo_config.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        logger.error(f"config.json inválido em {pasta.name}: {erro}")
        return None


def _listar_pastas_validas(pasta_raiz: Path) -> list[Path]:
    """Lista pastas que são recursos válidos (ignora __pycache__, etc)."""
    if not pasta_raiz.exists():
        return []

    pastas = []
    for item in pasta_raiz.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("."):
            continue
        pastas.append(item)

    return pastas


def _sincronizar_relatorios() -> dict:
    """Sincroniza pastas de app/relatorios/ com a tabela 'relatorios'."""
    pastas_filesystem = _listar_pastas_validas(PASTA_RELATORIOS)
    nomes_filesystem = {p.name for p in pastas_filesystem}

    estatisticas = {
        "inseridos": 0,
        "atualizados": 0,
        "removidos": 0,
        "reativados": 0,
        "ativos": len(nomes_filesystem),
    }

    with engine.begin() as conexao:
        # Buscar existentes
        resultado = (
            conexao.execute(text("SELECT nome, status FROM relatorios"))
            .mappings()
            .all()
        )
        existentes = {linha["nome"]: linha["status"] for linha in resultado}

        # Processar cada pasta
        for pasta in pastas_filesystem:
            config = _ler_config(pasta)
            if config is None:
                continue

            nome = pasta.name
            titulo = config.get("titulo", nome)
            descricao = config.get("descricao", "")
            categoria = config.get("categoria")
            agora = datetime.now()

            if nome not in existentes:
                conexao.execute(
                    text("""
                        INSERT INTO relatorios
                            (nome, titulo, descricao, categoria, status, ultimo_sync)
                        VALUES
                            (:nome, :titulo, :descricao, :categoria, 'ativo', :ultimo_sync)
                    """),
                    {
                        "nome": nome,
                        "titulo": titulo,
                        "descricao": descricao,
                        "categoria": categoria,
                        "ultimo_sync": agora,
                    },
                )
                estatisticas["inseridos"] += 1
                logger.info(f"[relatorios] Inserido: {nome}")

            else:
                status_atual = existentes[nome]

                if status_atual == "removido":
                    conexao.execute(
                        text("""
                            UPDATE relatorios
                            SET titulo = :titulo,
                                descricao = :descricao,
                                categoria = :categoria,
                                status = 'ativo',
                                removido_em = NULL,
                                ultimo_sync = :ultimo_sync
                            WHERE nome = :nome
                        """),
                        {
                            "nome": nome,
                            "titulo": titulo,
                            "descricao": descricao,
                            "categoria": categoria,
                            "ultimo_sync": agora,
                        },
                    )
                    estatisticas["reativados"] += 1
                    logger.info(f"[relatorios] Reativado: {nome}")

                else:
                    conexao.execute(
                        text("""
                            UPDATE relatorios
                            SET titulo = :titulo,
                                descricao = :descricao,
                                categoria = :categoria,
                                ultimo_sync = :ultimo_sync
                            WHERE nome = :nome
                        """),
                        {
                            "nome": nome,
                            "titulo": titulo,
                            "descricao": descricao,
                            "categoria": categoria,
                            "ultimo_sync": agora,
                        },
                    )
                    estatisticas["atualizados"] += 1

        # Marcar removidos
        nomes_no_banco = set(existentes.keys())
        sumiram = nomes_no_banco - nomes_filesystem

        for nome_sumido in sumiram:
            if existentes[nome_sumido] != "removido":
                conexao.execute(
                    text("""
                        UPDATE relatorios
                        SET status = 'removido',
                            removido_em = :removido_em
                        WHERE nome = :nome
                    """),
                    {
                        "nome": nome_sumido,
                        "removido_em": datetime.now(),
                    },
                )
                estatisticas["removidos"] += 1
                logger.info(f"[relatorios] Marcado como removido: {nome_sumido}")

    return estatisticas


def _sincronizar_alertas() -> dict:
    """Sincroniza pastas de app/alertas/ com a tabela 'alertas'."""
    pastas_filesystem = _listar_pastas_validas(PASTA_ALERTAS)
    nomes_filesystem = {p.name for p in pastas_filesystem}

    estatisticas = {
        "inseridos": 0,
        "atualizados": 0,
        "removidos": 0,
        "reativados": 0,
        "ativos": len(nomes_filesystem),
    }

    with engine.begin() as conexao:
        resultado = (
            conexao.execute(text("SELECT nome, status FROM alertas")).mappings().all()
        )
        existentes = {linha["nome"]: linha["status"] for linha in resultado}

        for pasta in pastas_filesystem:
            config = _ler_config(pasta)
            if config is None:
                continue

            nome = pasta.name
            titulo = config.get("titulo", nome)
            descricao = config.get("descricao", "")
            severidade = config.get("severidade", "info")
            agora = datetime.now()

            if nome not in existentes:
                conexao.execute(
                    text("""
                        INSERT INTO alertas
                            (nome, titulo, descricao, severidade, status, ultimo_sync)
                        VALUES
                            (:nome, :titulo, :descricao, :severidade, 'ativo', :ultimo_sync)
                    """),
                    {
                        "nome": nome,
                        "titulo": titulo,
                        "descricao": descricao,
                        "severidade": severidade,
                        "ultimo_sync": agora,
                    },
                )
                estatisticas["inseridos"] += 1
                logger.info(f"[alertas] Inserido: {nome}")

            else:
                status_atual = existentes[nome]

                if status_atual == "removido":
                    conexao.execute(
                        text("""
                            UPDATE alertas
                            SET titulo = :titulo,
                                descricao = :descricao,
                                severidade = :severidade,
                                status = 'ativo',
                                removido_em = NULL,
                                ultimo_sync = :ultimo_sync
                            WHERE nome = :nome
                        """),
                        {
                            "nome": nome,
                            "titulo": titulo,
                            "descricao": descricao,
                            "severidade": severidade,
                            "ultimo_sync": agora,
                        },
                    )
                    estatisticas["reativados"] += 1
                    logger.info(f"[alertas] Reativado: {nome}")

                else:
                    conexao.execute(
                        text("""
                            UPDATE alertas
                            SET titulo = :titulo,
                                descricao = :descricao,
                                severidade = :severidade,
                                ultimo_sync = :ultimo_sync
                            WHERE nome = :nome
                        """),
                        {
                            "nome": nome,
                            "titulo": titulo,
                            "descricao": descricao,
                            "severidade": severidade,
                            "ultimo_sync": agora,
                        },
                    )
                    estatisticas["atualizados"] += 1

        # Marcar removidos
        nomes_no_banco = set(existentes.keys())
        sumiram = nomes_no_banco - nomes_filesystem

        for nome_sumido in sumiram:
            if existentes[nome_sumido] != "removido":
                conexao.execute(
                    text("""
                        UPDATE alertas
                        SET status = 'removido',
                            removido_em = :removido_em
                        WHERE nome = :nome
                    """),
                    {
                        "nome": nome_sumido,
                        "removido_em": datetime.now(),
                    },
                )
                estatisticas["removidos"] += 1
                logger.info(f"[alertas] Marcado como removido: {nome_sumido}")

    return estatisticas


def sincronizar_filesystem_com_banco() -> dict:
    """Sincroniza ambas as tabelas com seus filesystems."""
    logger.info("Sincronizando filesystem com banco...")

    resultado_relatorios = _sincronizar_relatorios()
    resultado_alertas = _sincronizar_alertas()

    logger.info(
        f"Relatórios: {resultado_relatorios['ativos']} ativos | "
        f"+{resultado_relatorios['inseridos']} novos | "
        f"~{resultado_relatorios['atualizados']} atualizados | "
        f"-{resultado_relatorios['removidos']} removidos"
    )
    logger.info(
        f"Alertas: {resultado_alertas['ativos']} ativos | "
        f"+{resultado_alertas['inseridos']} novos | "
        f"~{resultado_alertas['atualizados']} atualizados | "
        f"-{resultado_alertas['removidos']} removidos"
    )

    return {
        "relatorios": resultado_relatorios,
        "alertas": resultado_alertas,
    }
