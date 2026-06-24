# Guia — Recuperar chave de criptografia

**Problema**: Você perdeu a chave de criptografia Fernet do `.env` e precisa recuperar o acesso às conexões cadastradas, ou gerar uma nova chave.

---

## Cenário A: A chave está em um gerenciador de senhas

Se a chave foi armazenada em 1Password, Bitwarden ou similar:

1. Abra o gerenciador de senhas
2. Busque por "Nexus - Chave de Criptografia"
3. Copie o valor
4. Atualize o `.env`:

```bash
CHAVE_CRIPTOGRAFIA=<chave-copiada>
```

5. Reinicie a aplicação

## Cenário B: Não há backup da chave

Se a chave foi **perdida definitivamente**, as senhas criptografadas são irrecuperáveis. O procedimento é:

### 1. Aceite a perda

Senhas armazenadas em `conexoes_bd.senha_criptografada` são cifradas com AES-128 (Fernet). Sem a chave original, a descriptografia é inviável.

### 2. Limpe a tabela de conexões

```sql
TRUNCATE conexoes_bd CASCADE;
```

O `CASCADE` também remove as referências em `grupos_conexoes_itens` e no histórico.

### 3. Gere uma nova chave

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Atualize o `.env`

```bash
CHAVE_CRIPTOGRAFIA=<nova-chave>
```

### 5. Recadastre as conexões

Siga o guia [Adicionar uma conexão de banco externo](adicionar-conexao.md) para cada conexão.

## Cenário C: A chave está corrompida

Se o Nexus retorna erro de descriptografia (`InvalidToken`) mas você tem certeza de que a chave está correta:

1. Verifique se há espaços ou quebras de linha no valor da chave no `.env`
2. A chave Fernet tem exatamente 44 caracteres Base64 (terminando em `=`)
3. Teste a chave manualmente:

```bash
uv run python -c "
from cryptography.fernet import Fernet
f = Fernet('sua-chave-aqui'.encode())
print(f.decrypt(b'gAAAAA...'))  # substitua por um valor criptografado do banco
"
```

## Prevenção

- **Sempre armazene a chave em um gerenciador de senhas** após gerá-la
- **Adicione a chave ao arquivo `RECUPERACAO.md`** do projeto (não commite no Git — use o gerenciador de senhas)
- **Faça backup do `.env`** em local seguro (fora do repositório)

---

**Ver também**:
- [Explicação — Modelo de segurança](../explicacao/modelo-de-seguranca.md)
- [Referência — Configuração](../referencia/configuracao.md)
