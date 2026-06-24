import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_cache_queries: dict[str, dict[str, str]] = {}


def _parsear_arquivo_sql(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {caminho}")

    conteudo = caminho.read_text(encoding="utf-8")

    queries: dict[str, str] = {}
    nome_atual: str | None = None
    linhas_atuais: list[str] = []

    for linha in conteudo.split("\n"):
        linha_limpa = linha.strip()

        if linha_limpa.startswith("-- name:"):
            if nome_atual is not None:
                sql_query = "\n".join(linhas_atuais).strip()
                if sql_query:
                    queries[nome_atual] = sql_query

            nome_atual = linha_limpa.replace("-- name:", "").strip()
            linhas_atuais = []
        else:
            if nome_atual is not None:
                # Strip comment-only lines to avoid encoding issues with non-ASCII chars
                if not linha_limpa.startswith("--"):
                    linhas_atuais.append(linha)

    if nome_atual is not None:
        sql_query = "\n".join(linhas_atuais).strip()
        if sql_query:
            queries[nome_atual] = sql_query

    if not queries:
        logger.warning(f"Nenhuma query com marcador '-- name:' encontrada em {caminho}")

    return queries


def carregar_queries(caminho_arquivo: Path) -> dict[str, str]:

    caminho_str = str(caminho_arquivo)
    if caminho_str not in _cache_queries:
        logger.info(f"Carregando queries de {caminho_arquivo.name}")
        _cache_queries[caminho_str] = _parsear_arquivo_sql(caminho_arquivo)

    return _cache_queries[caminho_str]


def carregar_query(caminho_arquivo: Path, nome_query: str) -> str:
    """
    Carrega uma query específica de um arquivo .sql.

    Args:
        caminho_arquivo: Path para o arquivo .sql
        nome_query: Nome da query (marcador -- name:)

    Returns:
        String SQL da query

    Raises:
        FileNotFoundError: se o arquivo não existir
        KeyError: se a query não existir no arquivo
    """

    queries = carregar_queries(caminho_arquivo)

    if nome_query not in queries:
        nomes_disponiveis = ", ".join(queries.keys()) or "(nenhuma)"
        raise KeyError(
            f"Query '{nome_query}' não encontrada em {caminho_arquivo.name}."
            f"Queries disponiveis: {nomes_disponiveis}"
        )

    return queries[nome_query]

