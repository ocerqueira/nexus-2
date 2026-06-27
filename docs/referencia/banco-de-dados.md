# Referência — Banco de dados

O Nexus usa PostgreSQL como banco interno. A estrutura é criada automaticamente na inicialização pelos arquivos SQL em `banco/` (executados em ordem numérica: `001_estrutura_inicial.sql`, `002_chatbot_sessoes.sql`, `003_timezone_agendamentos.sql`). Todas as instruções `CREATE` usam `IF NOT EXISTS` — é seguro executar múltiplas vezes.

---

## Diagrama de tabelas

```
usuarios ────────────────────────────────────────────────────────┐
│ (auto-referência: gestor_id → usuarios.id)                     │
│                                                                │
conexoes_bd ──┐                                                  │
              │                                                  │
grupos_conexoes ── grupos_conexoes_itens (N-N)                   │
                                                                 │
relatorios ── relatorios_destinatarios (N-N) ─────────────────  │
│                                                                │── permissoes
alertas ── alertas_destinatarios (N-N)  ─────────────────────── │
│       ── alertas_itens_notificados                             │
│                                                                │
agendamentos ── agendamentos_destinatarios (N-N)                 │
│                                                                │
despachos ── (alerta_id | relatorio_id | usuario_id)             │
│                                                                │
historico ───────────────────────────────────────────────────────┤
│                                                                │
chatbot_sessoes ─────────────────────────────────────────────────┤
│                                                                │
configuracoes ───────────────────────────────────────────────────┘

alertas_condicoes ⚠️ DEPRECATED (substituída pela migration 005)
```

---

## Tabelas

### `usuarios`

Usuários do sistema. Suporta três origens de cadastro: manual, WhatsApp e sincronização AD.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `identificador` | VARCHAR(255) UNIQUE | Chave única: número WhatsApp, e-mail ou login AD |
| `origem` | VARCHAR(20) | `manual`, `whatsapp` ou `ad_sync` |
| `nome` | VARCHAR(200) | Nome completo |
| `email` | VARCHAR(255) | E-mail (nullable) |
| `telefone` | VARCHAR(20) | Telefone fixo (nullable) |
| `whatsapp_numero` | VARCHAR(20) | Número WhatsApp (nullable) |
| `departamento` | VARCHAR(100) | Departamento (nullable) |
| `cargo` | VARCHAR(100) | Cargo (nullable) |
| `gestor_id` | INTEGER FK → usuarios | Hierarquia (nullable) |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `metadados` | JSONB | Campos flexíveis (objectGUID AD, grupos, etc) |
| `ultimo_sync` | TIMESTAMPTZ | Última sincronização AD (nullable) |
| `silencio_inicio` | TIME | Início da janela de silêncio (ex: `22:00`) — nullable |
| `silencio_fim` | TIME | Fim da janela de silêncio (ex: `06:00`) — suporta cruzamento de meia-noite |
| `silencio_ativo` | BOOLEAN | Se TRUE, despachos criados na janela recebem `enviar_apos` |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado automaticamente por trigger |

---

### `conexoes_bd`

Catálogo de conexões a bancos externos. Senhas são armazenadas criptografadas com Fernet.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `nome` | VARCHAR(100) UNIQUE | Identificador da conexão (ex: `erp_unidade_01`) |
| `tipo` | VARCHAR(20) | `firebird`, `postgres` ou `mysql` |
| `host` | VARCHAR(255) | Endereço do servidor |
| `porta` | INTEGER | Porta do banco |
| `banco` | VARCHAR(500) | Nome do database ou caminho do arquivo `.fdb` |
| `usuario` | VARCHAR(100) | Usuário do banco |
| `senha_criptografada` | TEXT | Senha cifrada com Fernet |
| `observacoes` | TEXT | Anotações livres (nullable) |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `grupos_conexoes`

Agrupamentos lógicos de conexões.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `nome` | VARCHAR(100) UNIQUE | Nome do grupo (ex: `todas_unidades`) |
| `descricao` | TEXT | Descrição (nullable) |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

### `grupos_conexoes_itens`

Relação N-N entre grupos e conexões.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `grupo_id` | INTEGER FK → grupos_conexoes | PK composta |
| `conexao_id` | INTEGER FK → conexoes_bd | PK composta |
| `criado_em` | TIMESTAMPTZ | Data de criação |

---

### `relatorios`

Catálogo de relatórios. Sincronizado automaticamente com `app/relatorios/*` na inicialização.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `nome` | VARCHAR(100) UNIQUE | Nome técnico (mesmo da pasta) |
| `titulo` | VARCHAR(200) | Título visível |
| `descricao` | TEXT | Descrição (nullable) |
| `categoria` | VARCHAR(50) | Categoria (nullable) |
| `status` | VARCHAR(20) | `ativo`, `inativo` ou `removido` |
| `modo_execucao` | VARCHAR(20) | `unico` (padrão) \| `por_destinatario` (1 execução por destinatário com filtros) |
| `ultimo_sync` | TIMESTAMPTZ | Última sincronização |
| `removido_em` | TIMESTAMPTZ | Quando foi marcado como removido |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `alertas`

Catálogo de alertas. Sincronizado automaticamente com `app/alertas/*`.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `nome` | VARCHAR(100) UNIQUE | Nome técnico (mesmo da pasta) |
| `titulo` | VARCHAR(200) | Título visível |
| `descricao` | TEXT | Descrição (nullable) |
| `severidade` | VARCHAR(20) | `info`, `aviso`, `critico` |
| `status` | VARCHAR(20) | `ativo`, `inativo` ou `removido` |
| `cooldown_minutos` | INTEGER | Cooldown global entre disparos (padrão: 60). Operado por item via `alertas_itens_notificados`. |
| `ultimo_disparo` | TIMESTAMPTZ | Timestamp do último despacho criado (qualquer item) |
| `ultimo_sync` | TIMESTAMPTZ | Última sincronização |
| `removido_em` | TIMESTAMPTZ | Quando foi marcado como removido |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `alertas_condicoes` ⚠️ DEPRECATED

Substituída pela migration 005. `cooldown_minutos` e `ultimo_disparo` foram movidos para `alertas`. Destinatários e canais foram movidos para `alertas_destinatarios`. Ver `banco/005b_migrar_alertas_condicoes.sql`.

---

### `alertas_destinatarios`

Destinatários fixos por alerta — substitui `alertas_condicoes`. Configurado pelo admin.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `alerta_id` | INTEGER FK → alertas | Alerta associado |
| `usuario_id` | INTEGER FK → usuarios | Destinatário (incluindo `origem='externo'`) |
| `canais` | TEXT[] | `{whatsapp,email}` |
| `modo_mensagem` | VARCHAR(20) | `individual` (1 msg/item) \| `agrupado` (resumo geral) |
| `limite_hora` | INTEGER | Max despachos/hora — NULL = sem limite |
| `limite_dia` | INTEGER | Max despachos/dia — NULL = sem limite |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `criado_em` | TIMESTAMPTZ | Data de criação |

---

### `relatorios_destinatarios`

Destinatários fixos por relatório.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `relatorio_id` | INTEGER FK → relatorios | Relatório associado |
| `usuario_id` | INTEGER FK → usuarios | Destinatário |
| `canais` | TEXT[] | Canais habilitados |
| `formato_whatsapp` | VARCHAR(20) | `documento` (PDF) \| `resumo_texto` (texto) |
| `filtro_parametros` | JSONB | Override de parâmetros para `modo_execucao='por_destinatario'` |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `criado_em` | TIMESTAMPTZ | Data de criação |

---

### `agendamentos_destinatarios`

Destinatários extras por agendamento específico (além do `agendamentos.usuario_id`).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `agendamento_id` | INTEGER FK → agendamentos | Agendamento associado |
| `usuario_id` | INTEGER FK → usuarios | Destinatário extra |
| `canais` | TEXT[] | Canais para este destinatário |
| `criado_em` | TIMESTAMPTZ | Data de criação |

---

### `alertas_itens_notificados`

Fingerprint por item para cooldown granular — evita re-notificar o mesmo item dentro do cooldown.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `alerta_id` | INTEGER FK → alertas | PK composta |
| `item_fingerprint` | VARCHAR(64) | SHA256 dos campos da linha. PK composta. |
| `primeiro_disparo` | TIMESTAMPTZ | Primeira vez que este item foi notificado |
| `ultimo_disparo` | TIMESTAMPTZ | Checado contra `alertas.cooldown_minutos` |
| `total_disparos` | INTEGER | Contador de disparos |

---

### `despachos`

Unidade mínima rastreável de entrega. Criada pelo orquestrador de alertas ou relatórios; consumida pelo `nexus_despachos_sender` no n8n.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `historico_id` | INTEGER FK → historico | Execução que originou o despacho |
| `alerta_id` | INTEGER FK → alertas | Alerta de origem (nullable) |
| `relatorio_id` | INTEGER FK → relatorios | Relatório de origem (nullable) |
| `usuario_id` | INTEGER FK → usuarios | Destinatário (nullable para externos) |
| `canal` | VARCHAR(20) | `whatsapp` \| `email` \| `sms` |
| `destino` | VARCHAR(255) | Número ou e-mail de destino |
| `payload` | JSONB | `{mensagem}` para texto \| `{assunto,html}` para email \| `{documento_base64,...}` para PDF |
| `status` | VARCHAR(30) | `pendente` → `enviado` → `confirmado` \| `falhou` \| `bloqueado_rate_limit` \| `cancelado` |
| `tentativas` | INTEGER | Contador de tentativas de envio |
| `erro` | TEXT | Mensagem de erro da última tentativa |
| `enviar_apos` | TIMESTAMPTZ | NULL = enviar agora. Preenchido por janela de silêncio. |
| `acao_requerida` | BOOLEAN | TRUE = destinatário deve confirmar (escalação futura) |
| `escalado_para` | INTEGER FK → usuarios | Para quem escalar se prazo expirar |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `permissoes`

Controle de acesso a relatórios e alertas. Hard delete — remover permissão = DELETE.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `usuario_id` | INTEGER FK → usuarios | Usuário |
| `tipo_recurso` | VARCHAR(20) | `relatorio` ou `alerta` |
| `recurso_id` | INTEGER | ID do recurso |
| `pode_solicitar` | BOOLEAN | Pode solicitar sob demanda |
| `pode_agendar` | BOOLEAN | Pode criar agendamentos |
| `limite_diario` | INTEGER | Máximo de solicitações por dia |
| `criado_em` | TIMESTAMPTZ | Data de criação |

**Constraints:** `uq_permissoes` UNIQUE (`usuario_id`, `tipo_recurso`, `recurso_id`).

---

### `agendamentos`

Agendamento de execução recorrente. Tabela única com `horarios` e `canais` como JSONB (modelo simplificado — sem tabelas auxiliares).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `usuario_id` | INTEGER FK → usuarios | Dono do agendamento |
| `tipo_recurso` | VARCHAR(20) | `relatorio` ou `alerta` |
| `recurso_id` | INTEGER | ID do recurso |
| `frequencia` | VARCHAR(20) | `diaria`, `semanal`, `mensal` ou `intervalo` |
| `dia_semana` | INTEGER | 1-7 se `semanal` |
| `dia_mes` | INTEGER | 1-31 se `mensal` |
| `intervalo_minutos` | INTEGER | Intervalo em minutos se `intervalo` |
| `horarios` | JSONB | Array de `{hora, minuto}` |
| `apenas_dias_uteis` | BOOLEAN | Pula sábado/domingo |
| `timezone` | VARCHAR(50) | Timezone IANA dos horários (padrão `America/Sao_Paulo`) |
| `parametros` | JSONB | Parâmetros extras para o recurso |
| `canais` | JSONB | Array de canais (`["whatsapp", "email"]`) |
| `ativo` | BOOLEAN | `TRUE` por padrão |
| `ultimo_envio` | TIMESTAMPTZ | Última execução |
| `proximo_envio` | TIMESTAMPTZ | Próxima execução calculada |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `configuracoes`

Tabela chave-valor para configurações do sistema que persistem entre reinicializações (ex: modo teste).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `chave` | VARCHAR(100) PK | Nome da configuração |
| `valor` | TEXT | Valor da configuração |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

**Chaves conhecidas:**
| Chave | Valores | Descrição |
|-------|---------|-----------|
| `modo_teste` | `"true"` / `"false"` | Ativa/desativa modo teste (redireciona notificações para contato de teste) |
| `test_email` | string | Email de destino no modo teste |
| `test_whatsapp` | string | WhatsApp de destino no modo teste |

---

### `chatbot_sessoes`

Sessões de conversa do chatbot WhatsApp. Mantém estado entre mensagens para navegação por menus.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `numero_whatsapp` | VARCHAR(30) | Número do usuário |
| `estado` | VARCHAR(50) | Estado atual do fluxo (`idle`, `aguardando_menu`, etc) |
| `dados` | JSONB | Dados acumulados na sessão (recurso, parâmetros, etc) |
| `criado_em` | TIMESTAMPTZ | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | Atualizado por trigger |

---

### `historico`

Registro de auditoria de todas as execuções.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Identificador único |
| `tipo_recurso` | VARCHAR(20) | `alerta` ou `relatorio` |
| `recurso_id` | INTEGER | ID do recurso |
| `recurso_nome` | VARCHAR(100) | Nome do recurso |
| `tipo_solicitacao` | VARCHAR(50) | `api`, `alerta_automatico`, `agendamento`, `chatbot` |
| `status` | VARCHAR(20) | `sucesso`, `erro`, `sem_dados`, `cooldown` |
| `usuario_id` | INTEGER FK → usuarios | Usuário solicitante (nullable) |
| `enviado_para` | JSONB | Canais e destinatários |
| `parametros` | JSONB | Parâmetros usados e resultado |
| `mensagem_erro` | TEXT | Mensagem de erro se `status=erro` |
| `hash_arquivo` | VARCHAR(64) | Fingerprint SHA256 para deduplicação de alertas |
| `criado_em` | TIMESTAMPTZ | Data de criação |

---

## Funções e triggers

### `atualizar_coluna_atualizado_em()`

Trigger genérica aplicada a todas as tabelas com coluna `atualizado_em`. Atualiza automaticamente `atualizado_em = NOW()` em qualquer `UPDATE`.

---

## Constraints de validação

| Constraint | Tabela | Valores |
|-----------|--------|---------|
| `chk_usuarios_origem` | usuarios | `manual`, `whatsapp`, `ad_sync` |
| `chk_conexoes_tipo` | conexoes_bd | `firebird`, `postgres`, `mysql` |
| `chk_relatorios_status` | relatorios | `ativo`, `inativo`, `removido` |
| `chk_alertas_status` | alertas | `ativo`, `inativo`, `removido` |
| `chk_alertas_severidade` | alertas | `info`, `aviso`, `critico` |
| `chk_historico_tipo_recurso` | historico | `alerta`, `relatorio` |
| `chk_historico_status` | historico | `sucesso`, `erro`, `sem_dados`, `cooldown` |
| `chk_ag_frequencia` | agendamentos | `diaria`, `semanal`, `mensal`, `intervalo` |
| `chk_ag_dia_semana` | agendamentos | 1-7 |
| `chk_ag_dia_mes` | agendamentos | 1-31 |
| `chk_ag_tipo_recurso` | agendamentos | `relatorio`, `alerta` |

---

## Arquivos de migração

| Arquivo | Conteúdo |
|---------|----------|
| `banco/001_estrutura_inicial.sql` | Tabelas base: usuarios, conexoes_bd, grupos_conexoes, grupos_conexoes_itens, relatorios, alertas, alertas_condicoes, permissoes, agendamentos, historico |
| `banco/002_chatbot_sessoes.sql` | Tabela `chatbot_sessoes` |
| `banco/003_timezone_agendamentos.sql` | Coluna `timezone` em `agendamentos` |
| `banco/004_agendamentos_intervalo.sql` | Frequência `intervalo` com `intervalo_minutos` em `agendamentos` |
| `banco/005_dispatch_refactor.sql` | Dispatch layer: `despachos`, `alertas_destinatarios`, `relatorios_destinatarios`, `agendamentos_destinatarios`, `alertas_itens_notificados`. Colunas `cooldown_minutos`/`ultimo_disparo` em `alertas`, `modo_execucao` em `relatorios`, `silencio_*` em `usuarios` |
| `banco/005b_migrar_alertas_condicoes.sql` | Migra dados de `alertas_condicoes` para as novas tabelas e prepara DROP |
