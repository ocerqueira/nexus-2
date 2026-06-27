"""
Testes unitários para app.core.carregador_sql.
Função pura de parsing — sem deps externas.
"""

from pathlib import Path

import pytest

from app.core.carregador_sql import carregar_queries, carregar_query


@pytest.fixture
def sql_simples(tmp_path) -> Path:
    conteudo = """\
-- name: buscar_usuarios
SELECT id, nome FROM usuarios WHERE ativo = 1

-- name: buscar_por_id
SELECT * FROM usuarios WHERE id = :id
"""
    arquivo = tmp_path / "teste.sql"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


@pytest.fixture
def sql_sem_marcador(tmp_path) -> Path:
    arquivo = tmp_path / "sem_marcador.sql"
    arquivo.write_text("SELECT 1", encoding="utf-8")
    return arquivo


@pytest.fixture
def sql_unica_query(tmp_path) -> Path:
    conteudo = """\
-- name: unica
SELECT 42 AS resposta
"""
    arquivo = tmp_path / "unica.sql"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


# =============================================================================
# carregar_queries
# =============================================================================

def test_retorna_dict_com_todas_queries(sql_simples):
    queries = carregar_queries(sql_simples)
    assert set(queries.keys()) == {"buscar_usuarios", "buscar_por_id"}


def test_sql_da_query_esta_correto(sql_simples):
    queries = carregar_queries(sql_simples)
    assert "SELECT id, nome FROM usuarios" in queries["buscar_usuarios"]
    assert "WHERE id = :id" in queries["buscar_por_id"]


def test_arquivo_inexistente_levanta_filenotfounderror(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_queries(tmp_path / "nao_existe.sql")


def test_arquivo_sem_marcador_retorna_dict_vazio(sql_sem_marcador):
    queries = carregar_queries(sql_sem_marcador)
    assert queries == {}


def test_comentarios_sql_nao_incluidos_no_resultado(tmp_path):
    conteudo = """\
-- name: com_comentarios
-- este comentário não deve aparecer no SQL
SELECT id FROM tabela
"""
    arquivo = tmp_path / "com_comentarios.sql"
    arquivo.write_text(conteudo, encoding="utf-8")
    queries = carregar_queries(arquivo)
    assert "--" not in queries["com_comentarios"]
    assert "SELECT id FROM tabela" in queries["com_comentarios"]


# =============================================================================
# carregar_query (por nome)
# =============================================================================

def test_carrega_query_pelo_nome(sql_simples):
    sql = carregar_query(sql_simples, "buscar_por_id")
    assert "WHERE id = :id" in sql


def test_query_inexistente_levanta_keyerror(sql_simples):
    with pytest.raises(KeyError, match="nao_existe"):
        carregar_query(sql_simples, "nao_existe")


def test_query_unica_carregada(sql_unica_query):
    sql = carregar_query(sql_unica_query, "unica")
    assert "42" in sql


# =============================================================================
# Cache
# =============================================================================

def test_cache_retorna_mesmo_objeto(sql_simples):
    q1 = carregar_queries(sql_simples)
    q2 = carregar_queries(sql_simples)
    assert q1 is q2
