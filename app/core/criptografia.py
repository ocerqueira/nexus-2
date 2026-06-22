from cryptography.fernet import Fernet

from config import configuracoes


def _obter_fernet() -> Fernet:
    chave_bytes = configuracoes.chave_criptografia.encode()
    return Fernet(chave_bytes)


def criptografar(texto_puro: str) -> str:
    """
    a função criptograda um texto (ex: senha de banco)

    Args:
        texto_puro: string a ser criptografada (ex: "minhaSenha123")

    Returns:
        string criptografada para guardar no banco
    """

    fernet = _obter_fernet()
    bytes_criptografados = fernet.encrypt(texto_puro.encode())
    return bytes_criptografados.decode()


def descriptografar(texto_criptografado: str) -> str:
    """
    essa aqui obviamente faz o contrario, descriptografa textos criptografados
    Args:
            texto_criptografado: string criptografada (vinda do banco)

        Returns:
            Texto original em texto puro.

        Raises:
            InvalidToken: se a chave for inválida ou o texto estiver corrompido
    """
    fernet = _obter_fernet()
    bytes_descriptografados = fernet.decrypt(texto_criptografado.encode())
    return bytes_descriptografados.decode()
