# Contexto para IA — Portal de Projetos (controle de revisões)

Documentos: **`README.md`** (rodar local, fases), `docs/roteiro.md` (fases seguintes), `docs/hospedagem.md`,
`docs/vercel.md`, `docs/render.md`, `docs/permissoes.md`, `docs/nomenclatura.md`, `docs/modelo3d.md`,
`docs/chat.md`, `docs/notificacoes.md`, `docs/backup.md`, `docs/ata-analise-critica.md`. Mapa de todos os sistemas:
`C:\GitHub\Desenvolvimento\MAPA_SISTEMAS.md`.

## Onde paramos

- **29/10/2026:** no ar a **ata de análise crítica (PRO-FL-005)**, exigida para o SIAC. Nenhuma revisão é liberada
  para obra sem o checklist da disciplina preenchido num pop-up. Com algum "N", a ata fica registrada e a revisão não é
  liberada. As atas aparecem na revisão e em "Atas de análise crítica", no menu lateral, no modelo ENG-FL-001
  ("Analisado por" fixo: Luigi Gasparin Ogliari). A obra ganhou o campo **endereço**, obrigatório ao criar obra.
  Detalhes em `docs/ata-analise-critica.md`.
- **Próximo passo:** a TREELE usar a ata nas próximas liberações e dizer se o agrupamento de itens por disciplina está
  certo. Disciplinas sem bloco na planilha (GAS, INC, CLI…) só têm os itens de representação gráfica. Depois, seguir
  `docs/roteiro.md`.
- **Pendente com a TREELE:** preencher o endereço das obras já cadastradas (Configurações da obra); confirmar se a sondagem fica com Fundação (FUN) e se os requisitos de desempenho de
  vedação (VED) ficam com Arquitetura (ARQ).

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
- 2026-10-29 · Estágio de projetos (Vinícius) · Claude Code · ata de análise crítica PRO-FL-005 obrigatória antes de liberar para obra: checklist por disciplina, lista de atas no menu e link na revisão · (este commit)
- 2026-10-29 · Estágio de projetos (Vinícius) · Claude Code · ata: caixa "Marcar todos como S" no topo do checklist, no lugar do "Restantes: S" de cada grupo · (este commit)
- 2026-10-29 · Estágio de projetos (Vinícius) · Claude Code · ata no modelo ENG-FL-001 (itens analisados, solicitação de alterações com a reprovação, analisado por) e endereço da obra, obrigatório ao criar · (este commit)
- 2026-10-29 · Estágio de projetos (Vinícius) · Claude Code · ata em PDF (Ver PDF / Baixar PDF na página da ata), gerado no servidor no modelo ENG-FL-001 com ReportLab · (este commit)
