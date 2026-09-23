# TREELE · Controle de revisões de projetos

Sistema de gestão de revisões de projetos de engenharia e arquitetura: nomenclatura
padronizada obrigatória, catálogo por obra/disciplina/fase/formato, status de
liberação e trilha de auditoria completa.

**Fase 1 (esta) está pronta e testada.** As fases seguintes — chat com IA sobre o
acervo, descrição automática do que mudou entre revisões e visualizador IFC 3D —
estão descritas em [docs/roteiro.md](docs/roteiro.md).

---

## Rodar agora (sem Docker)

Precisa de Python 3.12+ e Node 20+.

**1. API**

```bash
cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
```

```bash
cd backend && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Na primeira execução o banco (SQLite em `backend/data/`) é criado, os catálogos
são populados e o usuário administrador é criado. **A senha aparece uma única vez
no console** — anote. Para definir você mesmo, crie `backend/.env` a partir de
[`.env.example`](.env.example) e preencha `ADMIN_SENHA`.

**2. Interface**

```bash
cd frontend && npm install && npm run dev
```

Abra http://127.0.0.1:5173.

**3. Dados de demonstração (opcional)**

```bash
cd backend && .venv\Scripts\python scripts\dados_demo.py
```

Cria uma obra com 13 documentos, revisões liberadas, revisões em aberto e o
histórico de obsolescência — o suficiente para avaliar o fluxo com a equipe.

> **Nota Windows:** use `127.0.0.1`, não `localhost`. O Windows resolve `localhost`
> para IPv6 (`::1`) antes de IPv4 e o servidor escuta só em IPv4 — cada requisição
> paga ~2,3 s de espera até cair para o IPv4. A configuração do projeto já usa
> `127.0.0.1` em todos os lugares.

## Rodar com Docker (Postgres + MinIO)

> **Windows exige o WSL2 antes do Docker.** No Windows 11 Home o Docker Desktop
> só funciona com o WSL2 como motor — não existe Hyper-V nessa edição. Se o
> `docker info` reclamar de `dockerDesktopLinuxEngine`, é isso. Abra o PowerShell
> **como Administrador**, rode `wsl --install` e reinicie o computador. Depois
> abra o Docker Desktop uma vez e aceite os termos.

```bash
cp .env.example .env
```

Preencha `SECRET_KEY` no `.env` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`), depois:

```bash
docker compose up --build
```

Sistema em http://localhost:8080, console do MinIO em http://localhost:9001.

---

## Como o sistema é organizado

```
Obra → Documento → Revisão → Arquivo(s)
```

O **Documento** é a entidade estável ("Forma – Pav. Tipo"): nasce uma vez e nunca
muda de código. A **Revisão** é o que evolui (R00, R01, R02…) e carrega o status.
Os **Arquivos** são os bytes daquela revisão — em geral mais de um, porque o DWG
sobe junto com o PDF plotado e o RVT com o IFC exportado.

Separar Documento de Revisão é o que permite responder *"qual é a última versão
válida disto?"* sem depender de ninguém ter nomeado a pasta direito.

### As duas regras que fazem o trabalho

**Nomenclatura obrigatória.** O nome do arquivo é validado contra o template da
obra antes de qualquer byte subir, e os campos são *extraídos* dele. Ninguém
digita metadado, então ninguém erra o cadastro. Ver
[docs/nomenclatura.md](docs/nomenclatura.md).

**Obsolescência automática.** Publicou a R02, a R01 vira obsoleta no mesmo
instante. É o inverso da pasta de rede, onde a revisão velha continua ali
parecendo válida até alguém imprimir e executar errado.

### Duas formas de ver o acervo

**Lista** é uma tabela por documento, com filtros e busca — serve para procurar
algo específico e para exportar a lista mestra.

**Pastas** é um navegador em dois níveis — `Disciplina → Fase` — com tamanho,
data e resumo de formatos acumulados. Clicar na fase abre a pasta: todos os
documentos dali, cada um com o histórico completo de revisões e os arquivos de
cada revisão. É onde se confere o que foi entregue e se libera para obra sem
abrir documento por documento.

As pastas não existem no armazenamento: são derivadas dos metadados que o nome
do arquivo já carrega. Não há pasta para arrumar nem arquivo no lugar errado.

### Arquitetura

```
Navegador (React + TypeScript)
     │  HTTPS
  API (Python / FastAPI) ──── Postgres      catálogo, revisões, permissões, auditoria
     │
     └──────────────────── Object storage   os arquivos
            ↑ upload e download DIRETO por URL assinada
```

O arquivo **nunca** passa pela API: o navegador recebe uma URL assinada de curta
duração e fala direto com o storage. Sem isso um DWG de 800 MB ocupa um worker
inteiro no upload, e quem está na obra com 4G não baixa nada.

O armazenamento tem dois back-ends com a mesma interface — `local` (disco, para
desenvolvimento) e `s3` (MinIO auto-hospedado, S3, Cloudflare R2 ou Backblaze B2).
Trocar é uma variável de ambiente; nenhum outro arquivo muda.

No modo `s3` existem **dois endereços**, e confundi-los é a falha mais comum ao
subir em container:

| Variável | Quem usa | Valor no docker-compose |
|---|---|---|
| `S3_ENDPOINT` | o **navegador**, ao abrir a URL assinada | `http://localhost:9000` |
| `S3_ENDPOINT_INTERNO` | a **API**, pela rede do Docker | `http://minio:9000` |

A URL é assinada com o endereço público porque a assinatura SigV4 cobre o
cabeçalho `Host` — e o `Host` que chega ao MinIO é o público. Com um S3 de
verdade os dois endereços são iguais e basta preencher `S3_ENDPOINT`.

### Papéis

| Papel | Vê obsoletos | Envia | Libera para obra | Cancela | Gerencia |
|---|:--:|:--:|:--:|:--:|:--:|
| Coordenador | ✓ | ✓ | ✓ | ✓ | ✓ |
| Projetista | ✓ | ✓ | | | |
| Obra | ✓ | | | | |
| Cliente | | | | | |

Detalhes em [docs/permissoes.md](docs/permissoes.md).

---

## Migrações de esquema

O esquema é versionado com Alembic e as migrações rodam sozinhas na
inicialização. Banco criado antes disso é carimbado automaticamente com a
migração inicial, então atualizar uma instalação em uso não exige nada manual.

Para criar uma migração depois de alterar `app/models.py`:

```bash
cd backend && .venv\Scripts\python -m alembic revision --autogenerate -m "o que mudou"
```

Leia o arquivo gerado antes de commitar — o autogenerate acerta quase sempre,
mas não entende renomeação (vê como remover + criar, o que apaga dados) nem
nomeia restrições sozinho.

## Testes

```bash
cd backend && .venv\Scripts\python -m pytest tests -q
```

52 testes cobrindo o parser de nomenclatura, a regra de arquivo companheiro, a
obsolescência automática, o controle de permissões e a trilha de auditoria.

## Estrutura

```
backend/
  app/
    models.py               modelo de dados
    enums.py                status, papéis e matriz de permissões
    services/
      nomenclatura.py       template → regex, validação e extração de campos
      revisoes.py           regra de companheiro, liberação, obsolescência
      storage.py            back-ends local e S3, URLs assinadas
      auditoria.py          trilha de eventos
    api/                    rotas HTTP
  tests/
  scripts/dados_demo.py     povoa uma obra de demonstração
frontend/
  src/
    api.ts                  cliente HTTP e tipos do domínio
    estilos.css             sistema visual
    paginas/                telas
docs/
```

---

## Colocar no ar

Dois caminhos, ambos com roteiro pronto. **O escolhido pela TREELE é o
primeiro.**

### Render — sem servidor para administrar *(escolhido)*

**[docs/render.md](docs/render.md)** — GitHub, Cloudflare R2, e o
[`render.yaml`](render.yaml) monta banco e serviço sozinho a partir do
repositório. Cerca de 40 minutos, quase tudo espera de build. Sem SSH, sem
firewall para manter, sem certificado para renovar.

Custo estimado: **~US$ 13/mês (~R$ 70)**, com os arquivos no R2 — que não cobra
tráfego de saída, e saída é quase tudo o que a obra faz.

A interface e a API viajam na mesma imagem ([`Dockerfile`](Dockerfile)) e
rodam num processo só: a API sob `/api`, as telas sob `/`. Um serviço em vez de
dois, sem CORS e sem endereço de API para configurar.

### VPS próprio — mais barato, mais controle

**[docs/hospedagem.md](docs/hospedagem.md)** — contratar o servidor, apontar o
domínio, instalar, configurar o backup e testar a restauração. Cerca de uma
hora. Resumido, num Ubuntu 24.04 novo:

```bash
cd /opt/treele && sudo bash deploy/instalar-servidor.sh
```

O script instala o Docker, fecha o firewall, gera todos os segredos, sobe o
sistema com HTTPS automático (Caddy + Let's Encrypt) e agenda o backup diário.

Custo estimado: **~R$ 60/mês** num VPS em São Paulo. A diferença de preço é
pequena; a diferença está em quem administra a máquina.

## Antes de subir para produção

Esta lista não é opcional. Cada item é um jeito conhecido de perder dados ou
vazar acesso.

Os dois caminhos já resolvem quase tudo — o `render.yaml` no primeiro, o
instalador (`deploy/instalar-servidor.sh`) no segundo:

- [x] **`SECRET_KEY` própria e secreta** — gerada na criação, nunca digitada
      por ninguém. Ela assina as sessões *e* os links de download.
- [x] **Postgres, não SQLite** — gerenciado no Render; no compose de produção
      no VPS.
- [x] **Migrações de esquema** — Alembic, automático na subida.
- [x] **HTTPS com certificado válido** — pronto no Render; Caddy + Let's
      Encrypt no VPS.
- [x] **Banco e armazenamento fechados** — o banco não fica exposto e o bucket
      não é público; o acesso aos arquivos é por URL assinada de uma hora.
- [x] **Backup do banco** — do Render no primeiro caminho; diário às 02:15,
      com rotação de 14 dias, no segundo.

Sobram quatro, que dependem de você:

- [ ] **Trocar a senha do administrador** depois do primeiro acesso.
- [ ] **Liberar o CORS do bucket** — só no caminho do Render (passo 4 do
      roteiro). Sem isso o envio é bloqueado pelo navegador.
- [ ] **Cópia dos arquivos fora do fornecedor** (rclone para o OneDrive).
      Banco e arquivos são duas coisas distintas, e backup que só existe onde
      o original está não é backup.
- [ ] **Testar a restauração pelo menos uma vez.** Backup nunca restaurado é um
      arquivo grande com nome tranquilizador.
