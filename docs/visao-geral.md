# Nexus — Visão geral

O que é, o que faz e as decisões que moldaram o projeto.

---

## O que é o Nexus

Nexus é uma API de inteligência operacional para empresas que usam ERP legado (Firebird/SQL Server). Ele conecta dados brutos do ERP a pessoas — via WhatsApp e e-mail — sem exigir que o ERP seja modificado ou substituído.

O sistema tem três responsabilidades centrais:

1. **Buscar dados** de múltiplas fontes (ERP Firebird, PostgreSQL, MySQL)
2. **Transformar e entregar** como relatórios PDF agendados ou alertas em tempo real
3. **Rastrear cada entrega** com status, retry automático e histórico auditável

---

## O que o Nexus faz

### Relatórios agendados
- Gera PDFs a partir de queries SQL no ERP
- Envia automaticamente por WhatsApp (documento) ou e-mail (anexo)
- Suporta tokens dinâmicos de período: `{{mes_anterior_inicio}}`, `{{hoje}}`, etc.
- Cada agendamento tem sua própria lista de destinatários além dos destinatários fixos do relatório

### Alertas automáticos
- Monitora o ERP em busca de condições anômalas (comprimento excedente, conexões inativas, etc.)
- Envia mensagens individuais para os responsáveis de cada item afetado
- Extrai destinatários diretamente do ERP (ex: telefone do vendedor do pedido afetado) — sem cadastro manual
- Deduplica por fingerprint: o mesmo item só dispara uma vez por janela de cooldown

### Rastreabilidade
- Todo envio gera uma **entrega** com status rastreado: `pendente → processando → enviado → confirmado | falhou`
- Retry automático para falhas transitórias (até 3 tentativas em 24h)
- Histórico completo de execuções com parâmetros e resultado

### Admin Panel
- Interface web para cadastrar usuários, conexões, agendamentos e destinatários
- Disparo manual de relatórios e alertas
- Visualização de entregas pendentes, enviadas e falhas

---

## Decisões de arquitetura

### Filesystem como catálogo
Novos relatórios e alertas são criados adicionando uma pasta em `app/relatorios/` ou `app/alertas/`. Nenhum arquivo central de configuração é alterado. O Nexus descobre os processadores automaticamente via `importlib` e `POST /sincronizar` registra no banco.

**Por quê:** permite que desenvolvedores criem e testem novos relatórios sem tocar nas rotas. O deploy de um novo relatório é apenas um `git push`.

---

### Entregas como unidade de envio
O Nexus não envia mensagens diretamente. Ele produz **entregas** — registros no banco com destinatário, canal e payload serializado. O n8n consome essas entregas via polling e faz o envio via Evolution API (WhatsApp) ou SMTP.

```
Nexus cria a entrega → n8n envia → Nexus confirma
```

**Por quê:** desacopla a lógica de negócio (quem recebe o quê) da infraestrutura de envio (qual API de WhatsApp, qual SMTP). Trocar de provedor não afeta o Nexus.

---

### n8n é agnóstico
O n8n não sabe nada sobre relatórios, alertas ou destinatários. Ele apenas:
- Faz GET em `/entregas/pendentes`
- Envia cada item pelo canal indicado
- Faz PATCH em `/entregas/{id}/status`

Toda a lógica de negócio fica no Nexus.

**Por quê:** o n8n pode ser substituído por qualquer outro sistema de fila/worker sem mudar uma linha do Nexus.

---

### Destinatários em três camadas

| Camada | Fonte | Quem configura |
|--------|-------|----------------|
| Fixos do relatório/alerta | `relatorios_destinatarios` / `alertas_destinatarios` | Admin |
| Extras do agendamento | `agendamentos_destinatarios` | Admin |
| Dinâmicos do ERP | `contatos_setores` no processador | Desenvolvedor (SQL) |

Os dinâmicos são extraídos em runtime da própria query — se o pedido tem um vendedor com telefone, ele recebe automaticamente, sem nenhum cadastro no Nexus.

---

### Cooldown e deduplicação por fingerprint
Alertas usam SHA256 do conteúdo do item como fingerprint. Se o mesmo item já foi notificado dentro da janela de cooldown, é ignorado. Isso evita spam quando o mesmo problema persiste ao longo do tempo.

`?forcar=true` bypassa cooldown e dedup — útil para testes e reenvios manuais.

---

### Janela de silêncio por usuário
Cada usuário pode ter um horário de silêncio configurado (ex: não perturbar entre 22h e 07h). Entregas criadas dentro dessa janela ficam com `enviar_apos` preenchido e são enviadas após o horário permitido.

---

## Capacidades atuais

| Capacidade | Status |
|------------|--------|
| Multi-banco (Firebird, PostgreSQL, MySQL) | ✅ |
| Relatórios PDF com WeasyPrint | ✅ |
| Alertas com dedup por fingerprint | ✅ |
| Entregas rastreáveis com retry e claim atômico | ✅ |
| Envio WhatsApp via Evolution API | ✅ |
| Envio por e-mail via SMTP | ✅ |
| Agendamentos com cron e tokens dinâmicos | ✅ |
| Destinatários dinâmicos do ERP | ✅ |
| Admin Panel com HTMX | ✅ |
| Janela de silêncio por usuário | ✅ |
| Rate limit por (destinatário × alerta) | ✅ |
| Modo teste (redireciona tudo para número/e-mail de teste) | ✅ |
| Hot reload em dev (Docker + uvicorn --reload) | ✅ |

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| API | FastAPI (Python) |
| Renderização PDF | WeasyPrint + Jinja2 |
| Banco interno | PostgreSQL 16 |
| Bancos externos | Firebird 5, PostgreSQL, MySQL |
| Entrega | n8n + Evolution API (WhatsApp) + SMTP |
| Admin Panel | HTMX + Tailwind CSS |
| Container | Docker + uv |
