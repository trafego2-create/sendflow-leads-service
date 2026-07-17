# Handoff — Migração n8n → Python (SendFlow → Supabase → Google Sheets)

Sessão anterior ficou sem memória. Este arquivo resume tudo que foi feito e o que falta.

## Contexto do projeto

Empresa: Aprova Sim (cursos/mentorias, campanhas de captação via WhatsApp).
Lançamento atual: **PI-AGO-26** (Projeto INSS, agosto/2026).

Existia uma automação em **n8n** (webhook SendFlow → Supabase → Google Sheets) que captura leads
que entram/saem de grupos de WhatsApp. O usuário estava replicando essa automação de um lançamento
anterior (PES-MAI-26) para o novo (PI-AGO-26), copiando o workflow e trocando variáveis. A automação
não estava gravando nada no banco nem na planilha ("estão me cobrando").

Diagnosticamos vários bugs no n8n e, a pedido do usuário, **reescrevemos a automação inteira em
Python** (FastAPI), para rodar como serviço no EasyPanel em vez de n8n.

## Bugs encontrados no n8n original (contexto, já não importa pro Python)

1. Node `HTTP Request2` usava a URL da página do navegador
   (`/whats/campaigns/{id}/overview`) em vez da API
   (`/sendapi/releases/{id}/analytics`).
2. Node `Create a row` (Supabase) estava sem o campo `GRUPO DA CAMPANHA` no mapeamento.
3. Node `Update row in sheet4` (Google Sheets) tinha `matchingColumns: []` vazio → erro
   "Column to Match On is required".
4. **CAUSA RAIZ do "nada cai no banco"**: a tabela `PI_AGO_26` no Supabase tinha a coluna `ID`
   sem auto-incremento (Identity) configurado → todo INSERT falhava silenciosamente. **O usuário
   já corrigiu isso no Supabase** (Table Editor → coluna ID → ativou "Is Identity").
5. `ADMIN_OFFSET` usado na fórmula de cálculo de totais estava errado (1620); o valor certo,
   confirmado pelo usuário e por um colega (Luís Felipe), é **4794** (17 admins × 282 grupos).
6. Descoberta importante: `TOTAL LEADS` calculado pela fórmula do SendFlow
   (`add.total - offset - remove.total`) **não deduplica** — conta eventos brutos, não pessoas
   únicas. O valor correto de leads únicos deve vir do Supabase (`COUNT WHERE "LEAD ÚNICO" = 1`).

## O que foi construído

Projeto Python completo em **`C:\Users\trafe\Documents\sendflow-leads-service\`**:

```
app/
  config.py          → todas as configs vêm de env vars (pydantic-settings)
  supabase_client.py → get_lead, insert_lead, update_lead, get_leads_by_date,
                        count_unique_leads() [conta LEAD ÚNICO=1, fonte de verdade]
  sheets_client.py   → wrapper da Google Sheets API v4, com upsert_row (corrige o bug
                        do "Column to Match On" do n8n)
  sendflow_client.py → chama /sendapi/releases/{id}/analytics; já trata o fato de que a
                        API retorna uma LISTA com um objeto dentro, não o objeto direto
                        (bug descoberto testando com dado real)
  logic.py           → regras de negócio:
                        - handle_member_added: cria ou incrementa LEAD NÚMERO
                        - handle_member_removed: decrementa; LEAD ÚNICO vira 0 só quando
                          LEAD NÚMERO <= 0 (dedup correto, testado e validado)
                        - handle_campaign_metrics: evento webhook em tempo real
                        - poll_analytics: roda a cada N min (ENTRADAS/SAÍDAS por dia
                          vêm do SendFlow porque não tem como saber isso pelo Supabase;
                          TOTAL LEADS vem do Supabase, não do SendFlow)
                        - daily_append: cria a linha do dia na planilha à meia-noite
  main.py            → FastAPI + webhook POST + APScheduler (poll a cada 2 min,
                        append diário 00:00 America/Sao_Paulo)
requirements.txt
Dockerfile
.env                 → JÁ TEM AS CREDENCIAIS REAIS preenchidas (não commitar, está no
                        .gitignore)
.env.example
.gitignore
README.md            → passo a passo de deploy
```

### Credenciais já configuradas em `.env` (reais, testadas e funcionando)

- `SUPABASE_URL=https://bjfapsvlhojiouarbzap.supabase.co`
- `SUPABASE_SERVICE_KEY` = service_role JWT (já no arquivo)
- `SUPABASE_TABLE=PI_AGO_26`
- `GOOGLE_SERVICE_ACCOUNT_JSON` = service account `sendflow-leads-bot@n8n-trigrrer.iam.gserviceaccount.com`
  (projeto GCP `n8n-trigrrer`) — **chave privada validada e funcional**
- `GOOGLE_SHEET_ID=1QPpVLzJtREtyOTNYBvq8RNNtGq8DV62i744FVQ2NQj4` (planilha "Captação [PI-AGO-26]")
- `SENDFLOW_API_TOKEN` = token atual (pode ter sido trocado por um novo — checar com o usuário)
- `SENDFLOW_CAMPAIGN_ID=8AZ6TTPsLRzqAgJgYUt7`
- `ADMIN_OFFSET=4794`

### Testes já rodados e validados (ambiente local, venv em `.venv/`)

- ✅ Config carrega, chave da service account válida
- ✅ Insert/update/delete no Supabase funcionando (depois do fix do ID identity)
- ✅ Ciclo completo lead entra→sai→entra→sai testado: `LEAD NÚMERO` incrementa/decrementa
  certo, `LEAD ÚNICO` só zera quando sai de tudo
- ✅ SendFlow API responde 200 com dados reais quando testada a partir de dentro do n8n
  (o 403 que aparecia nos meus testes era bloqueio de IP do meu sandbox, não do token)
- ✅ **Testado em 15/07/2026**: usuário compartilhou a planilha "Captação [PI-AGO-26]" com
  `sendflow-leads-bot@n8n-trigrrer.iam.gserviceaccount.com` como Editor. Reexecutado
  `_service.spreadsheets().get(spreadsheetId=_sheet_id, ...)` — acesso OK. Aba configurada no
  `.env` (`GOOGLE_SHEET_NAME=LEAD TOTAL`) existe na planilha (junto com outras abas de extração
  não usadas por este projeto: EXTRACAO-BM, EXTRACAO-GA4, EXTRACAO-GA, EXTRACAO-TK,
  EXTRACAO-SEARCH, EXTRACAO-PMAX, EXTRACAO-GA DISPLAY, LEAD TOTAL VIPS, Captação Geral
  [PBB-JUN-26]).

## Análise de backfill histórico (em andamento, ainda NÃO gravado no banco)

O usuário exportou do SendFlow um CSV com o histórico completo de atividade
(6.458 eventos, de 29/05/2026 até 15/07/2026), salvo em:
`C:\Users\trafe\Downloads\SendFlow - Histórico de atividade - 15-07-2026,_15-09-04.csv`

Processei esse arquivo com Python (script ad-hoc, não salvo — refazer se precisar, é simples:
ler CSV `;`-separado, parsear `Numero` removendo aspas simples do início, `Data` no formato
`%d/%m/%Y, %H:%M:%S`).

**Descoberta**: números que agem como admin/staff (mesmo prefixo `5516...`, entram em dezenas/
centenas de grupos `Projeto INSS #2` a `#283` — que são só grupos de reserva) precisam ser
excluídos. O critério mais confiável (confirmado pelo usuário: só o grupo **"Projeto INSS #1"**
recebe leads reais, os outros 282 são reserva/staff) é **filtrar só eventos onde
`Grupo == "Projeto INSS #1"`**.

Resultado final desse filtro:
- **900 leads únicos** (por NÚMERO) já passaram pelo grupo #1 em algum momento
- **855 com `LEAD ÚNICO = 1`** (ainda estão em pelo menos um grupo)
- **45 com `LEAD ÚNICO = 0`** (saíram)

Isso é bem diferente do que a fórmula antiga do SendFlow dava (1477) — a fórmula antiga não
deduplica e provavelmente está inflada.

Os 900 registros computados (com `DATA1`, `GRUPO DA CAMPANHA`, `LEAD NÚMERO`, `LEAD ÚNICO`,
`NÚMERO` já no formato certo pra inserir no Supabase) estão salvos em:
`C:\Users\trafe\Documents\sendflow-leads-service\leads_preview.json`

**✅ FEITO (15/07/2026)**: usuário confirmou e os 900 registros foram gravados na tabela
`PI_AGO_26` via script ad-hoc (insert em 9 lotes de 100, usando `app/supabase_client.py`).
Verificado depois: 900 linhas na tabela, 855 com `LEAD ÚNICO = 1` — bate com o esperado.
Tabela estava vazia antes do insert (confirmado via count antes de rodar).

**✅ FEITO (15/07/2026)**: planilha compartilhada pelo usuário com a service account como Editor,
acesso testado e confirmado.

**✅ RESOLVIDO (15/07/2026)**: token do SendFlow no `.env` não precisa ser trocado — usuário
confirmou que o atual está funcionando (não gerou um novo).

**✅ FEITO (16/07/2026) — Deploy completo**:
- Repo criado em `github.com/trafego2-create/sendflow-leads-service` (público — o
  `leads_preview.json` foi removido do histórico do git antes de tornar público, por ter
  900 números de WhatsApp reais).
- App `contagem-leads` criado no EasyPanel (projeto `typebot`), conectado ao repo via GitHub,
  branch `main`, build automático via Dockerfile.
- Domínio: `https://typebot-contagem-leads.e4wfok.easypanel.host` — atenção: o mapeamento de
  porta precisou ser corrigido manualmente de 80 para **8000** (porta que o Uvicorn expõe) em
  Domains → editar.
- 10 variáveis de ambiente cadastradas no EasyPanel (as do `.env`, exceto as removidas — ver
  abaixo).
- Sendhook configurado no SendFlow apontando pra
  `https://typebot-contagem-leads.e4wfok.easypanel.host/webhook/sendflow`, eventos: Membro
  adicionado, Membro removido, Métricas da campanha.
- Teste end-to-end confirmado: webhook responde 200 OK e grava no Supabase (teste gerou uma
  linha fake `NÚMERO=0`, `ID=902` — **precisa ser apagada** antes do lançamento valer pra
  contagem real, ver "Loose ends" abaixo).

**✅ RESOLVIDO (16/07/2026) — poll_analytics removido**: o job que consultava
`/sendapi/releases/{id}/analytics` a cada 2 min dava 403 Forbidden consistente (testado
diretamente, não era rate limit nem configuração pendente do Sendhook). Descoberta: o n8n
original nunca usou esse endpoint — só processava entrada/saída de membro via webhook, e o
evento `campaign.metrics` (que dá TOTAL GRUPOS CHEIOS) já chega por **push** do próprio
SendFlow nos horários configurados no Sendhook (ex: 7h/12h/17h), sem precisar de polling ativo.
Removido: `app/sendflow_client.py`, a função `poll_analytics` em `logic.py`, e as env vars
`SENDFLOW_BASE_URL`, `SENDFLOW_API_TOKEN`, `SENDFLOW_CAMPAIGN_ID`, `ADMIN_OFFSET`,
`POLL_INTERVAL_MINUTES` (não são mais usadas pelo código). Commit `c43dcee`.

**✅ FEITO (16/07/2026) — Linha de teste apagada**: `ID=902`, `NÚMERO=0` removida do Supabase.

**✅ FEITO (16/07/2026) — Conferência de dados / reconciliação**: usuário exportou novo CSV do
SendFlow (histórico até 16/07 11:06, 6.706 eventos) e enviou pra comparar com o Supabase.
Processo (mesmo filtro `Grupo == "Projeto INSS #1"`, mesma lógica de `LEAD NÚMERO`/`LEAD ÚNICO`
do backfill original):
- CSV mostrou 945 números únicos que já entraram no grupo #1 em algum momento.
- Supabase tinha só 920 (antes da reconciliação) — **45 leads reais estavam faltando**,
  provavelmente do período de transição n8n→Python em que nem sempre havia captura funcionando.
- Calculado `LEAD NÚMERO`/`LEAD ÚNICO`/`DATA1` pra esses 45 (a partir do histórico completo de
  eventos de cada um, não só a última ocorrência) e inseridos no Supabase.
- Estado final: **967 linhas, 920 com LEAD ÚNICO=1**.
- Também calculada a tabela ENTRADAS/SAÍDAS/RELAÇÃO(E/S) por dia do grupo #1 (números únicos,
  dedupe por dia) — entregue no chat pro usuário colar manualmente no Sheet (por decisão dele,
  pra não arriscar mexer na automação). Confirmado que o "83 entradas/9 saídas" que aparecia no
  Sheet pro dia 16/07 era o agregado bruto de todos os grupos (inclusive reserva/staff), não
  filtrado — o número real do grupo #1 era 0 entradas/4 saídas nesse dia.
- **Verificado duplicação n8n vs Python**: comparando `LEAD NÚMERO` calculado do CSV vs o que
  estava no Supabase, **nenhum caso de duplicação/dobra** foi encontrado — os dados de lead em
  si (tabela `PI_AGO_26`) estavam limpos. Achado, sim: 18 leads que já tinham saído do grupo
  (segundo o CSV) mas o Supabase ainda mostrava `LEAD ÚNICO=1` (saída nunca processada, mesmo
  período de transição). Corrigido: `LEAD NÚMERO=0`, `LEAD ÚNICO=0` pra esses 18.
- Estado final pós-reconciliação: 968 linhas, contagem `LEAD ÚNICO=1` voltou a subir
  organicamente (leads reais entrando em tempo real via webhook) — não fixar esse número no
  handoff, sempre reconsultar o Supabase.

**✅ FEITO (16/07/2026) — Conflito com n8n identificado e resolvido (planilha)**: mesmo com o
Supabase limpo, a **planilha** (Sheets) continuava sendo sobrescrita porque o **workflow antigo
do n8n continuava ativo em paralelo** (usuário mantinha ligado "pra não perder dado"):
- Um node HTTP do n8n (`HTTP Request2`) chama exatamente `/sendapi/releases/{id}/analytics` —
  a mesma rota que dava 403 no nosso Python — só que **funciona do servidor do n8n** (confirma
  que o bloqueio da SendFlow é por IP, não pelo token). O resultado desse node alimentava
  `TOTAL GRUPOS CHEIOS`/`TOTAL LEADS` na aba com a fórmula antiga (inflada), sobrescrevendo o
  valor certo que a gente escrevia. **Usuário desativou esse node.**
- Havia também outro mecanismo do n8n escrevendo/limpando a tabela `DATA2` (histórico diário
  ENTRADAS/SAÍDAS) — linhas de julho sumiram e a de 29/05 voltou pro valor bruto (87/9/78) depois
  que a gente já tinha escrito o valor certo. **Ainda não resolvido** — precisa confirmar que o
  workflow inteiro do n8n está com o toggle "Active" desligado (não só nodes individuais) antes
  de reescrever essa tabela de novo, senão apaga tudo outra vez.
- **Descoberta sobre o design da planilha**: a célula `TOTAL LEADS` (linha 2) é o valor **bruto**
  esperado por uma fórmula já existente na planilha, `TOTAL LIMPO = TOTAL LEADS - QTD. de ADMs`
  (linha 3). Primeira tentativa: reintroduzir `ADMIN_OFFSET=4794` e escrever
  `count_unique_leads() + ADMIN_OFFSET` (commit `c15839b`) — funcionou, mas é um número
  sintético que pode desatualizar.
- **✅ FEITO (17/07/2026) — Corrigido pra bater com o n8n original**: usuário mandou o JSON do
  workflow n8n "base" (campanha antiga PES-MAI-26) pra comparar. Achado: o node
  `Update row in sheet7` do n8n sempre escreveu `TOTAL LEADS = body.data.participantsAmount`
  (o valor bruto **real**, direto do payload do SendFlow) — não um offset sintético. Corrigido:
  `handle_campaign_metrics` agora usa `data.get("participantsAmount")` direto (igual ao n8n
  original), removido `ADMIN_OFFSET`/`admin_offset` de novo do código (não é mais necessário —
  o `QTD. de ADMs` é só um valor fixo na própria planilha, célula L2, não precisa de env var).
  `LEADS NO DIA` continua recebendo o total **limpo** (Supabase, deduplicado) — diferente do
  n8n original, que também jogava o bruto ali; decisão deliberada, mantendo o número real de
  movimentação sem admin misturado. Commit `a6fddd6`.
- Também corrigido: nada atualizava `LEADS NO DIA` automaticamente antes — agora
  `handle_campaign_metrics` faz upsert nessa linha a cada push, e `daily_append` (meia-noite)
  cria a linha do dia seguinte, congelando o valor final do dia anterior.

## Loose ends / falta fazer

1. **Redeploy pendente no EasyPanel** — o commit com a reintrodução do `ADMIN_OFFSET` (escrito
   como bruto pra fórmula da planilha) precisa ser deployado manualmente (auto-deploy via push
   não está configurado, sempre precisa clicar em Deploy no painel depois do push).
2. **Confirmar que o workflow inteiro do n8n está desativado** (toggle "Active", não só nodes
   individuais) antes de reescrever a tabela `DATA2` (histórico diário) de novo — ela continua
   sendo sobrescrita/limpa por algo do n8n.
3. Depois de confirmado, reescrever a tabela `DATA2` completa (todos os 25 dias já calculados,
   de 29/05 a 16/07 — os valores estão no histórico desta conversa, ou recalculáveis do CSV em
   `C:\Users\trafe\Downloads\SendFlow - Histórico de atividade - 16-07-2026,_11-06-04.csv`
   filtrando `Grupo == "Projeto INSS #1"`, deduplicando por número por dia).
4. Considerar remover as env vars não usadas (`SENDFLOW_BASE_URL`, `SENDFLOW_API_TOKEN`,
   `SENDFLOW_CAMPAIGN_ID`, `POLL_INTERVAL_MINUTES`) do painel de Environment do EasyPanel — não
   quebram nada ficando (pydantic ignora extras), é só limpeza. `ADMIN_OFFSET` voltou a ser usado,
   não remover esse.
5. Revogar/trocar tokens que foram colados em prints durante a sessão (GitHub PAT usado
   temporariamente pra configurar o EasyPanel, se ainda existir; verificar em
   `github.com/settings/tokens`).

## Prompt para continuar em outra sessão

Cole isto na próxima conversa:

---

Estou continuando um projeto que comecei numa sessão anterior que ficou sem memória. Lê o
arquivo `C:\Users\trafe\Documents\sendflow-leads-service\HANDOFF.md` inteiro primeiro — ele tem
todo o contexto (o que é o projeto, bugs já corrigidos, credenciais já configuradas, e o que
falta fazer). Depois disso, me pergunta qual dos itens da seção "O que falta fazer" eu quero
tocar primeiro — não presuma, porque a prioridade pode ter mudado desde que escrevi o handoff.
Item mais urgente pra confirmar comigo assim que ler: se pode gravar os 900 leads do
`leads_preview.json` na tabela `PI_AGO_26` do Supabase (isso ainda não foi feito).

---
