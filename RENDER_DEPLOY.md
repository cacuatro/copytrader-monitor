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
DATABASE_URL=postgresql://postgres:SENHA@db.xxxxx.supabase.co:5432/postgres
```

Opcional:

```txt
USD_BRL_RATE=5.0000
```

Use `USD_BRL_RATE` apenas se quiser fixar manualmente a cotacao USD/BRL. Sem ela, o sistema busca a cotacao automaticamente.

## Supabase

Para manter acessos, comunicados, auditoria e edicoes de clientes salvos apos redeploy/restart do Render:

1. Crie um projeto no Supabase.
2. Acesse `Project Settings` > `Database` > `Connection string`.
3. Copie a connection string no formato `postgresql://...`.
4. No Render, adicione a variavel `DATABASE_URL` com essa URL.

Quando `DATABASE_URL` existir, o sistema cria automaticamente as tabelas `copytrader_state`, `copytrader_access_logs` e `copytrader_audit_logs`.

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

## Protecoes da integracao MyFXBook

O monitor reutiliza a sessao por ate 29 dias, renovando quando a API a rejeita.
A API vincula sessoes ao IP de origem; persistir uma sessao nao garante que ela
continue valida apos mudanca de IP.

As chamadas sao serializadas, com intervalo conservador de 1,5 segundo entre
elas, e consultas iguais aproveitam o cache. Esse intervalo nao e uma garantia
nem um limite oficial do MyFXBook. Falhas de login pausam novas chamadas por
15 minutos; HTTP 429 respeita tambem Retry-After quando maior. A pausa e salva
no banco configurado ou em JSON local e nao e removida pelo botao de atualizar.
No Render, configure DATABASE_URL para persistir a pausa entre redeploys;
arquivos locais em armazenamento efemero podem desaparecer.

A fila e o bloqueio de login sao por processo. Mantenha um unico worker/instancia
para esta integracao; varios processos exigem coordenacao distribuida adicional.
Nao use a mesma sessao salva em ambientes com IPs diferentes.

Validacao local sem chamadas reais ou alteracao de credenciais:

```powershell
backend/venv/Scripts/python.exe -B -W ignore::DeprecationWarning -m unittest discover -s tests -v
```
