-- =============================================================================
-- Estrutura inicial do banco Nexus
-- =============================================================================
-- Cria todas as tabelas, índices, constraints, triggers e comentários
-- do sistema gerador de relatórios e alertas.
-- =============================================================================


-- =============================================================================
-- FUNÇÃO: Atualizar coluna 'atualizado_em' automaticamente
-- =============================================================================
CREATE OR REPLACE FUNCTION atualizar_coluna_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION atualizar_coluna_atualizado_em() IS
    'Trigger genérico para atualizar coluna atualizado_em em qualquer tabela';



-- =============================================================================
-- TABELA: usuarios
-- =============================================================================
-- Usuários do sistema (cadastro manual, WhatsApp ou futuro AD).
-- =============================================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id                SERIAL PRIMARY KEY,
    identificador     VARCHAR(255) NOT NULL UNIQUE,
    origem            VARCHAR(20) NOT NULL DEFAULT 'manual',
    nome              VARCHAR(200) NOT NULL,
    email             VARCHAR(255),
    telefone          VARCHAR(20),
    whatsapp_numero   VARCHAR(20),
    departamento      VARCHAR(100),
    cargo             VARCHAR(100),
    gestor_id         INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    metadados         JSONB,
    ultimo_sync       TIMESTAMPTZ,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_usuarios_origem CHECK (origem IN ('manual', 'whatsapp', 'ad_sync'))
);

CREATE INDEX IF NOT EXISTS idx_usuarios_whatsapp ON usuarios(whatsapp_numero) WHERE whatsapp_numero IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usuarios_ativo ON usuarios(ativo);
CREATE INDEX IF NOT EXISTS idx_usuarios_origem ON usuarios(origem);

DROP TRIGGER IF EXISTS trg_usuarios_atualizado_em ON usuarios;
CREATE TRIGGER trg_usuarios_atualizado_em
BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE usuarios IS 'Usuários do sistema Nexus';
COMMENT ON COLUMN usuarios.identificador IS 'Chave única: número WhatsApp, email ou login AD';
COMMENT ON COLUMN usuarios.origem IS 'Como foi cadastrado: manual, whatsapp, ad_sync';
COMMENT ON COLUMN usuarios.gestor_id IS 'Hierarquia: aponta para outro usuário (auto-referência)';
COMMENT ON COLUMN usuarios.metadados IS 'Campos flexíveis (objectGUID do AD, grupos, etc)';
COMMENT ON COLUMN usuarios.ultimo_sync IS 'Última sincronização com AD (NULL para origem manual/whatsapp)';


-- =============================================================================
-- TABELA: conexoes_bd
-- =============================================================================
-- Catálogo de TODAS as conexões externas (Firebird, Postgres, MySQL).
-- Senhas são armazenadas criptografadas (Fernet + chave no .env).
-- =============================================================================
CREATE TABLE IF NOT EXISTS conexoes_bd (
    id                     SERIAL PRIMARY KEY,
    nome                   VARCHAR(100) NOT NULL UNIQUE,
    tipo                   VARCHAR(20) NOT NULL,
    host                   VARCHAR(255) NOT NULL,
    porta                  INTEGER NOT NULL,
    banco                  VARCHAR(500) NOT NULL,
    usuario                VARCHAR(100) NOT NULL,
    senha_criptografada    TEXT NOT NULL,
    observacoes            TEXT,
    ativo                  BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_conexoes_tipo CHECK (tipo IN ('firebird', 'postgres', 'mysql'))
);

CREATE INDEX IF NOT EXISTS idx_conexoes_tipo ON conexoes_bd(tipo);
CREATE INDEX IF NOT EXISTS idx_conexoes_ativo ON conexoes_bd(ativo);

DROP TRIGGER IF EXISTS trg_conexoes_bd_atualizado_em ON conexoes_bd;
CREATE TRIGGER trg_conexoes_bd_atualizado_em
BEFORE UPDATE ON conexoes_bd
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE conexoes_bd IS 'Catálogo de conexões a bancos externos (Firebird, Postgres, MySQL)';
COMMENT ON COLUMN conexoes_bd.nome IS 'Identificador único da conexão (ex: erp_unidade_01)';
COMMENT ON COLUMN conexoes_bd.tipo IS 'Tipo do banco: firebird, postgres, mysql';
COMMENT ON COLUMN conexoes_bd.banco IS 'Nome do database ou caminho do arquivo .fdb';
COMMENT ON COLUMN conexoes_bd.senha_criptografada IS 'Senha criptografada com Fernet (chave em .env: CHAVE_CRIPTOGRAFIA)';
COMMENT ON COLUMN conexoes_bd.observacoes IS 'Anotações livres (ex: versão, multiempresa, finalidade)';


-- =============================================================================
-- TABELA: grupos_conexoes
-- =============================================================================
-- Agrupamentos lógicos de conexões (ex: "todas_unidades", "regiao_sp").
-- =============================================================================
CREATE TABLE IF NOT EXISTS grupos_conexoes (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(100) NOT NULL UNIQUE,
    descricao       TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grupos_conexoes_ativo ON grupos_conexoes(ativo);

DROP TRIGGER IF EXISTS trg_grupos_conexoes_atualizado_em ON grupos_conexoes;
CREATE TRIGGER trg_grupos_conexoes_atualizado_em
BEFORE UPDATE ON grupos_conexoes
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE grupos_conexoes IS 'Grupos lógicos de conexões para reuso em relatórios';
COMMENT ON COLUMN grupos_conexoes.nome IS 'Nome do grupo (ex: todas_unidades, regiao_sp)';


-- =============================================================================
-- TABELA: grupos_conexoes_itens
-- =============================================================================
-- Relação N-N entre grupos e conexões.
-- =============================================================================
CREATE TABLE IF NOT EXISTS grupos_conexoes_itens (
    grupo_id      INTEGER NOT NULL REFERENCES grupos_conexoes(id) ON DELETE CASCADE,
    conexao_id    INTEGER NOT NULL REFERENCES conexoes_bd(id) ON DELETE CASCADE,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (grupo_id, conexao_id)
);

CREATE INDEX IF NOT EXISTS idx_grupos_itens_conexao ON grupos_conexoes_itens(conexao_id);

COMMENT ON TABLE grupos_conexoes_itens IS 'Vincula conexões a grupos (N-N)';


-- =============================================================================
-- TABELA: relatorios
-- =============================================================================
-- Catálogo de relatórios. Sincroniza com o filesystem (app/relatorios/*).
-- =============================================================================
CREATE TABLE IF NOT EXISTS relatorios (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(100) NOT NULL UNIQUE,
    titulo          VARCHAR(200) NOT NULL,
    descricao       TEXT,
    categoria       VARCHAR(50),
    status          VARCHAR(20) NOT NULL DEFAULT 'ativo',
    ultimo_sync     TIMESTAMPTZ,
    removido_em     TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_relatorios_status CHECK (status IN ('ativo', 'inativo', 'removido'))
);

CREATE INDEX IF NOT EXISTS idx_relatorios_status ON relatorios(status);
CREATE INDEX IF NOT EXISTS idx_relatorios_categoria ON relatorios(categoria);

DROP TRIGGER IF EXISTS trg_relatorios_atualizado_em ON relatorios;
CREATE TRIGGER trg_relatorios_atualizado_em
BEFORE UPDATE ON relatorios
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE relatorios IS 'Catálogo de relatórios (sincroniza com filesystem)';
COMMENT ON COLUMN relatorios.nome IS 'Nome técnico (mesma pasta em app/relatorios/)';
COMMENT ON COLUMN relatorios.status IS 'ativo: em uso | inativo: pausado | removido: pasta sumiu do filesystem';
COMMENT ON COLUMN relatorios.removido_em IS 'Quando foi detectado como removido (NULL se ativo/inativo)';
COMMENT ON COLUMN relatorios.ultimo_sync IS 'Última vez que foi sincronizado com o filesystem';


-- =============================================================================
-- TABELA: alertas
-- =============================================================================
-- Catálogo de alertas. Sincroniza com o filesystem (app/alertas/*).
-- =============================================================================
CREATE TABLE IF NOT EXISTS alertas (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(100) NOT NULL UNIQUE,
    titulo          VARCHAR(200) NOT NULL,
    descricao       TEXT,
    severidade      VARCHAR(20) NOT NULL DEFAULT 'info',
    status          VARCHAR(20) NOT NULL DEFAULT 'ativo',
    ultimo_sync     TIMESTAMPTZ,
    removido_em     TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_alertas_severidade CHECK (severidade IN ('info', 'aviso', 'critico')),
    CONSTRAINT chk_alertas_status CHECK (status IN ('ativo', 'inativo', 'removido'))
);

CREATE INDEX IF NOT EXISTS idx_alertas_status ON alertas(status);
CREATE INDEX IF NOT EXISTS idx_alertas_severidade ON alertas(severidade);

DROP TRIGGER IF EXISTS trg_alertas_atualizado_em ON alertas;
CREATE TRIGGER trg_alertas_atualizado_em
BEFORE UPDATE ON alertas
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE alertas IS 'Catálogo de alertas (sincroniza com filesystem)';
COMMENT ON COLUMN alertas.severidade IS 'info: informativo | aviso: requer atenção | critico: ação imediata';
COMMENT ON COLUMN alertas.status IS 'ativo: monitorando | inativo: pausado | removido: pasta sumiu';


-- =============================================================================
-- TABELA: alertas_condicoes
-- =============================================================================
-- Condições que disparam um alerta. Um alerta pode ter várias condições.
-- =============================================================================
CREATE TABLE IF NOT EXISTS alertas_condicoes (
    id                  SERIAL PRIMARY KEY,
    alerta_id           INTEGER NOT NULL REFERENCES alertas(id) ON DELETE CASCADE,
    nome                VARCHAR(100) NOT NULL,
    consulta_sql        TEXT NOT NULL,
    conexao_id          INTEGER REFERENCES conexoes_bd(id) ON DELETE SET NULL,
    parametros          JSONB,
    destinatarios       JSONB NOT NULL,
    canais              JSONB NOT NULL,
    frequencia_check    VARCHAR(20) NOT NULL DEFAULT 'horaria',
    cooldown_minutos    INTEGER NOT NULL DEFAULT 60,
    ultimo_disparo      TIMESTAMPTZ,
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_condicoes_frequencia CHECK (frequencia_check IN ('horaria', 'diaria'))
);

CREATE INDEX IF NOT EXISTS idx_condicoes_alerta ON alertas_condicoes(alerta_id);
CREATE INDEX IF NOT EXISTS idx_condicoes_ativo ON alertas_condicoes(ativo);

DROP TRIGGER IF EXISTS trg_alertas_condicoes_atualizado_em ON alertas_condicoes;
CREATE TRIGGER trg_alertas_condicoes_atualizado_em
BEFORE UPDATE ON alertas_condicoes
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE alertas_condicoes IS 'Condições SQL que disparam alertas';
COMMENT ON COLUMN alertas_condicoes.consulta_sql IS 'Query que, se retornar linhas, dispara o alerta';
COMMENT ON COLUMN alertas_condicoes.destinatarios IS 'JSON array com usuario_ids: [{"usuario_id": 1}, ...]';
COMMENT ON COLUMN alertas_condicoes.canais IS 'JSON array com canais: ["whatsapp", "email"]';
COMMENT ON COLUMN alertas_condicoes.cooldown_minutos IS 'Tempo mínimo entre disparos do mesmo alerta';
COMMENT ON COLUMN alertas_condicoes.ultimo_disparo IS 'Última vez que esta condição disparou';


-- =============================================================================
-- TABELA: permissoes
-- =============================================================================
-- Quem pode solicitar/agendar quais recursos (relatórios ou alertas).
-- Hard delete: revogar = DELETE.
-- =============================================================================
CREATE TABLE IF NOT EXISTS permissoes (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo_recurso    VARCHAR(20) NOT NULL,
    recurso_id      INTEGER NOT NULL,
    pode_solicitar  BOOLEAN NOT NULL DEFAULT TRUE,
    pode_agendar    BOOLEAN NOT NULL DEFAULT FALSE,
    limite_diario   INTEGER NOT NULL DEFAULT 10,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_permissoes_tipo CHECK (tipo_recurso IN ('relatorio', 'alerta')),
    CONSTRAINT uq_permissoes UNIQUE (usuario_id, tipo_recurso, recurso_id)
);

CREATE INDEX IF NOT EXISTS idx_permissoes_usuario ON permissoes(usuario_id);
CREATE INDEX IF NOT EXISTS idx_permissoes_recurso ON permissoes(tipo_recurso, recurso_id);

COMMENT ON TABLE permissoes IS 'Permissões granulares de acesso a relatórios e alertas';
COMMENT ON COLUMN permissoes.tipo_recurso IS 'relatorio ou alerta';
COMMENT ON COLUMN permissoes.recurso_id IS 'ID do relatório ou alerta (conforme tipo_recurso)';
COMMENT ON COLUMN permissoes.limite_diario IS 'Quantas vezes pode solicitar por dia (rate limit)';


-- =============================================================================
-- TABELA: historico
-- =============================================================================
-- Auditoria completa: toda solicitação fica registrada aqui.
-- Insert-only. Sem soft delete.
-- =============================================================================
CREATE TABLE IF NOT EXISTS historico (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    tipo_recurso        VARCHAR(20) NOT NULL,
    recurso_id          INTEGER,
    recurso_nome        VARCHAR(100) NOT NULL,
    tipo_solicitacao    VARCHAR(30) NOT NULL,
    parametros          JSONB,
    status              VARCHAR(20) NOT NULL,
    tamanho_arquivo     INTEGER,
    hash_arquivo        VARCHAR(64),
    mensagem_erro       TEXT,
    enviado_para        JSONB,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_historico_tipo_recurso CHECK (tipo_recurso IN ('relatorio', 'alerta')),
    CONSTRAINT chk_historico_tipo_solicitacao CHECK (tipo_solicitacao IN ('sob_demanda', 'agendado', 'alerta_automatico')),
    CONSTRAINT chk_historico_status CHECK (status IN ('sucesso', 'erro', 'negado', 'duplicado'))
);

CREATE INDEX IF NOT EXISTS idx_historico_usuario ON historico(usuario_id);
CREATE INDEX IF NOT EXISTS idx_historico_recurso ON historico(tipo_recurso, recurso_id);
CREATE INDEX IF NOT EXISTS idx_historico_recurso_nome ON historico(recurso_nome);
CREATE INDEX IF NOT EXISTS idx_historico_criado_em ON historico(criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_historico_hash ON historico(hash_arquivo) WHERE hash_arquivo IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_historico_status ON historico(status);

COMMENT ON TABLE historico IS 'Auditoria de todas as solicitações (insert-only)';
COMMENT ON COLUMN historico.recurso_nome IS 'Nome do recurso (preservado mesmo se relatório/alerta for removido)';
COMMENT ON COLUMN historico.tipo_solicitacao IS 'sob_demanda: usuário pediu | agendado: cron | alerta_automatico: condição disparou';
COMMENT ON COLUMN historico.status IS 'sucesso | erro | negado (sem permissão) | duplicado (mesmo hash recente)';
COMMENT ON COLUMN historico.hash_arquivo IS 'SHA256 do arquivo gerado (para detectar duplicatas)';
COMMENT ON COLUMN historico.enviado_para IS 'JSON com canais: {"whatsapp": "5521999999999", "email": "x@y.com"}';


-- =============================================================================
-- TABELA: agendamentos
-- =============================================================================
-- Relatórios/alertas que rodam automaticamente em horários definidos.
-- Suporta: 1+ horários por dia + filtro de dias úteis.
-- =============================================================================
DROP TABLE IF EXISTS agendamentos CASCADE;

CREATE TABLE agendamentos (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo_recurso        VARCHAR(20) NOT NULL,
    recurso_id          INTEGER NOT NULL,
    frequencia          VARCHAR(20) NOT NULL,
    dia_semana          INTEGER,
    dia_mes             INTEGER,
    horarios            JSONB NOT NULL,
    apenas_dias_uteis   BOOLEAN NOT NULL DEFAULT FALSE,
    parametros          JSONB,
    canais              JSONB NOT NULL,
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_envio        TIMESTAMPTZ,
    proximo_envio       TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_agendamentos_tipo CHECK (tipo_recurso IN ('relatorio', 'alerta')),
    CONSTRAINT chk_agendamentos_frequencia CHECK (frequencia IN ('diaria', 'semanal', 'mensal')),
    CONSTRAINT chk_agendamentos_dia_semana CHECK (dia_semana IS NULL OR dia_semana BETWEEN 1 AND 7),
    CONSTRAINT chk_agendamentos_dia_mes CHECK (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31),
    CONSTRAINT chk_agendamentos_semanal CHECK (
        frequencia <> 'semanal' OR dia_semana IS NOT NULL
    ),
    CONSTRAINT chk_agendamentos_mensal CHECK (
        frequencia <> 'mensal' OR dia_mes IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_agendamentos_usuario ON agendamentos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_recurso ON agendamentos(tipo_recurso, recurso_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_ativo ON agendamentos(ativo);
CREATE INDEX IF NOT EXISTS idx_agendamentos_proximo_envio ON agendamentos(proximo_envio) WHERE ativo = TRUE;

DROP TRIGGER IF EXISTS trg_agendamentos_atualizado_em ON agendamentos;
CREATE TRIGGER trg_agendamentos_atualizado_em
BEFORE UPDATE ON agendamentos
FOR EACH ROW EXECUTE FUNCTION atualizar_coluna_atualizado_em();

COMMENT ON TABLE agendamentos IS 'Execuções automáticas de relatórios e alertas';
COMMENT ON COLUMN agendamentos.dia_semana IS '1=segunda, 2=terça, ..., 7=domingo (apenas se frequencia=semanal)';
COMMENT ON COLUMN agendamentos.dia_mes IS '1-31 (apenas se frequencia=mensal)';
COMMENT ON COLUMN agendamentos.horarios IS 'JSONB com lista de horários: [{"hora": 9, "minuto": 0}, {"hora": 18, "minuto": 30}]';
COMMENT ON COLUMN agendamentos.apenas_dias_uteis IS 'Se true, pula sábados e domingos';
COMMENT ON COLUMN agendamentos.proximo_envio IS 'Próxima execução calculada (scheduler busca por isso)';
