# SendFlow Leads Service

Reimplementação em Python do fluxo n8n de captação de leads (SendFlow → Supabase → Google Sheets), pensada pra rodar como um único container genérico: trocando as variáveis de ambiente, a mesma imagem serve qualquer lançamento.

## O que faz

- **Webhook** (`POST /webhook/sendflow`): recebe os eventos do sendhook do SendFlow em tempo real.
  - `group.updated.members.added` → cria/atualiza o lead no Supabase
  - `group.updated.members.removed` → decrementa o contador do lead no Supabase
  - `campaign.metrics` → atualiza a linha de totais (linha 2) da planilha na hora (o SendFlow envia esse evento por push nos horários configurados no Sendhook, ex: 7h/12h/17h)
- **Append diário** (00:00 no fuso `TIMEZONE`): cria a linha do dia na planilha.

Não há polling ativo na API do SendFlow — só processamos o que chega via webhook. Uma versão anterior tentava consultar `/sendapi/releases/{id}/analytics` a cada poucos minutos, mas esse endpoint retornava 403 com o token de API disponível (provavelmente só acessível pelo painel logado), e o n8n original também nunca usou essa rota.

## Diferenças em relação ao workflow n8n original

- O update na planilha por `DATA` agora faz **upsert** (se a linha do dia não existir ainda, cria em vez de falhar) — isso corrige o bug do "Column to Match On" que estava derrubando o `Update row in sheet4`.
- A cadeia de nodes vestigiais (`Get row(s) in sheet` → `Get many rows2` → `Code in JavaScript10` → `Edit Fields12` no evento `campaign.metrics`) foi removida — os valores finais gravados nunca dependiam desses nodes intermediários, só do payload do webhook.

## Setup local

```bash
cp .env.example .env
# edite o .env com os valores reais
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Credencial do Google (Service Account)

1. [Google Cloud Console](https://console.cloud.google.com/) → **IAM e Admin → Contas de serviço → Criar conta de serviço**
2. Na conta criada → aba **Chaves → Adicionar chave → JSON** (baixa um arquivo)
3. Habilite a **Google Sheets API** em **APIs e Serviços → Biblioteca**
4. Abra a planilha de captação → **Compartilhar** → adicione o e-mail da service account (`...@projeto.iam.gserviceaccount.com`) como **Editor**
5. Cole o conteúdo do JSON (em uma linha só) na variável `GOOGLE_SERVICE_ACCOUNT_JSON`

## Deploy no EasyPanel (build automático via Git)

1. Suba esta pasta num repositório Git (GitHub/GitLab) — **não commite o `.env`**, ele já está no `.gitignore`
2. No EasyPanel: **Criar App → From Git Repository**, aponte pro repositório
3. Ele vai detectar o `Dockerfile` e buildar automaticamente a cada push
4. Em **Environment**, cadastre todas as variáveis do `.env.example` com os valores reais (inclusive o `GOOGLE_SERVICE_ACCOUNT_JSON` inteiro)
5. Configure a porta exposta como `8000` e gere/aponte o domínio do EasyPanel pro app
6. No SendFlow, em **Sendhooks**, aponte (ou crie um novo) para `https://SEU-DOMINIO-EASYPANEL/webhook/sendflow`, marcando os eventos: Membro adicionado, Membro removido, Métricas da campanha
7. Envie o teste do sendhook e confira em `GET /healthz` que o app está de pé, e no Supabase/planilha se o teste caiu

## Trocar de lançamento

Não precisa mexer em código — só trocar as env vars no EasyPanel:
`SUPABASE_TABLE`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_NAME`, `WEBHOOK_PATH`.
