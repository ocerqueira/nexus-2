"""Testes dos validadores de contato (formato Evolution API) e contrato de processadores."""

import pytest

from app.core.entregas_comum import normalizar_whatsapp, validar_email
from app.core.processadores import carregar_processador, verificar_contrato


# ─────────────────────────────────────────────────────────────────────────────
# normalizar_whatsapp
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    # já no formato Evolution API
    ("5517999990000", "5517999990000"),        # 13 dígitos (celular 9º dígito)
    ("551733334444", "551733334444"),          # 12 dígitos (fixo)
    # formatos variados de entrada
    ("+55 (17) 99999-0000", "5517999990000"),
    ("55 17 99999 0000", "5517999990000"),
    ("(17) 99999-0000", "5517999990000"),
    ("17999990000", "5517999990000"),          # DDD + 9 dígitos
    ("1733334444", "551733334444"),            # DDD + 8 dígitos
    ("017 99999-0000", "5517999990000"),       # prefixo de tronco 0
    (17999990000, "5517999990000"),            # int vindo do ERP
])
def test_normalizar_whatsapp_validos(entrada, esperado):
    assert normalizar_whatsapp(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    None, "", "   ", "abc", "999",             # vazio/curto demais
    "12345678",                                # 8 dígitos sem DDD
    "55179999900001234",                       # longo demais
    "4915112345678",                           # DDI estrangeiro (Alemanha)
    0,
])
def test_normalizar_whatsapp_invalidos(entrada):
    assert normalizar_whatsapp(entrada) is None


# ─────────────────────────────────────────────────────────────────────────────
# validar_email
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("joao@empresa.com.br", "joao@empresa.com.br"),
    ("  Joao@Empresa.COM  ", "joao@empresa.com"),  # strip + lowercase
    ("a.b+tag@x.co", "a.b+tag@x.co"),
])
def test_validar_email_validos(entrada, esperado):
    assert validar_email(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    None, "", "sem-arroba", "@dominio.com", "user@", "user@semtld",
    "user @espaco.com", "user@dominio .com",
])
def test_validar_email_invalidos(entrada):
    assert validar_email(entrada) is None


# ─────────────────────────────────────────────────────────────────────────────
# Contrato de processadores (usa as pastas _modelo como fixture viva)
# ─────────────────────────────────────────────────────────────────────────────

def test_carregar_processador_existente():
    classe = carregar_processador("alerta", "item_comprimento_excedente")
    assert classe is not None
    assert classe.__name__.startswith("Processador")


def test_carregar_processador_inexistente():
    assert carregar_processador("alerta", "nao_existe_essa_pasta") is None


def test_verificar_contrato_ok():
    assert verificar_contrato("alerta", "item_comprimento_excedente") is None
    assert verificar_contrato("relatorio", "itens_comprimento_por_carga") is None
    # os modelos também cumprem o contrato que ensinam
    assert verificar_contrato("alerta", "_modelo_alerta") is None
    assert verificar_contrato("relatorio", "_modelo_relatorio") is None


def test_verificar_contrato_pasta_quebrada():
    erro = verificar_contrato("relatorio", "nao_existe_essa_pasta")
    assert erro is not None and "Processador" in erro
