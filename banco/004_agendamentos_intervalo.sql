-- Migration: suporte a frequencia='intervalo' com intervalo_minutos
-- Idempotente: seguro rodar múltiplas vezes

ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS intervalo_minutos INTEGER;

ALTER TABLE agendamentos DROP CONSTRAINT IF EXISTS chk_agendamentos_frequencia;

DO $$ BEGIN
  ALTER TABLE agendamentos ADD CONSTRAINT chk_agendamentos_frequencia
    CHECK (frequencia IN ('diaria', 'semanal', 'mensal', 'intervalo'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE agendamentos ADD CONSTRAINT chk_agendamentos_intervalo
    CHECK (frequencia <> 'intervalo' OR intervalo_minutos IS NOT NULL);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN agendamentos.intervalo_minutos IS
    'Minutos entre execuções (apenas quando frequencia=intervalo)';
