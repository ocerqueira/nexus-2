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
    database_url: str = (
        "postgresql+psycopg://nexus_admin:nexus_dev_2024@localhost:55432/nexus"
    )

    # criptografia
    chave_criptografia: str = (
        "VhruMtBADWONpWNyyOaik4RnYmwvkTdYtQ-4WFCWsP0="
    )

    # autenticação
    api_key: str | None = None  # se vazio, auth desabilitada (desenvolvimento)

    # Active Directory (opcional — deixe em branco se não usar AD)
    ad_servidor: str | None = None          # ex: ldap://192.168.1.5
    ad_porta: int = 389                     # 389 plain/STARTTLS, 636 LDAPS
    ad_usar_tls: bool = False               # True para LDAPS na porta 636
    ad_bind_user: str | None = None         # DN completo do usuário de serviço
    ad_bind_password: str | None = None
    ad_ou: str | None = None                # OU padrão a sincronizar

    # configuração do pydantic settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


configuracoes = Configuracoes()