"""
Gerenciador de conexões com bancos externos (Firebird, Postgres, MySQL).

Lê o catálogo da tabela conexoes_bd, descriptografa senhas, monta URLs
e gerencia pool de engines SQLAlchemy para reuso.
"""

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.bd import engine as engine_nexus
from app.core.criptografia import descriptografar

logger = logging.getLogger(__name__)


class ConexaoNaoEncontrada(Exception):
    """Conexão não existe no catálogo ou está inativa."""

    pass


class TipoBancoNaoSuportado(Exception):
    """Tipo de banco não tem driver configurado."""

    pass


class GerenciadorConexoes:
    """
    Gerencia conexões com múltiplos bancos externos.

    Uso:
        gerenciador = GerenciadorConexoes()
        resultado = gerenciador.executar(
            conexao="erp_unidade_01",
            query="SELECT * FROM vendas WHERE data = :data",
            parametros={"data": "2024-01-15"}
        )
    """

    def __init__(self):
        # Cache de engines SQLAlchemy (uma por conexão)
        self._cache_engines: dict[str, Engine] = {}

        # Cache dos dados da conexão (evita consultar banco do Nexus toda vez)
        self._cache_dados: dict[str, dict] = {}

    def _buscar_dados_conexao(self, nome: str) -> dict:
        """
        Busca dados da conexão no catálogo (tabela conexoes_bd).
        Usa cache para evitar consultas repetidas.
        """
        if nome in self._cache_dados:
            return self._cache_dados[nome]

        with engine_nexus.connect() as conexao:
            resultado = (
                conexao.execute(
                    text("""
                    SELECT id, nome, tipo, host, porta, banco,
                           usuario, senha_criptografada
                    FROM conexoes_bd
                    WHERE nome = :nome AND ativo = TRUE
                """),
                    {"nome": nome},
                )
                .mappings()
                .first()
            )

        if not resultado:
            raise ConexaoNaoEncontrada(
                f"Conexão '{nome}' não encontrada ou está inativa"
            )

        dados = dict(resultado)
        self._cache_dados[nome] = dados
        return dados

    def _montar_url(self, dados: dict) -> str:
        """
        Monta URL SQLAlchemy conforme tipo do banco.
        Descriptografa a senha aqui (só usa em memória).
        """
        tipo = dados["tipo"]
        senha = descriptografar(dados["senha_criptografada"])
        usuario = dados["usuario"]
        host = dados["host"]
        porta = dados["porta"]
        banco = dados["banco"]

        if tipo == "postgres":
            return f"postgresql+psycopg://{usuario}:{senha}@{host}:{porta}/{banco}"

        elif tipo == "firebird":
            return f"firebird+firebird://{usuario}:{senha}@{host}:{porta}/{banco}"

        elif tipo == "mysql":
            return f"mysql+mysqlconnector://{usuario}:{senha}@{host}:{porta}/{banco}"

        else:
            raise TipoBancoNaoSuportado(
                f"Tipo de banco '{tipo}' não suportado. Use: postgres, firebird, mysql"
            )

    def _obter_engine(self, nome: str) -> Engine:
        """
        Retorna engine SQLAlchemy para a conexão.
        Cria na primeira vez, reusa nas próximas.
        """
        if nome in self._cache_engines:
            return self._cache_engines[nome]

        dados = self._buscar_dados_conexao(nome)
        url = self._montar_url(dados)

        logger.info(f"Criando engine para conexão '{nome}' (tipo: {dados['tipo']})")

        novo_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=5,
            pool_recycle=3600,  # Recicla conexão após 1 hora
        )

        self._cache_engines[nome] = novo_engine
        return novo_engine

    def executar(
        self,
        conexao: str,
        query: str,
        parametros: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Executa uma query em uma conexão e retorna lista de dicts.

        Args:
            conexao: Nome da conexão no catálogo (ex: "erp_unidade_01")
            query: SQL a executar (com parâmetros :nome)
            parametros: Dict com valores dos parâmetros

        Returns:
            Lista de dicionários (cada dict = uma linha)

        Raises:
            ConexaoNaoEncontrada: se conexão não existe
            TipoBancoNaoSuportado: se tipo de banco não tem driver
        """
        engine_externo = self._obter_engine(conexao)

        with engine_externo.connect() as conn:
            resultado = conn.execute(text(query), parametros or {})
            return [dict(linha) for linha in resultado.mappings()]

    def testar_conexao(self, nome: str) -> dict[str, Any]:
        """
        Testa se uma conexão funciona executando SELECT 1.

        Returns:
            {"status": "ok"} ou {"status": "erro", "mensagem": "..."}
        """
        try:
            self.executar(conexao=nome, query="SELECT 1 AS teste")
            return {"status": "ok", "mensagem": "Conexão validada com sucesso"}
        except Exception as erro:
            return {"status": "erro", "mensagem": str(erro)}

    def limpar_cache(self, nome: str | None = None) -> None:
        """
        Limpa cache de engines e dados.

        Args:
            nome: Se informado, limpa só essa conexão.
                  Se None, limpa tudo.
        """
        if nome:
            self._cache_engines.pop(nome, None)
            self._cache_dados.pop(nome, None)
            logger.info(f"Cache limpo para conexão '{nome}'")
        else:
            self._cache_engines.clear()
            self._cache_dados.clear()
            logger.info("Cache de conexões totalmente limpo")


# Instância única (singleton) usada em toda a aplicação
gerenciador_conexoes = GerenciadorConexoes()
