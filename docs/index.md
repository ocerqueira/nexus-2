# Nexus — Documentação

Bem-vindo à documentação do **Nexus**, o sistema agnóstico de geração de relatórios e alertas. O Nexus funciona como uma API que expõe relatórios e alertas cadastrados no filesystem, prontos para consumo por ferramentas de automação como N8N.

## Como usar esta documentação

Esta documentação segue o framework **Diátaxis**, organizada em quatro seções com propósitos distintos:

| Seção | Propósito | Quando usar |
|-------|-----------|-------------|
| [Tutoriais](tutoriais/index.md) | Aprenda fazendo | Você é novo no Nexus e quer ver funcionando |
| [Guias de instrução](guias-de-instrucao/index.md) | Resolva problemas | Você sabe o que quer fazer, mas não sabe os passos exatos |
| [Referência](referencia/index.md) | Consulte detalhes técnicos | Você precisa de informações precisas sobre um componente |
| [Explicação](explicacao/index.md) | Entenda os conceitos | Você quer compreender as decisões de arquitetura e design |

## Visão geral

O Nexus é uma API FastAPI que:

- **Mantém um catálogo de relatórios e alertas** sincronizado com o filesystem — criar um novo relatório é tão simples quanto criar uma pasta com `config.json`, `consultas.sql` e `processador.py`
- **Conecta-se a múltiplos bancos externos** (PostgreSQL, Firebird, MySQL) com credenciais criptografadas
- **Renderiza saídas em múltiplos formatos**: JSON (para consumo por API), HTML (para e-mail/web) e PDF (para download)
- **Orquestra notificações** com cooldown, destinatários, múltiplos canais (e-mail, WhatsApp) e templates Jinja2

## Comece por aqui

- **Primeiro contato**: [Tutorial — Primeira execução](tutoriais/primeira-execucao.md)
- **Precisa resolver algo?**: [Guias de instrução](guias-de-instrucao/index.md)
- **Quer entender a arquitetura?**: [Explicação — Arquitetura](explicacao/arquitetura.md)
