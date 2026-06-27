"""
Testes unitários para app.core.criptografia.
Usa a chave padrão de desenvolvimento definida em config.py — sem mocking necessário.
"""

import pytest
from cryptography.fernet import InvalidToken

from app.core.criptografia import criptografar, descriptografar


def test_criptografar_retorna_string():
    resultado = criptografar("minhaSenha123")
    assert isinstance(resultado, str)


def test_criptografado_diferente_do_original():
    resultado = criptografar("minhaSenha123")
    assert resultado != "minhaSenha123"


def test_round_trip_basico():
    texto = "minhaSenha123"
    assert descriptografar(criptografar(texto)) == texto


def test_round_trip_string_vazia():
    assert descriptografar(criptografar("")) == ""


def test_round_trip_caracteres_especiais():
    texto = "p@$$w0rd!#%&*()"
    assert descriptografar(criptografar(texto)) == texto


def test_round_trip_unicode():
    texto = "senha_ação_café_ñoño"
    assert descriptografar(criptografar(texto)) == texto


def test_round_trip_senha_longa():
    texto = "a" * 1000
    assert descriptografar(criptografar(texto)) == texto


def test_duas_chamadas_geram_ciphertexts_diferentes():
    # Fernet usa IV aleatório — dois cifrados do mesmo plaintext devem diferir
    c1 = criptografar("mesmoTexto")
    c2 = criptografar("mesmoTexto")
    assert c1 != c2
    # Mas ambos descriptografam para o mesmo valor
    assert descriptografar(c1) == descriptografar(c2) == "mesmoTexto"


def test_token_invalido_levanta_exception():
    with pytest.raises(InvalidToken):
        descriptografar("isto_nao_e_um_token_fernet_valido")


def test_token_corrompido_levanta_exception():
    cifrado = criptografar("valor_secreto")
    corrompido = cifrado[:-5] + "XXXXX"
    with pytest.raises((InvalidToken, Exception)):
        descriptografar(corrompido)
