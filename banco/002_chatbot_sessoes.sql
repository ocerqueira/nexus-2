-- =============================================================================
-- Sessoes do chatbot WhatsApp
-- Guarda estado entre mensagens (numero = chave, etapa = estado atual da conversa)
-- =============================================================================

CREATE TABLE IF NOT EXISTS chatbot_sessoes (
    numero        VARCHAR(30) PRIMARY KEY,
    etapa         VARCHAR(50) NOT NULL DEFAULT 'idle',
    recurso_tipo  VARCHAR(20),
    recurso_nome  VARCHAR(100),
    parametros    JSONB NOT NULL DEFAULT '{}',
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chatbot_sessoes_atualizado
    ON chatbot_sessoes(atualizado_em);
