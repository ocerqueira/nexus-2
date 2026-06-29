from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import configuracoes

# Engine principal: gerencia o pool de conexões com o banco interno
engine: Engine = create_engine(
    configuracoes.database_url,
    echo=False,  # Loga SQL no console quando DEBUG=true
    pool_pre_ping=True,  # Valida conexão antes de usar
    pool_size=5,  # Conexões mantidas no pool
    max_overflow=10,  # Conexões extras se o pool esgotar
    connect_args={"options": "-c timezone=UTC"},
)
