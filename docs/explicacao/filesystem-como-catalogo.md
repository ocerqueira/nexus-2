# Explicação — Filesystem como catálogo

## O problema

Em sistemas tradicionais de relatórios, adicionar um novo relatório exige:

1. Escrever uma migration SQL para registrá-lo no banco
2. Criar uma rota nova ou modificar um switch gigante
3. Tocar código existente em múltiplos lugares
4. Reiniciar a aplicação

Isso cria atrito e risco. Cada novo relatório é uma mudança de código que pode quebrar o sistema.

## A solução do Nexus

No Nexus, **o filesystem é a fonte de verdade**. A tabela do banco (`relatorios` ou `alertas`) é uma cópia sincronizada automaticamente.

```
app/
  relatorios/
    teste_conexoes/          ← esta pasta É o relatório
      config.json            ← metadados (título, descrição, parâmetros)
      consultas.sql          ← queries SQL com marcadores -- name:
      processador.py         ← classe Python (validar + buscar_dados)
      template.html          ← template Jinja2
```

O que acontece na inicialização:

1. O `Sincronizador` lista todas as pastas em `app/relatorios/` (ignorando `__pycache__`, pastas começando com `_` ou `.`)
2. Para cada pasta, lê `config.json` e extrai título, descrição, categoria
3. Compara com o que existe no banco:
   - Pasta nova → `INSERT` com status `ativo`
   - Pasta existente → `UPDATE` dos metadados
   - Pasta sumiu → `UPDATE` status para `removido`
4. Se a pasta reaparecer, o status volta para `ativo` ("reativação")

## Vantagens

### 1. Versionamento

Relatórios e alertas são arquivos. Eles vivem no Git junto com o código. Um pull request que adiciona um relatório contém tudo: SQL, lógica Python, template HTML, configuração.

### 2. Criação sem tocar código existente

Criar um relatório não modifica **nenhum** arquivo do core. O processador é descoberto automaticamente pela convenção de nome (classe `Processador*` em `processador.py`, via `app/core/processadores.py`). O orquestrador, o renderizador, as rotas — nada disso muda.

### 3. Remoção segura

Se uma pasta é deletada, o banco marca `status = 'removido'` em vez de deletar o registro. Isso preserva o histórico de execuções e permite reverter a remoção simplesmente recriando a pasta.

### 4. Descoberta automática

Não há necessidade de rodar migrations. O `POST /sincronizar` reflete mudanças no filesystem sem reiniciar a aplicação.

## Limitações

### Contrato validado só por convenção

A descoberta usa `importlib` + convenção de nome: a classe em `processador.py` precisa começar com `Processador` e implementar o contrato (`validar` + `buscar_dados` para relatórios, `validar` + `verificar` para alertas). Nada disso é imposto pelo Python em si — por isso o sincronizador verifica o contrato de cada pasta **no startup** e loga um *warning* para pastas quebradas, em vez de o erro só aparecer no primeiro disparo.

### Inicialização bloqueante

A sincronização acontece no startup da aplicação. Se houver centenas de pastas, o tempo de inicialização aumenta. Para a maioria dos casos (dezenas de relatórios), o impacto é desprezível.

## Comparação com alternativas

| Abordagem | Adicionar relatório | Versionamento | Remoção segura |
|-----------|---------------------|---------------|----------------|
| **Nexus (filesystem)** | Criar pasta (descoberta automática) | Git (arquivos) | Status `removido` |
| API dinâmica (upload) | Upload de arquivos | Precisa de sistema externo | Manual |
| Tudo no banco | SQL + migration | Precisa versionar migrations | Soft delete |
| Código hardcoded | Editar switch/rotas | Git (código) | Reverter código |
