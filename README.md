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

## Testes

```bash
cd backend && .venv\Scripts\python -m pytest tests -q
```

32 testes cobrindo o parser de nomenclatura, a regra de arquivo companheiro, a
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

## Antes de subir para produção

Esta lista não é opcional. Cada item é um jeito conhecido de perder dados ou
vazar acesso.

- [ ] **`SECRET_KEY` própria e secreta.** Ela assina as sessões *e* os links de
      download. Com a chave padrão, qualquer pessoa forja um link para qualquer
      arquivo. Trocá-la depois invalida sessões e links ativos — o que é seguro,
      só avise a equipe.
- [ ] **Postgres, não SQLite.** O SQLite é só para desenvolvimento.
- [ ] **Alembic no lugar do `create_all`.** Hoje o esquema é criado na
      inicialização (`app/main.py`). Isso cria tabelas novas, mas **não migra
      tabelas existentes** — a primeira alteração de coluna depois de haver dados
      em produção precisa de migração de verdade.
- [ ] **HTTPS com certificado válido** (Caddy ou nginx com Let's Encrypt).
      `BASE_URL` precisa ser o endereço público em `https://`, senão os links
      assinados apontam para o lugar errado.
- [ ] **Backup do banco e do storage.** São duas coisas distintas e as duas
      precisam de rotina: um dump do Postgres não traz os arquivos.
      Teste a restauração pelo menos uma vez.
- [ ] **`ADMIN_SENHA` trocada** depois do primeiro acesso.
- [ ] **`CORS_ORIGINS`** restrito ao endereço real do sistema.
- [ ] **Limite de tamanho** (`TAMANHO_MAX_MB`) coerente com os modelos de vocês.
