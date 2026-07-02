"""
Descoberta e validação de processadores de relatórios e alertas.

Convenção: cada pasta em app/relatorios/{nome}/ ou app/alertas/{nome}/ tem um
processador.py com exatamente uma classe cujo nome começa com 'Processador'.

Contrato mínimo por tipo:
  relatorio → validar(parametros) + buscar_dados(parametros)
  alerta    → validar(parametros) + verificar(parametros)

O sincronizador chama verificar_contrato() no startup para avisar cedo sobre
pastas quebradas — em vez de o erro só aparecer no primeiro disparo.
"""

import importlib
import logging

logger = logging.getLogger(__name__)

_METODOS_OBRIGATORIOS = {
    "relatorio": ("validar", "buscar_dados"),
    "alerta": ("validar", "verificar"),
}
_PACOTES = {"relatorio": "app.relatorios", "alerta": "app.alertas"}


def carregar_processador(tipo: str, nome: str) -> type | None:
    """
    Importa app.{relatorios|alertas}.{nome}.processador e retorna a classe
    Processador*. Retorna None (com warning no log) se o módulo não importa
    ou nenhuma classe segue a convenção de nome.
    """
    try:
        mod = importlib.import_module(f"{_PACOTES[tipo]}.{nome}.processador")
    except Exception as erro:
        logger.warning(f"[{tipo}:{nome}] processador.py não importável: {erro}")
        return None

    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and attr_name.startswith("Processador") and attr_name != "Processador":
            return attr

    logger.warning(
        f"[{tipo}:{nome}] nenhuma classe 'Processador*' encontrada em processador.py "
        f"— verifique o nome da classe"
    )
    return None


def verificar_contrato(tipo: str, nome: str) -> str | None:
    """
    Valida o contrato do processador de uma pasta.
    Retorna None se ok, ou a mensagem descrevendo o problema.
    """
    classe = carregar_processador(tipo, nome)
    if classe is None:
        return "classe 'Processador*' não encontrada ou módulo não importável"

    faltando = [
        m for m in _METODOS_OBRIGATORIOS[tipo]
        if not callable(getattr(classe, m, None))
    ]
    if faltando:
        return f"classe {classe.__name__} sem método(s) obrigatório(s): {', '.join(faltando)}"
    return None
