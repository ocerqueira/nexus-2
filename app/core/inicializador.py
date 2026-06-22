"""
Inicializador do banco Nexus.
Executa arquivos SQL da pasta banco/ ao subir o sistema.
Como todos os comandos usam IF NOT EXISTS, é seguro rodar múltiplas vezes.
"""

import logging
from pathlib import Path

from sqlalchemy import text

from app.bd import engine

logger = logging.getLogger(__name__)

# Pasta onde ficam os arquivos SQL de estrutura
PASTA_BANCO = Path(__file__).resolve().parent.parent.parent / "banco"


def garantir_estrutura_banco() -> None:
    """
    Executa todos os arquivos .sql da pasta banco/.

    Idempotente: como o SQL usa IF NOT EXISTS, pode rodar várias vezes
    sem efeitos colaterais.
    """
    if not PASTA_BANCO.exists():
        logger.warning(f"Pasta {PASTA_BANCO} não existe")
        return

    arquivos = sorted(PASTA_BANCO.glob("*.sql"))

    if not arquivos:
        logger.warning("Nenhum arquivo SQL encontrado em banco/")
        return

    logger.info(f"Garantindo estrutura do banco ({len(arquivos)} arquivo(s) SQL)...")

    for arquivo in arquivos:
        logger.info(f"Executando: {arquivo.name}")
        sql = arquivo.read_text(encoding="utf-8")

        with engine.begin() as conexao:
            conexao.execute(text(sql))

    logger.info("Estrutura do banco garantida.")
