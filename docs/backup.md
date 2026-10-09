# Backup fora do Supabase

Desde 09/10/2026. O backup diário do Supabase Pro cobre só o **banco**, por 7
dias, e fica dentro do próprio Supabase. Os **arquivos** do Storage não têm
backup nenhum lá: um arquivo apagado (por exemplo, ao excluir uma obra) não
volta. Por isso existe esta cópia, em outro fornecedor.

## O que é copiado, e para onde

Uma tarefa do GitHub Actions ([.github/workflows/backup.yml](../.github/workflows/backup.yml))
roda todo dia às 03:17 (Brasília) e grava numa biblioteca de documentos do
SharePoint da TREELE, na pasta `sistema-de-projetos/`:

| Pasta | Conteúdo | Quanto tempo |
|---|---|---|
| `arquivos/` | Espelho do bucket, com as mesmas chaves do Storage | Enquanto existir no sistema |
| `excluidos/<data_hora>/` | O que saiu do bucket ou foi substituído naquele dia | 90 dias |
| `banco/` | `pg_dump` do schema `treele`, um por dia | 90 dias |

- A cópia dos arquivos é incremental: só sobe o que é novo ou mudou.
- Nada se perde por espelhamento: arquivo que sai do sistema vai para
  `excluidos/`, não é apagado do backup.
- Se o bucket voltar vazio (chave errada, problema no Supabase), a tarefa para
  sem mexer no backup.
- Depois dos 90 dias, o que a limpeza apaga ainda passa pela lixeira do
  SharePoint.
- Falhou, o GitHub manda e-mail para quem fez o último commit do arquivo do
  workflow. O resultado de cada rodada fica em **GitHub → Actions → Backup**,
  com um resumo do que há no SharePoint.

Custo: zero. O GitHub dá 2.000 minutos por mês em repositório privado; cada
rodada leva poucos minutos. O espaço sai da cota do SharePoint da empresa.

## Configuração (uma vez)

Feita por quem administra o Microsoft 365 da TREELE.

### 1. Site do SharePoint

O banco copiado tem e-mails e o resumo das senhas dos usuários: não pode ficar
visível para a empresa toda. Duas formas:

- Um site só para isto (ex.: **Backup Sistemas**), privado, com apenas os
  administradores como membros. É o mais isolado.
- Uma pasta num site que já existe (a escolha de 09/10/2026), com as
  permissões **restritas**: na pasta, **Gerenciar acesso** → **Parar de herdar
  permissões** (em "Avançado") e deixar só os administradores. Neste caso o
  aplicativo do passo 2 pode gravar no site inteiro, não só na pasta — o
  `Sites.Selected` libera por site.

### 2. Aplicativo no Entra ID

1. [entra.microsoft.com](https://entra.microsoft.com) → **Aplicativos** →
   **Registros de aplicativo** → **Novo registro**. Nome: `Backup sistema de
   projetos`. Tipo de conta: só esta organização. Sem URI de redirecionamento.
2. Anotar da página do aplicativo: **ID do aplicativo (cliente)** e **ID do
   diretório (locatário)**.
3. **Certificados e segredos** → **Novo segredo do cliente**, validade de 24
   meses. Copiar o **Valor** na hora (ele não aparece de novo). **Anotar na
   agenda a data de vencimento** — no dia, o backup para.
4. **Permissões de API** → **Adicionar** → **Microsoft Graph** →
   **Permissões de aplicativo** → `Sites.Selected` → **Conceder consentimento
   de administrador**.

`Sites.Selected` sozinha não dá acesso a nada. O passo seguinte libera
**apenas** o site do backup — o aplicativo não enxerga o resto do SharePoint.

### 3. Liberar o site para o aplicativo

No [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer),
entrando com a conta de administrador (ele pede consentimento para
`Sites.FullControl.All` na primeira vez):

```
GET https://graph.microsoft.com/v1.0/sites/<empresa>.sharepoint.com:/sites/<nome-do-site>
```

O `id` da resposta é o do site. Com ele:

```
POST https://graph.microsoft.com/v1.0/sites/<id-do-site>/permissions

{
  "roles": ["write"],
  "grantedToIdentities": [{
    "application": { "id": "<ID do aplicativo>", "displayName": "Backup sistema de projetos" }
  }]
}
```

E o ID da biblioteca de documentos:

```
GET https://graph.microsoft.com/v1.0/sites/<id-do-site>/drive
```

O `id` desta resposta é o `MS_DRIVE_ID`.

### 4. Segredos no GitHub

Repositório → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**, um por linha:

| Segredo | De onde vem |
|---|---|
| `DATABASE_URL` | O mesmo da Vercel |
| `S3_ENDPOINT`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Os mesmos da Vercel |
| `MS_TENANT_ID` | ID do diretório (locatário), passo 2 |
| `MS_CLIENT_ID` | ID do aplicativo (cliente), passo 2 |
| `MS_CLIENT_SECRET` | Valor do segredo, passo 2 |
| `MS_DRIVE_ID` | ID da biblioteca, passo 3 |

Na aba **Variables** da mesma tela, a variável `BACKUP_PASTA` com o caminho da
pasta dentro da biblioteca (ex.: `TI/Backup sistema de projetos`). Sem ela, a
cópia vai para `sistema-de-projetos/` na raiz da biblioteca.

Depois, **Actions** → **Backup** → **Run workflow** para a primeira rodada.
Faltando algum segredo, a tarefa diz qual no primeiro passo.

## Restaurar

### Um arquivo excluído

Está em `excluidos/<data_hora>/` com o mesmo caminho que tinha no Storage.
Baixar pelo SharePoint e subir no Supabase Storage com o mesmo caminho, ou:

```
rclone copyto "sharepoint:sistema-de-projetos/excluidos/<data_hora>/<caminho>" "supabase:<bucket>/<caminho>"
```

O registro no banco também precisa existir — se o arquivo saiu porque a obra
foi excluída, é restauração completa (abaixo).

### Tudo (banco e arquivos)

1. **Banco**, num Postgres 17 vazio (um projeto novo do Supabase, por
   exemplo), pela conexão direta ou pelo pooler em modo sessão (porta 5432):

   ```
   pg_restore --no-owner --no-privileges -d "<url do banco novo>" treele-<data>.dump
   ```

   Cria o schema `treele` com todos os dados, inclusive a versão das
   migrações: o sistema sobe sem rodar nada de novo.

2. **Arquivos**, para o bucket novo, com as mesmas chaves:

   ```
   rclone copy "sharepoint:sistema-de-projetos/arquivos" "supabase:<bucket novo>"
   ```

3. Trocar `DATABASE_URL` e as `S3_*` na Vercel e fazer Redeploy.

As variáveis `RCLONE_CONFIG_*` no topo do workflow mostram como configurar os
dois lados do rclone.

### Teste de restauração

Feito em 09/10/2026, antes da primeira rodada: o `pg_dump` do schema `treele`
foi restaurado num Postgres 17 local e as contagens bateram com a produção
(5 obras, 45 documentos, 50 revisões, 87 arquivos, 8 usuários, migração
`b6f8d0e2a4c5`). A cópia dos arquivos foi testada para uma pasta local: 94
objetos, exclusão indo para `excluidos/` e limpeza por data.

Repetir o teste de restauração a cada seis meses, a partir do backup de
verdade no SharePoint.
