# Contexto para IA — Portal de Projetos (controle de revisões)

Documentos: **`README.md`** (rodar local, fases), `docs/roteiro.md` (fases seguintes), `docs/hospedagem.md`,
`docs/vercel.md`, `docs/render.md`, `docs/permissoes.md`, `docs/nomenclatura.md`, `docs/modelo3d.md`,
`docs/chat.md`, `docs/notificacoes.md`, `docs/backup.md`. Mapa de todos os sistemas:
`C:\GitHub\Desenvolvimento\MAPA_SISTEMAS.md`.

## Onde paramos

- **28/10/2026:** no ar. Últimas entregas (até 27/10/2026): conflitos entre disciplinas com filtro e busca, pavimentos
  "ocultar todos", BCF, chat do acervo com os modelos IFC e login Microsoft.
- **Próximo passo:** seguir `docs/roteiro.md`.

## O que é
Gestão de revisões de projetos de engenharia e arquitetura: nomenclatura padronizada, catálogo por
obra/disciplina/fase/formato, status de liberação, trilha de auditoria, visualizador 3D (IFC, BCF, conflitos) e
login Microsoft Entra ID.

## Onde está
- Produção: **https://projetos.treele.com.br** (Vercel `treele-projetos`, time `treele2`; ver `docs/vercel.md` e
  `docs/render.md` para a parte do servidor). GitHub `Treele-S-A/treele-projetos`, branch `main`.
- Stack: API **FastAPI** (Python 3.12, `backend/`) + interface **Vite** (`frontend/`). Local: SQLite em
  `backend/data/`. Também há `Dockerfile`, `docker-compose.yml`, `render.yaml`, `index.py` (entrada na Vercel).
- Backup: `.github/workflows/backup.yml`. Variáveis em `.env.example` (`SECRET_KEY`, `ADMIN_EMAIL`,
  `STORAGE_BACKEND`, `BASE_URL`, `CORS_ORIGINS`…). Nunca commitar `.env`/`.env.local`.

## Mapa do código
| Pasta | Conteúdo |
|---|---|
| `backend/` | API (app.main), modelos, scripts (`dados_demo.py`) |
| `frontend/` | Interface |
| `deploy/` | Apoio de publicação |
| `docs/` | Documentação por tema |

## Histórico

Uma linha por trabalho, a mais recente no fim: `AAAA-MM-DD · pessoa · IA usada · o que mudou · commit`.

- 2026-10-28 · TI (titreele) · Claude Code · criado este `CONTEXTO_IA.md`, `CLAUDE.md` e `AGENTS.md` com as regras obrigatórias de registro · (este commit)
