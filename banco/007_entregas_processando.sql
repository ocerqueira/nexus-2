-- Adiciona status 'processando' ao ciclo de vida de entregas.
-- Fluxo: pendente → processando (claim do n8n) → enviado/falhou.
-- Evita envio duplicado quando dois pollers rodam ao mesmo tempo.
-- Idempotente: drop + add do constraint a cada boot.

ALTER TABLE entregas ADD COLUMN IF NOT EXISTS processando_em TIMESTAMPTZ;

COMMENT ON COLUMN entregas.processando_em IS 'Quando o n8n fez claim desta entrega. Usado para re-filar entregas travadas.';

ALTER TABLE entregas DROP CONSTRAINT IF EXISTS chk_despachos_status;
ALTER TABLE entregas DROP CONSTRAINT IF EXISTS chk_entregas_status;
ALTER TABLE entregas ADD CONSTRAINT chk_entregas_status CHECK (status IN (
    'pendente', 'processando', 'enviado', 'falhou', 'confirmado',
    'aguardando_acao', 'bloqueado_rate_limit', 'cancelado'
));
