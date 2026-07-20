# Guia: configurar essa automação pra uma captação nova

Esse serviço (`contagem-leads` no EasyPanel) é genérico — a mesma imagem/código serve
qualquer lançamento, só trocando dados de configuração. Não precisa mexer em código nenhuma vez.

## Sobre VIP e lançamentos simultâneos

- **VIP é tratado como se fosse "mais um lançamento"**: é uma campanha separada dentro do
  SendFlow, referente ao mesmo lançamento, mas configurada como uma instância independente desse
  serviço (app próprio no EasyPanel, próprio Sendhook/webhook, própria tabela no Supabase — ex:
  `PI_AGO_26_VIP`). A diferença é que ele escreve na **mesma planilha** do lançamento normal,
  só que numa **aba diferente** — isso já é suportado só trocando `GOOGLE_SHEET_NAME` (mantém o
  mesmo `GOOGLE_SHEET_ID` do lançamento principal, mas aponta pro nome da aba VIP).
- **Pode ter mais de um lançamento rodando no mesmo mês** (captação normal + VIP de um
  lançamento, e possivelmente outro lançamento inteiro em paralelo). Cada combinação
  campanha×lançamento ativa ao mesmo tempo precisa do seu próprio app no EasyPanel (ver Passo 4).
  Nenhuma mudança de código é necessária — é só repetir esse guia pra cada um.

## Checklist do que você precisa ter em mãos

Antes de começar, tenha isso preparado:

1. **Nome da tabela no Supabase** que vai guardar os leads desse lançamento (ex: `PI_SET_26`).
2. **ID da planilha do Google Sheets** de captação desse lançamento (da URL:
   `docs.google.com/spreadsheets/d/`**`ESSE-ID-AQUI`**`/edit`).
3. **Nome da aba** dentro dessa planilha que tem a tabela de totais (geralmente `LEAD TOTAL`).
4. **Nome exato do grupo real de captação** no SendFlow (ex: `Projeto Tal #1`) — só usado pra
   saber o que perguntar, o filtro de verdade é por número de admin (item 6).
5. **ID da campanha no SendFlow** (da URL do painel, `/campaigns/`**`ESSE-ID`**`/overview`).
6. **Lista de números de admin/staff** — ver seção própria abaixo, precisa de um export de
   histórico de atividade do SendFlow pra descobrir.

## Passo 1 — Preparar a tabela no Supabase

1. Cria uma tabela nova no Supabase com esse nome exato de colunas (bate com o que o código
   espera, não pode ter diferença de acento/maiúscula):
   - `ID` — int8, **Primary Key, Is Identity marcado** (auto-incremento — se esquecer isso,
     todo INSERT falha silenciosamente, foi o bug original que começou esse projeto todo)
   - `DATA1` — text (data no formato `dd/mm/aaaa`)
   - `GRUPO DA CAMPANHA` — text
   - `LEAD NÚMERO` — int8
   - `LEAD ÚNICO` — int8 (0 ou 1)
   - `NÚMERO` — int8 (número de telefone com DDI, sem o `+` nem aspas)
2. Confirma que a `SUPABASE_SERVICE_KEY`/`SUPABASE_URL` que já estão configuradas continuam
   valendo (é o mesmo projeto Supabase pra todos os lançamentos, só muda o nome da tabela).

## Passo 2 — Preparar a planilha do Google Sheets

Duplica uma planilha de um lançamento anterior (mantém a estrutura) ou cria os cabeçalhos exatos
na aba de totais (linha 1):

```
A: DATA2          B: ENTRADAS   C: SAÍDAS   D: RELAÇÃO (E/S)
F: TOTAL GRUPOS CHEIOS   G: TOTAL LEADS
I: DATA           J: LEADS NO DIA
L: QTD. de ADMs
```

Na linha 2:
- `L2` = número fixo de admins × grupos (pergunte ou calcule, ver seção de admins abaixo)
- `F3` = texto `TOTAL LIMPO`, `G3` = fórmula `=G2-L2`

Compartilha a planilha com a service account (`sendflow-leads-bot@n8n-trigrrer.iam.gserviceaccount.com`)
como **Editor** — é a mesma conta de serviço pra todos os lançamentos.

## Passo 3 — Identificar os números de admin/staff

Isso muda a cada lançamento (equipe pode variar). Exporte do SendFlow o histórico de atividade
completo da campanha nova (painel → Atividades → Exportar) e rode:

```python
import csv
from collections import defaultdict

grupos_por_numero = defaultdict(set)
with open("historico.csv", encoding="utf-8-sig") as f:
    reader = csv.reader(f, delimiter=";")
    next(reader)
    for r in reader:
        numero, grupo = r[1].lstrip("'"), r[2]
        grupos_por_numero[numero].add(grupo)

for numero, grupos in sorted(grupos_por_numero.items(), key=lambda x: -len(x[1]))[:30]:
    print(numero, len(grupos))
```

Números de admin aparecem em **dezenas/centenas de grupos distintos**; leads reais só em 1
(o grupo que estava ativo quando entraram). Normalmente tem um corte bem claro entre os dois
grupos (ex: 18 números em 66+ grupos, depois cai pra no máximo 4). Os que estão acima do corte
viram a lista de `ADMIN_NUMBERS`.

**Atenção**: espere ter volume real de dados antes de fazer essa análise (nos primeiros dias,
com poucos eventos, o corte estatístico pode não ficar claro ainda).

## Passo 4 — Criar (ou reaproveitar) o serviço no EasyPanel

**Só precisa criar um app novo se esse lançamento vai rodar AO MESMO TEMPO que outro já ativo**
(cada um precisa da própria URL de webhook). Se o lançamento anterior já encerrou, reaproveita o
mesmo app: só troca as env vars do Passo 3/anteriores e clica em Deploy — pula pro final desse
passo.

Pra criar um app novo:

1. No EasyPanel, **+ Service → App** → aba **Github** → Owner `trafego2-create`, Repository
   `sendflow-leads-service`, Branch `main`, Build Path `/` (mesmo repositório de sempre, ele é
   genérico).
2. Aba **Domains** → confirma que a porta mapeada é **8000** (não 80 — já erramos isso antes).
3. Aba **Environment** → cole isso, preenchendo os `<<placeholders>>`:

```
# Supabase (URL e KEY são as mesmas de sempre, só troca a TABLE)
SUPABASE_URL=https://bjfapsvlhojiouarbzap.supabase.co
SUPABASE_SERVICE_KEY=<<mesma de sempre, pegar do .env local ou de outro lançamento>>
SUPABASE_TABLE=<<nome da tabela nova, ex: PI_SET_26>>

# Google Sheets (service account é sempre a mesma, JSON completo em uma linha só)
GOOGLE_SERVICE_ACCOUNT_JSON=<<mesmo JSON de sempre>>
GOOGLE_SHEET_ID=<<ID da planilha nova>>
GOOGLE_SHEET_NAME=LEAD TOTAL

# Admins dessa campanha (ver Passo 3) — sem espaço entre os números, separado por vírgula
ADMIN_NUMBERS=<<lista de números>>

# Scheduler
TIMEZONE=America/Sao_Paulo

# Webhook
WEBHOOK_PATH=/webhook/<<nome curto do lançamento, ex: pi-set-26>>
PORT=8000
```

4. Clica em **Deploy**.
5. Confirma que subiu: `https://<<dominio-gerado>>/healthz` deve responder `{"status":"ok"}`.

## Passo 5 — Configurar o Sendhook no SendFlow

1. No SendFlow → **Sendhooks → + Adicionar**
2. Nome: `Captação [nome do lançamento]`
3. Link: `https://<<dominio-do-easypanel>>/webhook/<<WEBHOOK_PATH configurado>>`
4. Eventos: marcar **Membro adicionado**, **Membro removido**, **Métricas da campanha**
5. Próxima → selecionar a campanha certa → Próxima → **Enviar teste**
6. Confirma no Supabase que apareceu uma linha de teste, e nos Logs do EasyPanel que não deu erro

## Passo 6 — Validar

- Deixe rodar um dia real e confira: `ENTRADAS`/`SAÍDAS` da tabela `DATA2` batendo com atividade
  real, `TOTAL LEADS`/`LEADS NO DIA` atualizando nos horários de push do SendFlow (geralmente
  7h/12h/17h).
- Depois de alguns dias com volume, refaça a análise de admins (Passo 3) pra confirmar que a
  lista inicial estava certa — pode aparecer gente nova circulando muito que precisa ser
  adicionada.

---

## Prompt pronto pra colar numa sessão nova comigo

```
Preciso configurar a automação de captação de leads (SendFlow → Supabase → Google Sheets) pra
um lançamento novo. O projeto já existe e é genérico — código em
C:\Users\trafe\Documents\sendflow-leads-service, repositório
github.com/trafego2-create/sendflow-leads-service, rodando no EasyPanel (projeto "typebot").

Lê o arquivo NOVO-LANCAMENTO.md inteiro nesse diretório primeiro — tem o passo a passo completo.
Lê também o HANDOFF.md pra contexto histórico do projeto (bugs já corrigidos, decisões de
design, por que as coisas são do jeito que são).

Dados desse lançamento novo:
- É captação normal ou VIP? <<preencher>> (se VIP, usa o mesmo GOOGLE_SHEET_ID do lançamento
  normal correspondente, só muda a aba/GOOGLE_SHEET_NAME e a tabela do Supabase)
- Nome/tabela Supabase: <<preencher>>
- ID da planilha Google Sheets: <<preencher>>
- Nome da aba dentro da planilha: <<preencher, ex: "LEAD TOTAL" ou a aba VIP>>
- Nome do grupo real de captação no SendFlow: <<preencher>>
- ID da campanha no SendFlow: <<preencher>>
- Vai rodar ao mesmo tempo que outro lançamento/campanha já ativo? <<sim/não>>
- CSV de histórico de atividade (pra identificar admins), se já tiver: <<caminho ou "ainda não
  tenho, preciso exportar primeiro">>

Me guia pelos passos, confirmando comigo antes de qualquer deploy ou escrita em produção.
```
