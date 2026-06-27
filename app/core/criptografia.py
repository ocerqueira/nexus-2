from cryptography.fernet import Fernet

from config import configuracoes


def _obter_fernet() -> Fernet:
    chave_bytes = configuracoes.chave_criptografia.encode()
    return Fernet(chave_bytes)


def criptografar(texto_puro: str) -> str:
    """Criptografa um texto com Fernet (AES-128-CBC + HMAC). Retorna string base64 para salvar no banco."""
    fernet = _obter_fernet()
    bytes_criptografados = fernet.encrypt(texto_puro.encode())
    return bytes_criptografados.decode()


def descriptografar(texto_criptografado: str) -> str:
    """
    Descriptografa um texto criptografado com Fernet.

    Raises:
        cryptography.fernet.InvalidToken: se a chave estiver errada ou o texto corrompido.
    """
    fernet = _obter_fernet()
    bytes_descriptografados = fernet.decrypt(texto_criptografado.encode())
    return bytes_descriptografados.decode()
