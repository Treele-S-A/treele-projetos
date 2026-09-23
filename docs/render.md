# Colocar no ar com o Render

Roteiro para sair da máquina do Vinicius e ir para um endereço que a equipe
inteira alcança, **sem servidor para administrar**. Leva cerca de 40 minutos, e
a maior parte é espera de build.

> Todas as senhas e chaves ficam com vocês. Nada neste roteiro exige que alguém
> de fora tenha credencial da TREELE.

O caminho alternativo — VPS próprio, com SSH e manutenção por conta da casa —
continua documentado em [hospedagem.md](hospedagem.md). Ele é mais barato e dá
mais controle; este aqui é mais simples e não pede administração de servidor.

---

## Como fica montado

```
 Navegador
    │
    ├──── https://treele.onrender.com ────┐
    │                                     │
    │                          Render (um contêiner)
    │                          interface + API no mesmo processo
    │                                     │
    │                                     └──── Postgres (Supabase, já existente)
    │
    └──── PUT/GET direto por URL assinada ────── Cloudflare R2 (os arquivos)
```

São **três fornecedores de propósito**, e o banco é o único que já era de
vocês antes deste roteiro: a TREELE já usa o Supabase (plano gratuito) para
outro sistema, e sobra espaço (161 de 500 MB usados, conferido em 23/09/2026)
para o metadado deste — que é texto (nome do documento, revisão, status,
trilha de auditoria), não arquivo. Os arquivos pesados (DWG, RVT, PDF) vão
para o R2, não para o Supabase; por isso este sistema, sozinho, ocupa poucos
megabytes. O limite de 500 MB, porém, é um só para os dois sistemas.

Usa-se **só o Postgres** do Supabase, não o Auth nem o Storage dele — o login
deste sistema já está pronto e testado, e reescrevê-lo para depender de outro
serviço seria trabalho sem necessidade.

---

## O que vai custar

| | Por mês |
|---|---|
| Render — serviço web (plano Starter) | US$ 7 |
| Supabase — plano gratuito, já usado pela TREELE para outro sistema | R$ 0 |
| Cloudflare R2 — até 10 GB, sem custo de saída | US$ 0 |
| **Total adicional** | **≈ US$ 7 (~R$ 35)** |

O acervo de vocês tem poucos gigabytes e cresce de 2 a 4 GB por ano — os
modelos Revit continuam no Drive. Os 10 GB gratuitos do R2 cobrem alguns anos;
depois disso o R2 cobra por GB armazenado, e continua sem cobrar saída.

**Por que não o plano gratuito do Render para o serviço web.** Ele hiberna
depois de alguns minutos parado e leva perto de um minuto para acordar — quem
abre o sistema acha que caiu. Para avaliar por uma tarde serve; para a equipe
usar, não. (O Postgres próprio do Render nem entra mais nessa conta — ver
acima.)

Confira os preços no painel antes de confirmar: eles mudam, e a cotação do
dólar também. Vale acompanhar também o uso do Supabase (**Project Settings →
Usage**) depois que este sistema entrar em produção, para saber quando os
500 MB gratuitos vão apertar de vez — nesse dia, a saída é o plano Pro do
Supabase, não sair dele.

---

## Antes de começar

Três contas — criar é gratuito; o que se paga é o serviço no Render. O
Supabase vocês já têm.

| Conta | Para quê |
|---|---|
| **GitHub** | guardar o código; é de lá que o Render lê |
| **Render** | rodar o sistema (dá para entrar com o GitHub) |
| **Cloudflare** | guardar os arquivos no R2 |

O Cloudflare pede cartão para habilitar o R2 mesmo no uso gratuito. Dentro dos
10 GB não é cobrado.

---

## 1. Colocar o código no GitHub

Crie um repositório **privado** chamado `treele-projetos`. Sem README, sem
`.gitignore` — o repositório já tem os dois.

Depois, no `C:\dev\treele-projetos`:

```bash
git remote add origin https://github.com/SEU-USUARIO/treele-projetos.git
```

```bash
git push -u origin main
```

Nenhum segredo sobe: `.env` e `.env.producao` estão no `.gitignore` desde o
começo. Para confirmar antes de enviar:

```bash
git ls-files | grep "\.env" | grep -v "\.env\.example" ; echo "(nada acima = nenhum segredo no repositório)"
```

O `.env.example` aparece no repositório e deve mesmo: ele só lista os nomes
das variáveis, sem valor nenhum.

## 2. Criar o armazenamento no Cloudflare R2

No painel do Cloudflare, em **R2**:

**2.1 — Criar o bucket.** Nome `treele-projetos`, localização *Automatic*.
Deixe o acesso público **desligado**: quem autoriza cada download é o sistema,
por URL assinada de uma hora.

**2.2 — Criar a chave de API.** Em *R2 → API → Manage API Tokens → Create API
Token*, permissão **Object Read & Write**, restrita ao bucket `treele-projetos`.

Anote os três valores que aparecem **uma única vez**:

| Valor no painel | Variável no Render |
|---|---|
| Access Key ID | `S3_ACCESS_KEY` |
| Secret Access Key | `S3_SECRET_KEY` |
| Endpoint (`https://<id-da-conta>.r2.cloudflarestorage.com`) | `S3_ENDPOINT` |

O endpoint é o endereço **sem** o nome do bucket no fim. Se o painel mostrar
`.../treele-projetos`, tire essa parte.

> A configuração de CORS do bucket é o passo 4 — ela precisa do endereço do
> sistema, que só existe depois do passo 3.

## 2.3 — Pegar a string de conexão do Supabase

No projeto do Supabase que a TREELE já usa: botão **Connect**, no topo do
painel (ou *Project Settings → Database*). Escolha a string do **Transaction
pooler** (porta `6543`) — é a que divide melhor o limite de conexões do plano
gratuito. A do *Session pooler* também funciona; a *Direct connection*, não
use: ela pode não ser alcançável a partir do Render.

Troque `[YOUR-PASSWORD]` na string pela senha do banco. Se ninguém lembra
qual é, dá para gerar outra em *Database → Settings* — mas **confira antes se o
outro sistema usa essa senha**: o Lovable costuma falar com o Supabase por
chave de API, não pela senha do banco, mas vale a certeza antes de trocar.

Copie essa string agora, mas **não cole em lugar nenhum ainda** além do
próprio Render, no próximo passo — ela contém a senha do banco.

## 3. Criar tudo no Render

No painel: **New → Blueprint → Connect a repository** e escolha
`treele-projetos`. O Render lê o [`render.yaml`](../render.yaml) do repositório
e monta o serviço web.

Ele vai pedir os valores que o arquivo deixou em branco de propósito, porque
são segredos:

| Campo | O que pôr |
|---|---|
| `DATABASE_URL` | a string de conexão do passo 2.3, exatamente como o Supabase mostrou |
| `S3_ENDPOINT` | o endpoint do passo 2.2 |
| `S3_ACCESS_KEY` | a Access Key ID do passo 2.2 |
| `S3_SECRET_KEY` | a Secret Access Key do passo 2.2 |
| `ADMIN_EMAIL` | o e-mail de quem vai administrar (o seu) |

`SECRET_KEY` e `ADMIN_SENHA` o Render gera sozinho — não precisa inventar.

Clique em **Apply**. A primeira construção leva de 8 a 15 minutos: ela compila
a interface e instala as dependências do Python. As seguintes são mais rápidas,
por causa do cache.

Na primeira subida, o sistema cria o schema `treele` dentro do banco do
Supabase e as tabelas dele lá dentro — o `public`, onde mora o outro sistema,
não é tocado. Isso foi testado com uma tabela de mesmo nome (`usuarios`) já
existindo no `public`, e através de um pooler igual ao do Supabase, com
conexões simultâneas.

Quando terminar, o Render mostra o endereço — algo como
`https://treele.onrender.com`. **Anote.**

Se a construção falhar, a aba *Logs* diz onde. O erro mais comum é `npm ci`
sem `package-lock.json`, e o repositório já tem o arquivo.

## 4. Liberar o CORS do bucket

**Este passo não é opcional.** O envio de arquivo é o navegador falando
*direto* com o R2, num endereço diferente do sistema — sem essa liberação, o
navegador bloqueia o envio antes mesmo de tentar, e o erro na tela não explica
nada.

No bucket `treele-projetos`, em *Settings → CORS Policy → Edit*, cole:

```json
[
  {
    "AllowedOrigins": ["https://treele.onrender.com"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

Troque `https://treele.onrender.com` pelo endereço que o Render deu no passo 3.
**Sem barra no fim.** Se um dia o sistema mudar de endereço, esta lista precisa
mudar junto.

O download não passa por aqui — ele é uma navegação do navegador, não uma
chamada de JavaScript.

## 5. Primeiro acesso

A senha do administrador foi gerada pelo Render. Para ver: **serviço `treele` →
Environment → `ADMIN_SENHA` → Reveal**.

Abra o endereço, entre com o `ADMIN_EMAIL` e essa senha, e **troque a senha em
seguida**. Depois:

1. Cadastre as obras reais (código, nome, responsável).
2. Cadastre as pessoas, cada uma com seu papel — ver
   [permissoes.md](permissoes.md).
3. Envie um arquivo de teste e baixe de volta. É o que prova que os passos 2 e
   4 ficaram certos.

Se o envio falhar, o problema está no CORS (passo 4) ou na chave (passo 2.2),
nessa ordem de probabilidade.

---

## Se der errado

Os cinco tropeços prováveis, na ordem em que aparecem:

| O que você vê | O que é |
|---|---|
| A construção falha antes de subir | Erro de build. A aba *Logs* mostra a linha exata. |
| O serviço sobe e cai, dizendo `SECRET_KEY inválida para produção` | A chave não foi gerada ou ficou curta. Em *Environment*, apague `SECRET_KEY` e deixe o Render gerar outra. O sistema se recusa a rodar com chave fraca de propósito: ela assina as sessões *e* os links de download. |
| Aparece `aviso: não foi possível confirmar o bucket` no log, mas o sistema sobe | Normal no R2: a chave enxerga os objetos, não o bucket. Só é problema se o envio também falhar. |
| O envio de arquivo falha no navegador sem mensagem clara | CORS do bucket (passo 4). Confira se o endereço em `AllowedOrigins` é exatamente o do sistema, sem barra no fim. |
| O serviço sobe e cai, dizendo `DB_SCHEMA é 'treele', mas a transação está em ...` | O sistema se recusou a criar tabelas fora do schema dele — de propósito, para não tocar no banco do outro app. Confira se `DATABASE_URL` é a string do Supabase, completa. |

## Backup

**O banco** — catálogo, revisões, permissões, auditoria — mora no Supabase, no
plano gratuito. **Confira em *Database → Backups* do Supabase se existe cópia
restaurável nesse plano.** O comum no gratuito é não existir — e aí o backup do
banco passa a ser por nossa conta, porque ele é a única coisa que não se
reconstrói: os arquivos estão no R2 (e no Drive), mas qual revisão está
liberada, quem enviou e a trilha de auditoria só existem aqui.

A defesa é um `pg_dump` só do schema `treele`, periódico, guardado fora do
Supabase — por exemplo, no próprio R2. Isso **ainda não está montado**: é o
próximo item depois de o sistema subir. Enquanto não estiver, não desligue o
fluxo antigo.

Esse é o custo real de reaproveitar o Supabase gratuito em vez do Postgres
pago do Render: os US$ 6 por mês incluíam backup diário. Vale a troca, mas só
com o dump montado.

**Os arquivos** ficam no R2 e são responsabilidade de vocês. O risco real não é
corromper um arquivo — o sistema nunca substitui bytes de revisão liberada,
só acrescenta — é alguém apagar o bucket por engano. Duas defesas:

- **Durante a transição, mantenha o Drive.** Ele já é a segunda cópia. Só
  desligue quando o sistema tiver alguns meses de uso.
- **Depois, uma cópia periódica para o OneDrive** com o `rclone`, que fala S3 e
  OneDrive nativamente. É a mesma ferramenta do roteiro do VPS
  ([hospedagem.md](hospedagem.md), passo 6).

Backup nunca restaurado é um arquivo grande com nome tranquilizador. Teste uma
vez.

---

## Domínio próprio, quando quiserem

Não é necessário para começar: o endereço do Render já vem com HTTPS válido.

Quando quiserem `projetos.treele.com.br`:

1. No Render, **serviço `treele` → Settings → Custom Domains → Add**.
2. No painel de DNS do domínio da TREELE, crie o **registro CNAME** que o
   Render mostrar.
3. Atualize o `AllowedOrigins` do passo 4 para o novo endereço.

É **um** registro só, não dois. No roteiro do VPS eram dois porque o
armazenamento também precisava de nome próprio; aqui ele já mora no Cloudflare,
com endereço pronto.

---

## O que este caminho não resolve

Vale saber antes, para não virar surpresa:

- **Não há acesso ao servidor.** Scripts administrativos (como
  `scripts/excluir_obra.py`) rodam pelo *Shell* do painel do Render, disponível
  nos planos pagos.
- **O plano Starter tem 512 MB de RAM.** Sobra para a Fase 1. A Fase 3 —
  descrição automática do que mudou entre revisões, que abre IFC e PDF — vai
  pedir mais; na hora, é trocar o plano no painel, sem mexer em código.
- **Dependência de três fornecedores** (Render, Supabase, Cloudflare). Em
  compensação, dado e processamento ficam separados: se um dia trocarmos de
  hospedagem, nem o banco nem o acervo se movem.
- **O banco é dividido com outro sistema.** As tabelas deste ficam no schema
  `treele`, sem tocar nas do outro app — mas o limite de 500 MB do plano
  gratuito é um só, para os dois. Acompanhe em *Project Settings → Usage*.
- **O Supabase gratuito pausa projetos parados por uma semana.** Com dois
  sistemas usando o mesmo projeto todo dia, isso não deve acontecer; se um dia
  acontecer, é reativar no painel.
