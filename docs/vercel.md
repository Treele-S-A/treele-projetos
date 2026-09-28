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
    │                              Vercel (uma função)
    │                              interface + API sob /api
    │                                         │
    │                                         └──── Postgres (Supabase, schema treele)
    │
    └──── PUT/GET direto por URL assinada ────────── armazenamento dos arquivos
                                                     (Cloudflare R2 ou Supabase Storage)
```

O sistema roda na Vercel como **uma função**: a Vercel reconhece a aplicação
FastAPI pelo `index.py` da raiz, e o build compila a interface junto
([`vercel.json`](../vercel.json)). Os arquivos de projeto nunca passam por ela —
vão do navegador direto para o armazenamento.

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

Já está: `viniciusbordini/treele-projetos`, privado. A Vercel lê de lá — cada
envio para a branch `main` vira um deploy novo, sozinho.

## 2. Armazenamento dos arquivos

Duas opções, e o sistema funciona igual nas duas:

- **Cloudflare R2** — o bucket e a chave já foram criados. Ver
  [render.md](render.md), passos 2.1 e 2.2.
- **Supabase Storage** — com o Supabase Pro contratado, dispensa o Cloudflare.
  **Antes de escolher, precisa de um teste**: o Supabase não deixa configurar
  pelo S3 a liberação de envio direto do navegador (CORS). Ver a conversa de
  28/09/2026 — o teste leva 15 minutos.

Em qualquer das duas você vai ter quatro valores: **endpoint, região, Access Key
ID e Secret Access Key**.

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
| `S3_REGION` | região do passo 2 (`auto` no R2) |
| `S3_ACCESS_KEY` | Access Key ID do passo 2 |
| `S3_SECRET_KEY` | Secret Access Key do passo 2 |

Não precisa cadastrar `API_PREFIX`, `DB_SCHEMA`, `AMBIENTE`, `STORAGE_BACKEND`
nem `ESTATICOS_DIR`: o [`index.py`](../index.py) já define os padrões desta
implantação — de propósito, porque esquecer `DB_SCHEMA` não daria erro
nenhum, só jogaria as tabelas no `public` do Supabase que os outros sistemas
também usam.

Clique em **Deploy**. O build leva uns 2 minutos.

## 6. Conferir

Abra `https://<nome-do-projeto>.vercel.app/api/saude`. Tem que aparecer:

```json
{"ok": true, "ambiente": "producao", "storage": "s3"}
```

Se aparecer erro, a aba **Logs** do deploy diz qual. Os mais prováveis:

| O que aparece | O que é |
|---|---|
| `SECRET_KEY inválida para produção` | chave curta ou esquecida — volte ao passo 4 |
| erro de conexão com o banco | `DATABASE_URL` errada, ou a senha ainda com `[YOUR-PASSWORD]` |
| `aviso: não foi possível confirmar o bucket` | normal com chave restrita ao bucket; só é problema se o envio falhar |

## 7. Liberar o envio direto do navegador (CORS)

O navegador envia os arquivos direto para o armazenamento, num endereço
diferente do sistema, e só consegue se o armazenamento liberar o endereço do
sistema. No **R2**: bucket → *Settings → CORS Policy*, o mesmo JSON do
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
HTTPS. Não esqueça de acrescentar o novo endereço no CORS do passo 7.

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
