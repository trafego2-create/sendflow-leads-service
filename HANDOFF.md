# Handoff — SendFlow → Supabase → Google Sheets (Aprova Sim)

Documento consolidado. Se você está retomando esse projeto numa sessão nova, leia isso inteiro
antes de fazer qualquer coisa — depois disso o [Prompt para continuar](#prompt-para-continuar-em-outra-sessão)
no final tem um checklist do que perguntar.

## O que é esse projeto

Empresa: Aprova Sim (cursos/mentorias, campanhas de captação via WhatsApp).
Lançamento atual: **PI-AGO-26** (Projeto INSS, agosto/2026).

Serviço Python (FastAPI) em **`C:\Users\trafe\Documents\sendflow-leads-service\`**, repositório
`github.com/trafego2-create/sendflow-leads-service` (público), rodando no EasyPanel (projeto
`typebot`, serviço `contagem-leads`, URL `https://typebot-contagem-leads.e4wfok.easypanel.host`).

Recebe webhooks do SendFlow (entrada/saída de membro em grupos de WhatsApp + métricas da
campanha) e mantém sincronizados: uma tabela no Supabase (fonte de verdade dos leads) e uma
planilha do Google Sheets (visualização/relatório pra equipe).

**Substituiu uma automação em n8n** que tinha vários bugs (detalhes na seção de histórico, no
fim deste arquivo) e que ainda pode estar rodando em paralelo — ver seção "n8n" abaixo.

**Pode ter vários lançamentos/campanhas rodando ao mesmo tempo** (inclusive campanhas VIP, que
são uma campanha separada no SendFlow referente ao mesmo lançamento, escrevendo na mesma
planilha só que numa aba diferente). Cada combinação ativa ao mesmo tempo = uma instância
separada desse serviço (app próprio no EasyPanel). Ver `NOVO-LANCAMENTO.md` pra configurar uma
nova.

## Arquitetura atual

```
app/
  config.py           → configs via env vars (pydantic-settings), ver lista completa abaixo
  supabase_client.py   → get_lead, insert_lead, update_lead, count_unique_leads()
  sheets_client.py      → wrapper Sheets API v4: upsert_row, update_summary_row, increment_cell
  logic.py               → regras de negócio (detalhe abaixo)
  main.py                → FastAPI + webhook POST + APScheduler
NOVO-LANCAMENTO.md    → guia passo a passo pra configurar esse serviço num lançamento novo
```

### `logic.py` — o que cada handler faz

- **`handle_member_added`** (evento `group.updated.members.added`): se o número está em
  `ADMIN_NUMBERS`, ignora (log + return). Senão, cria ou incrementa `LEAD NÚMERO` no Supabase,
  seta `LEAD ÚNICO=1`, e incrementa `ENTRADAS` da linha de hoje na planilha (tabela `DATA2`).
- **`handle_member_removed`** (evento `group.updated.members.removed`): mesmo filtro de admin.
  Decrementa `LEAD NÚMERO`; `LEAD ÚNICO` só vira `0` quando `LEAD NÚMERO <= 0`. Incrementa
  `SAÍDAS` da linha de hoje.
- **`handle_campaign_metrics`** (evento `campaign.metrics`, chega por **push** do SendFlow nos
  horários configurados no Sendhook — normalmente 7h/12h/17h, não é polling): escreve
  `TOTAL GRUPOS CHEIOS` (= `groupsFullAmount` do payload) e `TOTAL LEADS` (= `participantsAmount`
  do payload, **valor bruto real**) na linha 2 da planilha. Também faz upsert de `LEADS NO DIA`
  (tabela `DATA`/`LEADS NO DIA`) com `count_unique_leads()` — esse sim é o **número limpo e
  deduplicado**, direto do Supabase.
- **`daily_append`** (cron, meia-noite `America/Sao_Paulo`): cria a linha do próximo dia na
  planilha (`DATA2`+`DATA` = hoje).

Falhas ao escrever na planilha **nunca** derrubam o processamento do Supabase nem propagam erro
pro webhook do SendFlow (evita retry/duplicação) — são só logadas.

## Env vars atuais em produção (EasyPanel → contagem-leads → Environment)

```
SUPABASE_URL=https://bjfapsvlhojiouarbzap.supabase.co
SUPABASE_SERVICE_KEY=<service_role JWT>
SUPABASE_TABLE=PI_AGO_26
GOOGLE_SERVICE_ACCOUNT_JSON=<JSON da service account sendflow-leads-bot@n8n-trigrrer.iam.gserviceaccount.com>
GOOGLE_SHEET_ID=1QPpVLzJtREtyOTNYBvq8RNNtGq8DV62i744FVQ2NQj4
GOOGLE_SHEET_NAME=LEAD TOTAL
ADMIN_NUMBERS=5516991081133,5516994054610,5516991876538,5516994602791,5516991628640,5516992243112,5516992352349,5516997384603,5516992314699,5516992162853,5516992932850,5516993910017,5516994109615,5516991262116,5516992580599,5516993966587,5516993678375,5516997353630
TIMEZONE=America/Sao_Paulo
WEBHOOK_PATH=/webhook/sendflow
PORT=8000
```

Ainda tem lixo não-usado sobrando (`SENDFLOW_BASE_URL`, `SENDFLOW_API_TOKEN`,
`SENDFLOW_CAMPAIGN_ID`, `ADMIN_OFFSET`, `POLL_INTERVAL_MINUTES`, `CAMPAIGN_GROUP_NAME`) — não
quebram nada (pydantic ignora extras), é só limpeza pendente.

**Importante sobre deploy**: auto-deploy via push **não está configurado**. Todo push no GitHub
precisa de um clique manual em **Deploy** no EasyPanel pra entrar em produção. Sempre confirme
com o usuário se ele já deployou antes de assumir que uma correção está ativa.

**Importante sobre `ADMIN_NUMBERS`**: tem default vazio no código — se a env var não estiver
configurada, o app **sobe normalmente sem erro nenhum**, só que sem filtrar ninguém (silencioso).
Sempre confirme visualmente (print da aba Environment) que o valor está lá antes de considerar
resolvido, `/healthz` OK não é suficiente.

## Estrutura da tabela Supabase (`PI_AGO_26`)

| Coluna | Tipo | Observação |
|---|---|---|
| `ID` | int8 | PK, **Is Identity precisa estar marcado** — sem isso todo INSERT falha silenciosamente (foi a causa raiz do bug original do n8n) |
| `DATA1` | text | `dd/mm/aaaa`, data da primeira entrada desse número |
| `GRUPO DA CAMPANHA` | text | Nome do grupo em que entrou (informativo, não usado pra filtro) |
| `LEAD NÚMERO` | int8 | Contador líquido de entradas/saídas |
| `LEAD ÚNICO` | int8 | 0 ou 1 — 1 = ainda está em algum grupo. `count_unique_leads()` conta `WHERE LEAD ÚNICO=1`, é a fonte de verdade do total de leads |
| `NÚMERO` | int8 | Telefone com DDI, sem `+` |

Estado em 20/07/2026: **1973 linhas, 1848 com `LEAD ÚNICO=1`** (crescendo organicamente,
sempre reconsultar em vez de confiar num número fixo aqui).

## Estrutura da planilha Google Sheets (aba `LEAD TOTAL`)

```
A: DATA2   B: ENTRADAS   C: SAÍDAS   D: RELAÇÃO (E/S)
F: TOTAL GRUPOS CHEIOS   G: TOTAL LEADS
I: DATA    J: LEADS NO DIA
L: QTD. de ADMs
```

Linha 2 é fixa (nosso código sempre escreve `TOTAL GRUPOS CHEIOS`/`TOTAL LEADS` ali via
`update_summary_row`). Linha 3: `F3="TOTAL LIMPO"`, `G3` tem a fórmula `=G2-L2` (subtrai
`QTD. de ADMs` do bruto — **essa fórmula é imprecisa**, é uma aproximação estática antiga, não
confie nela pra número exato; o número confiável é `LEADS NO DIA`, que vem direto do Supabase
deduplicado).

**⚠️ Problema recorrente não resolvido**: alguma coisa (suspeita: resquício do n8n, não
100% confirmado) ocasionalmente apaga/embaralha linhas da tabela `DATA2` e desalinha o bloco de
totais (`TOTAL LIMPO` passa a referenciar células erradas). Já aconteceu 3+ vezes nesta sessão.
Quando acontecer: reler o range `A1:L20` da planilha, reconstruir manualmente em ordem
cronológica sem buracos, e realinhar a fórmula `G3=G2-L2` e `L2` (QTD de ADMs). Usuário decidiu
não investigar a causa raiz por enquanto (seria: Google Sheets → Arquivo → Histórico de versões,
ver quem edita essa área).

## n8n — situação

Existia uma automação n8n paralela (mesma campanha) que o usuário manteve ativa durante a
migração "pra não perder dado". Ela tinha (pelo menos) dois problemas que já causaram conflito:

1. Um node `HTTP Request2` chamava `/sendapi/releases/{id}/analytics` a cada 15 min e
   sobrescrevia `TOTAL GRUPOS CHEIOS`/`TOTAL LEADS` com fórmula antiga (inflada). **Usuário já
   desativou esse node.**
2. Algo (não identificado com certeza) ainda mexe na tabela `DATA2` às vezes — ver seção acima.

**Reconciliação de dados já foi feita** (comparando histórico exportado do SendFlow vs Supabase)
e **nenhuma duplicação de leads** foi encontrada — os dados individuais de lead estão limpos.
O n8n ainda não foi desligado por completo (decisão do usuário, não urgente).

## Decisões de design importantes (pra não repetir debate)

- **Filtro de admin é por número de telefone, não por nome de grupo.** A campanha rotaciona
  automaticamente pro próximo grupo quando o atual enche (`#1` → `#2` → `#3`...), então um filtro
  fixo por nome descartaria leads reais. Admins são identificados por aparecerem em
  dezenas/centenas de grupos distintos no histórico (script no `NOVO-LANCAMENTO.md`).
- **`TOTAL LEADS` (bruto) = `participantsAmount` do payload real do SendFlow**, não um cálculo
  nosso — bate com o design original do n8n (confirmado comparando o JSON do workflow deles).
- **`LEADS NO DIA` = número limpo do Supabase**, diferente do n8n original que também usava
  bruto ali — decisão deliberada, é o número que a equipe deveria realmente confiar.
- **Sem polling ativo na API do SendFlow** — o endpoint `/analytics` dá 403 do nosso servidor
  (funciona só de dentro do n8n, provavelmente bloqueio por IP). Tudo que precisamos vem por
  push (webhook), nunca puxamos ativamente.
- **900 leads históricos + reconciliações posteriores já foram inseridos** no Supabase a partir
  de exports de CSV do SendFlow, filtrando só o grupo real e deduplicando por número.

## O que falta fazer

1. Confirmar que o deploy mais recente (incremento de `ENTRADAS`/`SAÍDAS` em tempo real, commit
   `b7973cf` ou mais novo — checar `git log` pra ver o HEAD atual) está em produção.
2. Limpar env vars não usadas no EasyPanel (lista na seção de env vars acima).
3. Revogar/trocar qualquer token que tenha sido colado em prints durante sessões anteriores
   (GitHub PAT, etc. — checar `github.com/settings/tokens`).
4. Decidir se/quando desligar o n8n de vez.
5. Considerar resolver o problema recorrente da tabela `DATA2` de vez (ver seção acima) em vez
   de só remendar toda vez que acontece.
6. Refazer a análise de números de admin periodicamente (pessoal novo pode aparecer).

## Prompt para continuar em outra sessão

Cole isto na próxima conversa:

---

Estou continuando o projeto de automação de captação de leads (SendFlow → Supabase → Google
Sheets) da Aprova Sim. Lê o arquivo
`C:\Users\trafe\Documents\sendflow-leads-service\HANDOFF.md` inteiro primeiro — tem a
arquitetura atual, decisões de design, e o que falta fazer. Se for configurar um lançamento
novo (não o PI-AGO-26 atual), lê também o `NOVO-LANCAMENTO.md` no mesmo diretório.

Depois de ler, me pergunta o que eu quero fazer primeiro — não presuma prioridade, pode ter
mudado desde que esse handoff foi escrito. Antes de qualquer deploy ou escrita em produção
(Supabase ou Sheets), confirma comigo.

---

## Histórico detalhado (contexto de como chegamos aqui, não essencial pro dia a dia)

Bugs originais no n8n: URL errada num HTTP Request, campo faltando num Create Row, matchingColumns
vazio, coluna `ID` sem auto-incremento (causa raiz de "nada gravava"), offset de admin errado, e
a fórmula de total não deduplicava. Migração pra Python decidida pelo usuário depois desse
diagnóstico. Ao longo da migração: backfill de 900 leads históricos via CSV filtrado por grupo
real, deploy no EasyPanel (com trocas de porta 80→8000), remoção de polling redundante, dois
ciclos de reconciliação de dados contra exports do SendFlow, descoberta e correção de um bug de
contaminação por grupo (webhook processava qualquer grupo, não só o real — corrigido primeiro
por nome de grupo, depois definitivamente por número de admin depois de entender que a campanha
rotaciona de grupo automaticamente), e implementação de contagem em tempo real de
entradas/saídas na planilha. Detalhes de cada etapa (incluindo números exatos e comandos
usados) estão no histórico do git (`git log`) e nas mensagens da sessão em que foram feitas, se
precisar consultar algo bem específico.
