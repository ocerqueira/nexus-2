-- Adiciona coluna timezone em agendamentos
-- Horários armazenados em hora local da unidade; proximo_envio salvo em UTC.
ALTER TABLE agendamentos
    ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) NOT NULL DEFAULT 'America/Sao_Paulo';

COMMENT ON COLUMN agendamentos.timezone IS
    'Timezone IANA dos horários configurados (ex: America/Sao_Paulo, America/Cuiaba)';
