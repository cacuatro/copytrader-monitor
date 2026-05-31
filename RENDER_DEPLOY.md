# Deploy no Render

Este projeto roda frontend e backend no mesmo servico do Render.

## Configuracao

1. No Render, crie um novo Blueprint usando este repositorio.
2. O Render vai ler o arquivo `render.yaml` automaticamente.
3. Configure as variaveis de ambiente do servico:

```txt
MYFXBOOK_EMAIL=seu_email_myfxbook
MYFXBOOK_PASSWORD=sua_senha_myfxbook
AUTH_SECRET=um_texto_grande_e_aleatorio
TOKEN_TTL_HOURS=12
ADMIN_USERNAME=seu_usuario_admin
ADMIN_PASSWORD=sua_senha_admin_segura
SUPPORT_WHATSAPP=5548999999999
```

Opcional:

```txt
USD_BRL_RATE=5.0000
```

Use `USD_BRL_RATE` apenas se quiser fixar manualmente a cotacao USD/BRL. Sem ela, o sistema busca a cotacao automaticamente.

## Links

Depois do deploy, use:

```txt
https://seu-projeto.onrender.com/?cliente=rayla
https://seu-projeto.onrender.com/admin
```

Health check da API:

```txt
https://seu-projeto.onrender.com/api/status
```
