from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracoes(BaseSettings):
    """Configurações da aplicação carregados do .env."""

    # ambiente
    ambiente: str = "desenvolvimento"
    debug: bool = True

    # API
    api_titulo: str = "Nexus - Gerador de Relatórios"
    api_versao: str = "0.1.0"

    # banco de dados interno (nexus)
    database_url: str

    # criptografia
    chave_criptografia: str

    # configuração do pydantic settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


configuracoes = Configuracoes()
