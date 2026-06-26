# Fluxo do sistema — Nexus

Visão completa de como um evento percorre o sistema, do gatilho até o destinatário.

---

## Visão geral

```mermaid
flowchart TD
    subgraph GATILHOS["Gatilhos"]
        G1["⏰ Agendamento\n(cron)"]
        G2["📲 On-demand\n(API / chatbot)"]
        G3["🖱 Manual\n(Admin Panel)"]
    end

    subgraph N8N_DISP["n8n — nexus_dispatcher"]
        D1["GET /agendamentos\n/proximas-execucoes"]
        D2["Loop por agendamento"]
        D3{{"tipo?"}}
    end

    subgraph NEXUS["Nexus API"]
        subgraph RELATORIO["Relatório"]
            R1["POST /relatorios/{nome}/solicitar\n?notificar=true"]
            R2["Processador\nbuscar_dados()"]
            R3["Renderizador\ngerar_pdf()"]
            R4["Orquestrador\nrelatórios"]
        end
        subgraph ALERTA["Alerta"]
            A1["POST /alertas/{nome}/verificar"]
            A2["Processador\nverificar()"]
            A3["Cooldown +\nFingerprint (dedup)"]
            A4["Orquestrador\nalertas"]
        end
        subgraph DEST["Resolução de destinatários"]
            DE1["Fixos\n(relatorios/alertas_destinatarios)"]
            DE2["Dinâmicos do ERP\n(contatos_setores)"]
            DE3["Do agendamento\n(agendamentos_destinatarios)"]
        end
        DP["Tabela despachos\nstatus = pendente"]
    end

    subgraph N8N_SEND["n8n — nexus_despachos_sender"]
        S1["GET /despachos/pendentes\n(polling a cada minuto)"]
        S2["Loop por despacho"]
        S3{{"canal?"}}
        S4["Evolution API\nsendMedia (PDF)\nou sendText"]
        S5["SMTP\nsendEmail"]
        S6["PATCH /despachos/{id}/status\nstatus = enviado | falhou"]
    end

    subgraph DEST_FINAL["Destinatários"]
        F1["📱 WhatsApp"]
        F2["📧 E-mail"]
    end

    G1 --> D1
    G2 --> R1
    G2 --> A1
    G3 --> R1
    G3 --> A1

    D1 --> D2 --> D3
    D3 -- relatorio --> R1
    D3 -- alerta --> A1

    R1 --> R2 --> R3 --> R4
    A1 --> A2 --> A3 --> A4

    R4 --> DE1 & DE3
    A4 --> DE1 & DE2

    DE1 & DE2 & DE3 --> DP

    DP --> S1
    S1 --> S2 --> S3
    S3 -- whatsapp --> S4 --> S6
    S3 -- email --> S5 --> S6

    S4 --> F1
    S5 --> F2
```

---

## Fluxo de relatório (detalhado)

```mermaid
sequenceDiagram
    participant Trigger as Gatilho (cron / API)
    participant Nexus as Nexus API
    participant ERP as Banco externo (ERP)
    participant DB as PostgreSQL (Nexus)
    participant N8N as n8n sender
    participant WA as WhatsApp / E-mail

    Trigger->>Nexus: POST /solicitar?notificar=true
    Nexus->>ERP: SQL buscar_dados()
    ERP-->>Nexus: dados brutos
    Nexus->>Nexus: gerar_pdf() — WeasyPrint
    Nexus->>DB: buscar destinatários
    DB-->>Nexus: lista (fixos + agendamento)
    Nexus->>DB: INSERT despachos (status=pendente)
    Nexus-->>Trigger: {despachos: [...]}

    loop a cada minuto
        N8N->>Nexus: GET /despachos/pendentes
        Nexus-->>N8N: [{id, canal, destino, payload}]
        N8N->>WA: sendMedia (PDF) ou sendText
        WA-->>N8N: 200 OK
        N8N->>Nexus: PATCH /despachos/{id}/status = enviado
    end
```

---

## Fluxo de alerta (detalhado)

```mermaid
sequenceDiagram
    participant Trigger as Gatilho (cron / API)
    participant Nexus as Nexus API
    participant ERP as ERP Firebird
    participant DB as PostgreSQL (Nexus)
    participant N8N as n8n sender
    participant WA as WhatsApp

    Trigger->>Nexus: POST /alertas/{nome}/verificar
    Nexus->>DB: verifica cooldown global
    alt em cooldown
        Nexus-->>Trigger: motivo: cooldown_ativo
    else livre
        Nexus->>ERP: SQL verificar()
        ERP-->>Nexus: itens afetados + telefones vendedores
        Nexus->>DB: verifica fingerprint por item (dedup)
        Note over Nexus: itens já notificados = ignorados
        Nexus->>DB: buscar destinatários fixos
        Nexus->>Nexus: merge fixos + dinâmicos do ERP
        Nexus->>DB: INSERT despachos por (item × destinatário)
        Nexus->>DB: atualiza fingerprints + ultimo_disparo
        Nexus-->>Trigger: {despachos: [...]}
    end

    loop a cada minuto
        N8N->>Nexus: GET /despachos/pendentes
        N8N->>WA: sendText (mensagem individual por item)
        N8N->>Nexus: PATCH status = enviado
    end
```

---

## Resolução de destinatários

```mermaid
flowchart LR
    subgraph FONTES["Fontes (merge por whatsapp/email)"]
        F1["relatorios_destinatarios\nfixos do relatório"]
        F2["alertas_destinatarios\nfixos do alerta"]
        F3["agendamentos_destinatarios\nextras do agendamento"]
        F4["usuario_id do agendamento\ncriador"]
        F5["contatos_setores\ndo processador ERP\n(vendedores, assistentes)"]
    end

    subgraph FILTROS["Filtros por destinatário"]
        C1["janela de silêncio\n→ enviar_apos"]
        C2["rate limit\n(limite_hora / limite_dia)"]
        C3["canal disponível\n(whatsapp_numero / email)"]
    end

    subgraph DESPACHO["Despacho"]
        D["status = pendente\ncanal · destino · payload"]
    end

    F1 & F2 & F3 & F4 & F5 --> C1 --> C2 --> C3 --> D
```

---

## Estados de um despacho

```mermaid
stateDiagram-v2
    [*] --> pendente: INSERT (Nexus)
    pendente --> enviado: n8n entregou com sucesso
    pendente --> falhou: Evolution/SMTP retornou erro
    falhou --> pendente: retry automático (tentativas < 3, < 24h)
    enviado --> confirmado: confirmação de leitura (futuro)
    pendente --> cancelado: cancelamento manual
    falhou --> cancelado: tentativas esgotadas ou manual
```
