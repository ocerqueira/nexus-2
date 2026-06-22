"""
Processador do relatório: teste_conexoes
Lista conexões cadastradas no Nexus com diferentes filtros.
"""

from pathlib import Path
from typing import Any

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

# Caminho do arquivo de queries deste relatório
ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"

# Nome da conexão usada por este relatório
CONEXAO = "nexus_proprio"


class ProcessadorTesteConexoes:
    """Processa o relatório de teste de conexões."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        """
        Valida os parâmetros recebidos.

        Returns:
            (valido, mensagem_erro)
        """
        # apenas_ativas: opcional, mas se vier, deve ser boolean
        if "apenas_ativas" in parametros:
            valor = parametros["apenas_ativas"]
            if not isinstance(valor, bool):
                return False, "Parâmetro 'apenas_ativas' deve ser true ou false"

        # tipo_banco: opcional, mas se vier, deve estar na lista permitida
        if "tipo_banco" in parametros and parametros["tipo_banco"]:
            tipos_validos = ["postgres", "firebird", "mysql"]
            if parametros["tipo_banco"] not in tipos_validos:
                return (
                    False,
                    f"Parâmetro 'tipo_banco' deve ser um de: {tipos_validos}",
                )

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        """
        Executa as queries necessárias e monta o payload de retorno.

        Decide qual query usar baseado nos parâmetros (sem usar
        NULL implícito - queries explícitas para cada cenário).
        """
        # Valores padrão se não informados
        apenas_ativas = parametros.get("apenas_ativas", True)
        tipo_banco = parametros.get("tipo_banco")

        # Decide qual query usar baseado nos parâmetros
        if tipo_banco and apenas_ativas:
            nome_query = "filtrar_ativas_por_tipo"
            params_query = {"tipo_banco": tipo_banco}

        elif tipo_banco:
            nome_query = "filtrar_por_tipo"
            params_query = {"tipo_banco": tipo_banco}

        elif apenas_ativas:
            nome_query = "listar_apenas_ativas"
            params_query = {}

        else:
            nome_query = "listar_todas_conexoes"
            params_query = {}

        # Carrega a query do arquivo .sql
        query = carregar_query(ARQUIVO_CONSULTAS, nome_query)

        # Executa via gerenciador
        conexoes = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=query,
            parametros=params_query,
        )

        # Query auxiliar: contagem por tipo
        query_contagem = carregar_query(ARQUIVO_CONSULTAS, "contar_por_tipo")
        contagem_por_tipo = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=query_contagem,
        )

        # Monta payload de retorno
        return {
            "total": len(conexoes),
            "filtros_aplicados": {
                "apenas_ativas": apenas_ativas,
                "tipo_banco": tipo_banco or "todos",
            },
            "conexoes": conexoes,
            "resumo_por_tipo": contagem_por_tipo,
        }
