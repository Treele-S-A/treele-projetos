# Colocar no ar com a Vercel

A TREELE decidiu centralizar os sistemas da empresa na Vercel, cada um num
subdomínio de `treele.com.br`. Este é `projetos.treele.com.br`.

Leva uns 30 minutos, quase tudo espera de build. Sem servidor para administrar.

> Todas as senhas e chaves ficam com vocês. Nada neste roteiro exige que alguém
> de fora tenha credencial da TREELE — e nenhuma delas vai para o chat.

---

## Como fica montado

```
 Navegador
    │
    ├──── https://projetos.treele.com.br ─────┐
    │                                         │
    │                              Vercel (dois serviços)
    │                              interface Vite + API FastAPI
    │                                         │
    │                                         └──── Postgres (Supabase, schema treele)
    │
    └──── PUT/GET direto por URL assinada ────────── armazenamento dos arquivos
                                                     (Cloudflare R2 ou Supabase Storage)
```

O sistema roda na Vercel como dois serviços ([`vercel.json`](../vercel.json)):
`frontend` publica a interface Vite em `/`, e `api` publica o FastAPI em `/api`.
As rotas da API são acessadas pelo navegador no mesmo domínio. Não há chamada
servidor-a-servidor entre os serviços, portanto não há binding interno. Os
arquivos de projeto vão do navegador direto para o armazenamento.

## O que vai custar

| | Por mês |
|---|---|
| Vercel Pro — **dividido entre todos os sistemas** da TREELE | US$ 20 por pessoa que publica |
| Supabase Pro — já contratado, **dividido entre todos os sistemas** | US$ 25 |
| Armazenamento dos arquivos | ver o passo 2 |

O plano gratuito da Vercel **não serve**: pela regra de uso da própria Vercel,
ele é só para uso pessoal, sem fins comerciais, e um sistema da construtora é
uso comercial.

---

## 1. Código no GitHub

O repositório está na organização `Treele-S-A` como `treele-projetos`. A
integração com a Vercel já cria deployments quando há commits; para publicar,
a conta/equipe Vercel conectada precisa ter acesso à organização e ao autor do
commit, conforme o plano e as regras da equipe. A configuração do repositório
define dois serviços e suas rotas; as credenciais continuam no painel da
Vercel, nunca no GitHub.
## 2. Armazenamento dos arquivos

Duas opções, e o sistema funciona igual nas duas:

- **Cloudflare R2** — o bucket e a chave já foram criados. Ver
  [render.md](render.md), passos 2.1 e 2.2.
- **Supabase Storage** — **a escolhida.** Dispensa o Cloudflare e fica no
  mesmo projeto do banco. Testado em 30/09/2026 com envio e download direto
  do navegador pelas URLs assinadas do sistema: funciona sem configurar nada.

No Supabase Storage:

1. *Storage → New bucket* → nome `treele-projetos`, **Public desligado**.
2. *Project Settings → Storage* → seção *S3 Connection*: anote o **endpoint**
   (`https://<projeto>.storage.supabase.co/storage/v1/s3`) e a **região**.
3. Na mesma página, *S3 Access Keys → New access key*: anote **Access Key ID**
   e **Secret Access Key** (o secret só aparece uma vez).

Nomes de arquivo com acento ou espaço não são problema: o sistema guarda cada
arquivo com um nome só de letras sem acento, números, `.`, `_` e `-` (o
Supabase recusa o resto), e devolve o nome original no download.

## 3. Banco: a string do Supabase

No Supabase: botão **Connect**, no topo do painel → string do **Transaction
pooler** (porta `6543`). Troque `[YOUR-PASSWORD]` pela senha do banco.

**Veja também a região do projeto** (*Project Settings → General → Region*).
O sistema faz várias consultas ao banco em cada acesso; se a função estiver
longe dele, cada consulta paga a viagem. O [`vercel.json`](../vercel.json) está
com `"regions": ["gru1"]` — São Paulo. Se o Supabase estiver em outra região,
avise antes do deploy para ajustar.

## 4. Gerar a chave de sessão e a senha do admin

A Vercel não gera valores sozinha, como o Render fazia. No seu computador:

```bash
python -c "import secrets; print('SECRET_KEY =', secrets.token_urlsafe(48)); print('ADMIN_SENHA =', secrets.token_urlsafe(12))"
```

Guarde os dois num gerenciador de senhas. A `SECRET_KEY` assina as sessões e
os links de download; se ela vazar, qualquer um forja um acesso.

## 5. Criar o projeto na Vercel

No painel da Vercel, no time da TREELE (plano Pro): **Add New → Project →
Import** o repositório `treele-projetos`.

- **Framework Preset:** FastAPI (a Vercel detecta sozinha).
- **Root Directory:** deixe **vazio** — a raiz do repositório. Com `backend/`
  a Vercel não enxerga a pasta da interface e o build falha.
- **Build and Output Settings:** não mexa — o `vercel.json` já define.

### Variáveis de ambiente

Em **Environment Variables**, cadastre as abaixo. **Marque só o ambiente
Production** em cada uma.

> Por que só Production: a Vercel cria uma prévia a cada envio para qualquer
> branch. Com as variáveis valendo também para as prévias, uma prévia com
> migração nova **mudaria o banco de produção** antes de alguém aprovar. Sem
> as variáveis, a prévia simplesmente não sobe — que é o comportamento certo.

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a string do passo 3 |
| `SECRET_KEY` | a do passo 4 |
| `ADMIN_EMAIL` | o e-mail de quem administra (o seu) |
| `ADMIN_SENHA` | a do passo 4 |
| `S3_ENDPOINT` | endpoint do passo 2 |
| `S3_REGION` | região do passo 2 (`sa-east-1` no Supabase de São Paulo; `auto` no R2) |
| `S3_ACCESS_KEY` | Access Key ID do passo 2 |
| `S3_SECRET_KEY` | Secret Access Key do passo 2 |

Não precisa cadastrar `API_PREFIX`, `DB_SCHEMA`, `AMBIENTE` nem
`STORAGE_BACKEND`: o entrypoint [`backend/vercel.py`](../backend/vercel.py)
define os padrões desta implantação — de propósito, porque esquecer `DB_SCHEMA`
não daria erro nenhum, só jogaria as tabelas no `public` do Supabase que os
outros sistemas também usam.
Clique em **Deploy**. O build leva uns 2 minutos.

## 6. Conferir

### Login Microsoft Entra ID do Projetos

O Projetos usa autenticação própria no FastAPI e apenas o banco Postgres do
Supabase. O botão Microsoft não utiliza Supabase Auth. Ele aceita somente
contas do locatário Microsoft da Treele com e-mail `@treele.com.br`. No
primeiro acesso, cria o usuário ativo sem privilégios de administrador e sem
vínculo com obras. Um administrador deve atribuir as obras; contas já
desativadas continuam bloqueadas.

Crie um **registro de aplicativo separado** no Microsoft Entra, do tipo
**somente este diretório organizacional**. Em **Authentication**, configure a
plataforma **Web** com esta URI de retorno:

`https://projetos.treele.com.br/api/auth/microsoft/callback`

Crie um client secret e copie o campo **Value**, nunca o Secret ID. Configure
estas variáveis **somente no serviço da API em Production** na Vercel:

| Variável | Valor |
|---|---|
| `ENTRA_TENANT_ID` | Directory (tenant) ID do aplicativo |
| `ENTRA_CLIENT_ID` | Application (client) ID |
| `ENTRA_CLIENT_SECRET` | Value do client secret, oculto e nunca no Git |
| `SITE_URL` | `https://projetos.treele.com.br` |

Depois de configurar, é necessário um novo deploy para o backend receber as
variáveis. O endpoint `/api/auth/microsoft/status` informa se as três
credenciais estão presentes, sem expor seus valores. Para desenvolvimento
local, registre também a URI Web
`http://localhost:8000/auth/microsoft/callback` e defina as mesmas variáveis
apenas no `.env` local do backend. O cookie que protege o login é do host da
API, então o início e a volta precisam usar o mesmo nome: crie
`frontend/.env.development.local` (fora do Git) com
`VITE_API=http://localhost:8000` e abra a interface em
`http://localhost:5173`, que é o primeiro endereço de `CORS_ORIGINS` e para
onde a volta da Microsoft leva.

O login por e-mail e senha existente continua disponível. A autorização por
obra continua no banco próprio, após o Entra confirmar a identidade.

### Conferir implantação

Abra `https://<nome-do-projeto>.vercel.app/api/saude`. Tem que aparecer:

```json
{"ok": true, "ambiente": "producao", "storage": "s3"}
```

Se aparecer erro, a aba **Logs** do projeto diz qual — clique na linha
vermelha para ver a mensagem inteira. Os mais prováveis:

| O que aparece | O que é |
|---|---|
| `Configuração de produção incompleta` | a própria mensagem lista cada variável que falta ou está errada — corrija todas e faça **Redeploy** |
| erro de conexão com o banco | `DATABASE_URL` com a senha errada |
| `aviso: não foi possível confirmar o bucket` | normal com chave restrita ao bucket; só é problema se o envio falhar |
| deploy **Blocked**, "commit author email is not a valid email" | o e-mail dos commits não está ligado à conta do GitHub. Use o endereço interno do GitHub: `git config user.email "<id>+<usuário>@users.noreply.github.com"` e envie um commit novo |

Armadilhas que já aconteceram nesta implantação:

- **Variável nova ou alterada só vale no deploy seguinte.** Depois de mexer em
  qualquer uma: *Deployments → ⋯ do deploy do topo → Redeploy*.
- **Ao editar, o campo Value aparece vazio.** Variável do tipo *Secret* não é
  mostrada de volta. Cole o valor de novo ao editar.
- **Tirar o Preview, não o Production.** Com só *Preview* marcado, a variável
  some da produção.
- **Cada valor no seu lugar.** `DATABASE_URL` começa com `postgresql://`;
  `S3_ENDPOINT` começa com `https://` — as duas linhas ficam vizinhas no
  arquivo de segredos e é fácil trocar.

## 7. Liberar o envio direto do navegador (CORS)

O navegador envia os arquivos direto para o armazenamento, num endereço
diferente do sistema, e só consegue se o armazenamento liberar o endereço do
sistema.

- **Supabase Storage:** nada a fazer — ele já libera qualquer origem. Não é
  brecha: sem uma URL assinada pelo sistema, válida por uma hora e para um
  único arquivo, o Supabase recusa o envio e o download.
- **R2:** bucket → *Settings → CORS Policy*, o mesmo JSON do
  [render.md](render.md), passo 4, com o endereço `.vercel.app` — e, depois do
  passo 9, também `https://projetos.treele.com.br`.

## 8. Primeiro acesso

Entre com `ADMIN_EMAIL` e `ADMIN_SENHA` e **troque a senha** em seguida. Depois:

1. Cadastre as obras (código, nome, responsável).
2. Envie o logo de cada uma em *Configurações da obra* — os arquivos já
   escolhidos estão em `Downloads\Logos das obras para o sistema`.
3. Cadastre as pessoas, cada uma com seu papel ([permissoes.md](permissoes.md)).
4. Envie um arquivo de teste e baixe de volta: é o que prova que os passos 2 e 7
   ficaram certos.

## 9. O subdomínio `projetos.treele.com.br`

No projeto da Vercel: *Settings → Domains → Add* → `projetos.treele.com.br`. A
Vercel mostra um registro **CNAME**; cadastre-o no DNS de `treele.com.br`
(quem cuida do domínio da TREELE). Em minutos o endereço passa a funcionar, com
HTTPS. Se estiver usando R2, acrescente o novo endereço no CORS do passo 7.

---

## Backup

**O banco** está no Supabase Pro: backup diário, guardado por 7 dias. Confirme
em *Database → Backups*.

**Os arquivos** não entram nesse backup — nem no R2, nem no Supabase Storage;
arquivo apagado não volta. O risco real é apagarem por engano, porque o sistema
nunca substitui bytes de revisão liberada. Durante a transição, o Drive continua
sendo a segunda cópia: não desligue o Mobuss antes de o sistema ter alguns meses
de uso.

## Limites que vale conhecer

- **Primeiro acesso depois de um tempo parado** leva alguns segundos: a função
  liga, confere o banco e sobe. Os seguintes são imediatos.
- **Várias instâncias sobem ao mesmo tempo** em pico de acesso. A preparação do
  banco é travada no próprio Postgres: uma prepara, as outras esperam. Testado
  com dez subindo juntas pelo mesmo tipo de pooler do Supabase.
- **A Fase 3** (descrição automática do que mudou entre revisões) leva minutos
  por comparação e não cabe numa função. Quando chegarmos nela, esse trabalho
  roda num serviço à parte, acionado pelo sistema.

O caminho alternativo, sem a Vercel, continua documentado: [render.md](render.md)
(Render) e [hospedagem.md](hospedagem.md) (servidor próprio). A mesma imagem
Docker ([`Dockerfile`](../Dockerfile)) serve aos dois.
