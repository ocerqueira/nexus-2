# Explicação — Modelo de segurança

## Visão geral

O Nexus lida com credenciais de bancos de dados externos. Senhas em texto puro no banco seriam um risco inaceitável. O sistema adota criptografia simétrica com Fernet (AES-128 em modo CBC com HMAC) para proteger esses dados.

## Como funciona

### Criptografia

```python
from cryptography.fernet import Fernet

# 1. Geração da chave (feita uma vez, armazenada no .env)
chave = Fernet.generate_key()  # ex: b'abc123def456...='  (44 chars Base64)

# 2. Criptografar senha (antes de inserir no banco)
fernet = Fernet(chave)
senha_criptografada = fernet.encrypt(b"minhaSenha123")
# → b'gAAAAABl...'  (token Fernet)

# 3. Armazenar no banco
INSERT INTO conexoes_bd (..., senha_criptografada)
VALUES (..., 'gAAAAABl...');
```

### Descriptografia

```python
# 1. Buscar do banco
senha_criptografada = "gAAAAABl..."

# 2. Descriptografar (só em memória, nunca em disco/log)
fernet = Fernet(chave)
senha_pura = fernet.decrypt(senha_criptografada.encode()).decode()
# → "minhaSenha123"

# 3. Usar para montar URL de conexão
url = f"postgresql+psycopg://{usuario}:{senha_pura}@{host}:{porta}/{banco}"
```

### Onde a descriptografia acontece

A descriptografia acontece **apenas** no método `_montar_url()` do `GerenciadorConexoes`, que é chamado sob demanda quando uma engine é criada. A senha em texto puro:

- Nunca é armazenada em disco
- Nunca aparece em logs
- Vive apenas em memória durante a montagem da URL
- A URL é passada diretamente para o `create_engine()` do SQLAlchemy

## A chave de criptografia

### Geração

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A chave tem 44 caracteres Base64 (32 bytes de chave AES + 16 bytes de assinatura HMAC).

### Armazenamento

A chave vive no arquivo `.env`:

```bash
CHAVE_CRIPTOGRAFIA=abc123def456...=
```

O `.env` **não deve ser commitado** no Git. O `.gitignore` do projeto já inclui `.env`.

### Risco de perda

Se a chave for perdida, **todas as senhas criptografadas são irrecuperáveis**. O Fernet usa AES-128, que não tem backdoor. O procedimento de recuperação está documentado em [Recuperar chave de criptografia](../guias-de-instrucao/recuperar-chave-criptografia.md).

## Superfície de ataque

| Vetor | Risco | Mitigação |
|-------|-------|-----------|
| `.env` exposto no repositório | Alto | `.gitignore` + revisão de PR |
| Chave em log | Médio | A chave nunca é logada; logs usam `logging` sem a chave |
| Senha em log | Médio | A senha pura nunca é logada; o `GerenciadorConexoes` não loga URLs |
| Acesso ao banco Nexus | Alto | Quem lê `conexoes_bd` vê tokens Fernet, não senhas — mas com acesso ao `.env` pode descriptografar |
| Memória do processo | Baixo | A senha pura existe em memória por milissegundos durante `_montar_url()` |

## O que NÃO é criptografado

- Metadados de conexão: host, porta, nome do banco, usuário — são armazenados em texto puro
- Dados de relatórios e alertas
- Histórico de execuções
- Templates e configurações

Apenas o campo `conexoes_bd.senha_criptografada` é protegido.

## Alternativas consideradas

| Alternativa | Por que não foi usada |
|-------------|----------------------|
| Variáveis de ambiente por conexão | Não escala — cada conexão precisaria de uma variável; o catálogo no banco é mais prático |
| Vault (HashiCorp) | Complexidade desnecessária para o escopo atual; pode ser adicionado depois |
| KMS da nuvem | Acoplamento com provedor; o Nexus é agnóstico de infraestrutura |
| Senha em texto puro | Risco inaceitável em qualquer cenário |

## Evolução futura

O modelo atual é adequado para o escopo do Nexus. Se o sistema crescer:

- **Rotação de chaves**: Suporte a múltiplas chaves Fernet com período de transição
- **Vault integration**: Buscar senhas sob demanda de um cofre externo em vez do banco
- **Criptografia em repouso**: PostgreSQL com TDE (Transparent Data Encryption) para proteger todo o banco
