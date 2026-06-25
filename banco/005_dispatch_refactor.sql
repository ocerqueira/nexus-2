-- =============================================================================
-- Migration 005: Dispatch Layer Refactor
-- =============================================================================
-- Substitui alertas_condicoes por modelo granular de despachos rastreáveis.
-- Inclui: destinatários por alerta/relatório/agendamento, fingerprint por item,
--         janela de silêncio, rate limit, relatório filtrado por destinatário.
--
-- Executar em sequência:
--   1. Este arquivo (schema)
--   2. 005b_migrar_alertas_condicoes.sql (dados + DROP)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE A: Ajustes em tabelas existentes
-- ─────────────────────────────────────────────────────────────────────────────

-- usuarios: adicionar origem 'externo' (clientes, motoristas, fornecedores)
--           + janela de silêncio (não perturbar entre X e Y horas)
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS chk_usuarios_origem;
ALTER TABLE usuarios ADD CONSTRAINT chk_usuarios_origem
    CHECK (origem IN ('manual', 'whatsapp', 'ad_sync', 'externo'));

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS silencio_inicio TIME;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS silencio_fim    TIME;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS silencio_ativo  BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN usuarios.silencio_inicio IS 'Início da janela de silêncio (hora local). Ex: 22:00';
COMMENT ON COLUMN usuarios.silencio_fim    IS 'Fim da janela de silêncio (hora local). Ex: 06:00';
COMMENT ON COLUMN usuarios.silencio_ativo  IS 'Se TRUE, despachos criados na janela ficam com enviar_apos preenchido';


-- alertas: cooldown e último disparo no nível do alerta (não da condição)
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS cooldown_minutos INTEGER NOT NULL DEFAULT 60;
ALTER TABLE alertas ADD COLUMN IF NOT EXISTS ultimo_disparo   TIMESTAMPTZ;

COMMENT ON COLUMN alertas.cooldown_minutos IS 'Cooldown global entre disparos (minutos). Operado por item via alertas_itens_notificados.';
COMMENT ON COLUMN alertas.ultimo_disparo   IS 'Timestamp do último despacho criado (qualquer item)';


-- relatorios: suporte a execução individual por destinatário
ALTER TABLE relatorios ADD COLUMN IF NOT EXISTS modo_execucao VARCHAR(20) NOT NULL DEFAULT 'unico';

DO $$ BEGIN
    ALTER TABLE relatorios ADD CONSTRAINT chk_relatorios_modo_execucao
        CHECK (modo_execucao IN ('unico', 'por_destinatario'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN relatorios.modo_execucao IS 'unico: 1 execução, N envios | por_destinatario: 1 execução por destinatário usando filtro_parametros';


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE B: Destinatários fixos por alerta
-- Substitui alertas_condicoes.destinatarios + alertas_condicoes.canais
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alertas_destinatarios (
    id             SERIAL PRIMARY KEY,
    alerta_id      INTEGER NOT NULL REFERENCES alertas(id) ON DELETE CASCADE,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    canais         JSONB NOT NULL DEFAULT '["whatsapp"]',
    modo_mensagem  VARCHAR(20) NOT NULL DEFAULT 'individual',
    limite_hora    INTEGER,
    limite_dia     INTEGER,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (alerta_id, usuario_id),
    CONSTRAINT chk_ad_modo CHECK (modo_mensagem IN ('individual', 'agrupado'))
);

CREATE INDEX IF NOT EXISTS idx_alertas_dest_alerta ON alertas_destinatarios(alerta_id) WHERE ativo = TRUE;

DROP TRIGGER IF EXISTS trg_alertas_dest_atualizado_em ON alertas_destinatarios;
CREATE TRIGGER trg_alertas_dest_atualizado_em
BEFORE UPDATE ON alertas_destinatarios
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE  alertas_destinatarios               IS 'Destinatários fixos por alerta (substitui alertas_condicoes.destinatarios)';
COMMENT ON COLUMN alertas_destinatarios.canais        IS 'Canais habilitados: ["whatsapp", "email", "sms"]';
COMMENT ON COLUMN alertas_destinatarios.modo_mensagem IS 'individual: 1 despacho/item | agrupado: 1 despacho com todos os itens';
COMMENT ON COLUMN alertas_destinatarios.limite_hora   IS 'Max despachos/hora para este par (alerta, destinatário). NULL = sem limite.';
COMMENT ON COLUMN alertas_destinatarios.limite_dia    IS 'Max despachos/dia para este par (alerta, destinatário). NULL = sem limite.';


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE C: Destinatários fixos por relatório
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS relatorios_destinatarios (
    id                SERIAL PRIMARY KEY,
    relatorio_id      INTEGER NOT NULL REFERENCES relatorios(id) ON DELETE CASCADE,
    usuario_id        INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    canais            JSONB NOT NULL DEFAULT '["whatsapp"]',
    formato_whatsapp  VARCHAR(20) NOT NULL DEFAULT 'documento',
    filtro_parametros JSONB,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (relatorio_id, usuario_id),
    CONSTRAINT chk_rd_formato CHECK (formato_whatsapp IN ('documento', 'resumo_texto'))
);

CREATE INDEX IF NOT EXISTS idx_relatorios_dest_rel ON relatorios_destinatarios(relatorio_id) WHERE ativo = TRUE;

DROP TRIGGER IF EXISTS trg_relatorios_dest_atualizado_em ON relatorios_destinatarios;
CREATE TRIGGER trg_relatorios_dest_atualizado_em
BEFORE UPDATE ON relatorios_destinatarios
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE  relatorios_destinatarios                  IS 'Destinatários fixos por relatório';
COMMENT ON COLUMN relatorios_destinatarios.formato_whatsapp IS 'documento: PDF binário via WhatsApp | resumo_texto: campo resumo como texto';
COMMENT ON COLUMN relatorios_destinatarios.filtro_parametros IS 'Override de parâmetros para este destinatário (usado quando modo_execucao=por_destinatario)';


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE D: Destinatários extras por agendamento
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agendamentos_destinatarios (
    agendamento_id  INTEGER NOT NULL REFERENCES agendamentos(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    canais          JSONB NOT NULL DEFAULT '["whatsapp"]',
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (agendamento_id, usuario_id)
);

COMMENT ON TABLE agendamentos_destinatarios IS 'Destinatários extras por agendamento (além do usuario_id criador)';


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE E: Fingerprint granular por item
-- Habilita cooldown por item (não por run do alerta)
-- Para alertas sistêmicos: item_fingerprint = hash do estado global
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alertas_itens_notificados (
    id                SERIAL PRIMARY KEY,
    alerta_id         INTEGER NOT NULL REFERENCES alertas(id) ON DELETE CASCADE,
    item_fingerprint  VARCHAR(64) NOT NULL,
    primeiro_disparo  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_disparo    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_disparos    INTEGER NOT NULL DEFAULT 1,

    UNIQUE (alerta_id, item_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_ain_alerta_ultimo ON alertas_itens_notificados(alerta_id, ultimo_disparo);

COMMENT ON TABLE  alertas_itens_notificados                  IS 'Rastreio de itens notificados para cooldown granular por item';
COMMENT ON COLUMN alertas_itens_notificados.item_fingerprint IS 'SHA256 do item. Alertas sistêmicos usam hash do estado global.';


-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE F: Despachos rastreáveis
-- Unidade mínima de entrega: (destinatário × canal × payload)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS despachos (
    id             SERIAL PRIMARY KEY,
    historico_id   INTEGER      REFERENCES historico(id)   ON DELETE SET NULL,
    alerta_id      INTEGER      REFERENCES alertas(id)     ON DELETE SET NULL,
    relatorio_id   INTEGER      REFERENCES relatorios(id)  ON DELETE SET NULL,
    usuario_id     INTEGER      REFERENCES usuarios(id)    ON DELETE SET NULL,
    canal          VARCHAR(20)  NOT NULL,
    destino        VARCHAR(255) NOT NULL,
    payload        JSONB        NOT NULL,
    status         VARCHAR(30)  NOT NULL DEFAULT 'pendente',
    tentativas     INTEGER      NOT NULL DEFAULT 0,
    ultimo_erro    TEXT,
    acao_requerida BOOLEAN      NOT NULL DEFAULT FALSE,
    prazo_acao     TIMESTAMPTZ,
    escalado_para  INTEGER      REFERENCES usuarios(id),
    enviar_apos    TIMESTAMPTZ,
    enviado_em     TIMESTAMPTZ,
    criado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_despachos_canal   CHECK (canal IN ('whatsapp', 'email', 'sms')),
    CONSTRAINT chk_despachos_status  CHECK (status IN (
        'pendente', 'enviado', 'falhou', 'confirmado',
        'aguardando_acao', 'bloqueado_rate_limit', 'cancelado'
    ))
);

CREATE INDEX IF NOT EXISTS idx_despachos_pendentes  ON despachos(status, enviar_apos) WHERE status = 'pendente';
CREATE INDEX IF NOT EXISTS idx_despachos_historico  ON despachos(historico_id);
CREATE INDEX IF NOT EXISTS idx_despachos_usuario    ON despachos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_despachos_alerta     ON despachos(alerta_id);
CREATE INDEX IF NOT EXISTS idx_despachos_relatorio  ON despachos(relatorio_id);

COMMENT ON TABLE  despachos                 IS 'Registro de cada envio individual: intenção + resultado de entrega';
COMMENT ON COLUMN despachos.canal           IS 'whatsapp | email | sms';
COMMENT ON COLUMN despachos.destino         IS 'Número WhatsApp (5517...), endereço email, ou número SMS';
COMMENT ON COLUMN despachos.payload         IS 'Conteúdo renderizado: whatsapp={mensagem} | email={assunto,html} | sms={texto}';
COMMENT ON COLUMN despachos.status          IS 'pendente→enviado→confirmado | falhou | aguardando_acao | bloqueado_rate_limit | cancelado';
COMMENT ON COLUMN despachos.enviar_apos     IS 'NULL=enviar agora. Preenchido quando destinatário tem janela de silêncio ativa.';
COMMENT ON COLUMN despachos.acao_requerida  IS 'TRUE=destinatário deve confirmar ação (escalação futura via prazo_acao+escalado_para)';
COMMENT ON COLUMN despachos.escalado_para   IS 'Para quem escalar se prazo_acao expirar sem confirmação';
