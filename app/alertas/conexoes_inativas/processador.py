"""
Processador do alerta: conexoes_inativas
Detecta quando há conexões cadastradas mas desativadas no Nexus.

Versão simplificada: só verifica e retorna os dados.
A decisão de notificar, formatar mensagem, etc é feita pelo orquestrador
(que vamos criar depois).
"""

from pathlib import Path
from typing import Any

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO = "nexus_proprio"


class ProcessadorConexoesInativas:
    """Processa o alerta de conexões inativas."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        """Valida os parâmetros recebidos."""
        if "incluir_observacoes" in parametros:
            if not isinstance(parametros["incluir_observacoes"], bool):
                return False, "Parâmetro 'incluir_observacoes' deve ser true ou false"

        return True, ""

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        """
        Executa a query e retorna os dados encontrados.
        Sistema decide se notifica baseado em ter dados ou não.
        """
        incluir_observacoes = parametros.get("incluir_observacoes", False)

        # Escolhe query baseado no parâmetro
        if incluir_observacoes:
            nome_query = "verificar_conexoes_inativas_com_observacoes"
        else:
            nome_query = "verificar_conexoes_inativas"

        query = carregar_query(ARQUIVO_CONSULTAS, nome_query)

        # Executa
        dados_encontrados = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=query,
        )

        # Resumo curto
        total = len(dados_encontrados)
        if total == 0:
            resumo = "Nenhuma conexão inativa"
        elif total == 1:
            resumo = "1 conexão inativa detectada"
        else:
            resumo = f"{total} conexões inativas detectadas"

        return {
            "encontrou_dados": total > 0,
            "total": total,
            "resumo": resumo,
            "dados": dados_encontrados,
        }
