# Contexto para IA — Portal de Projetos (controle de revisões)

Documentos: **`README.md`** (rodar local, fases), `docs/roteiro.md` (fases seguintes), `docs/hospedagem.md`,
`docs/vercel.md`, `docs/render.md`, `docs/permissoes.md`, `docs/nomenclatura.md`, `docs/modelo3d.md`,
`docs/chat.md`, `docs/notificacoes.md`, `docs/backup.md`, `docs/ata-analise-critica.md`, `docs/fornecedores.md`. Mapa de todos os sistemas:
`C:\GitHub\Desenvolvimento\MAPA_SISTEMAS.md`.

## Onde paramos

- **30/10/2026, integração para publicação:** as melhorias locais de interface, tema, perfil e seletor de obra foram mescladas aos quatro commits recentes do estágio de projetos (tipos de acesso, solicitações externas, chat e 3D). Build do frontend e suíte do backend passaram após o rebase. Próximo passo: publicar a `main` e verificar a implantação; pendente com a TREELE: homologar o visual e a edição de perfil em produção. `.env`, `.env1`, `.env.local` e a configuração local de banco/S3 não entram no Git.

- **30/10/2026, seletor de obra e carimbo:** o seletor nativo da barra lateral foi substituído por uma lista própria com destaque da obra ativa, contraste em temas claro/escuro, fechamento por clique externo/Escape e animação leve. O carimbo de liberação no tema escuro deixou de usar `mix-blend-mode:multiply` e ganhou tinta verde clara legível sobre fundo escuro. Build validado; homologar no localhost. Sem commit/publicação.

- **30/10/2026, PDFs no localhost:** preview usava PostgreSQL de produção, mas `STORAGE_BACKEND=local` com pasta temporária vazia; por isso documentos retornavam 404. Confirmado em leitura que o PDF de MIL existe no S3 de produção. API local reiniciada com `STORAGE_BACKEND=s3` e variáveis S3 já fornecidas no `vercel-producao.env`, sem copiar credenciais ao Git e mantendo `--lifespan off`. `/saude` por localhost e IP responde `storage=s3`; URL pré-assinada para o PDF retornou HTTP 206 `application/pdf`. Usuário precisa reabrir o documento a partir do sistema para obter novo link. Sem commit/publicação.

- **30/10/2026, contraste do tema escuro:** ajustadas cores de estados e fundos de cartões, campos, avisos e controles que permaneciam claros. No visualizador 3D, lista de modelos, propriedades, vistas, BCF, conflitos, menu de contexto e formulários receberam superfícies e texto legíveis. Canvas BIM/IFC e capas/logos das obras não foram alterados. Build frontend validado; falta homologação visual pelo usuário no localhost. Sem commit/publicação.

- **30/10/2026, API no acesso pela LAN:** a API estava ativa, mas o processo Vite havia herdado `VITE_API=http://127.0.0.1:8000` do ambiente do shell, prevalecendo sobre `frontend/.env.local`. Isso fazia o outro PC chamar a própria porta 8000. Vite reiniciado com `VITE_API=/api` explicitamente; o módulo servido confirma `/api` e `http://192.168.0.160:5173/api/saude` responde 200. No outro PC, recarregar sem cache. Sem commit/publicação.

- **30/10/2026, menu de Projetos:** abertura e recolhimento da barra lateral suavizados no padrão do RH, com transição da largura, deslocamento curto e fade; no mobile a altura também anima. Mantido o giro do ícone e respeitada a preferência por movimento reduzido. Validar visualmente no localhost. Sem commit/publicação a pedido do usuário.

- **30/10/2026, localhost em rede:** Vite de Projetos escuta em `0.0.0.0:5173`; `frontend/.env.local` usa `VITE_API=/api` para encaminhar chamadas ao backend local em `127.0.0.1:8000`. O IP atual do host é `192.168.0.160`. O backend local usa o banco PostgreSQL de produção no schema `treele`, com `--lifespan off` para não executar migrações na inicialização. A porta 5173 respondeu pelo IP na própria máquina. **Pendente com a TI:** abrir no Firewall do Windows a porta TCP 5173 para a rede confiável; a tentativa automática foi negada por falta de privilégio de administrador. Acesso Microsoft pelo IP não funciona com o redirect local `localhost:8000`; no outro PC, usar e-mail e senha ou configurar um endereço HTTPS apropriado. Sem commit/publicação a pedido do usuário.

- **30/10/2026:** frontend local atualizado no padrão visual do RH: entrada com foto integral gerada da equipe de projetos/obra e cartão central, ícone amarelo oficial do sistema também na aba do navegador, moldura clara com blur leve e ícone que recolhe/expande o menu com giro. Build validado. O preview da API em `localhost:8000` usa uma cópia SQLite em `%TEMP%` feita por backup somente leitura de `backend/data/treele-local.db`, com armazenamento local isolado; o banco original não foi alterado. A conta `ti@treele.com.br` está ativa na cópia. Sem commit/publicação a pedido do usuário.
- **30/10/2026, revisão Entra ID local:** `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` e `ENTRA_CLIENT_SECRET` estão presentes; o início redireciona para Microsoft e o callback chega a `localhost:8000` com cookie. O diagnóstico seguro mostrou **HTTP 401 / `invalid_client` / AADSTS7000215** na troca do código. A produção foi consultada somente para comparar o início do OAuth: **Tenant ID e Client ID são iguais aos locais**, e o usuário confirma que o login de produção funciona. Portanto o problema está no **Value do Client Secret local**. O preview foi reiniciado sem access log. **Pendente com a TI:** obter o Value válido existente ou criar um segredo separado para desenvolvimento no mesmo aplicativo Entra, atualizar apenas `backend/.env`, sem enviar o segredo no chat; reiniciar a API e testar novamente. Nenhum segredo foi alterado nesta revisão.
- **30/10/2026, exportação Vercel:** CLI autenticada como TI vinculou o projeto local `treele2/treele-projetos` para consulta e confirmou que `ENTRA_CLIENT_SECRET` existe em Production com tipo **Secret**. `vercel env run -e production` informou que valores desse tipo **não podem ser extraídos**; o arquivo `vercel-producao.env` fornecido pelo usuário é de 14/10 e não tem variáveis `ENTRA_*`. Nada foi exportado para o backend local, e a mudança automática do CLI em `.gitignore` foi revertida. Próximo passo: usar um Value guardado ou criar um segredo separado para localhost no mesmo registro Entra.
- **Próximo passo visual:** homologar em `http://localhost:5173/`; o trabalho funcional e as pendências da TREELE seguem abaixo.
- **29/10/2026:** no ar:
  - a **ata de análise crítica (PRO-FL-005 / modelo ENG-FL-001)**, obrigatória antes de liberar para obra, com PDF;
  - o campo **endereço** da obra;
  - o módulo **Fornecedores de projetos (PRO-FL-002)**: cadastro, qualificação documental e avaliação de desempenho,
    com os 2 fornecedores da planilha importados;
  - o **menu lateral** em três módulos, Projetos, Configurações e Qualidade, cada um com o título acima da linha.
  - **30/10/2026:** os **tipos de acesso** (administrador, comercial, todas as obras, obra específica), editáveis em
    Usuários. Os 97 acessos da planilha de cargos foram cadastrados, e cada pessoa entra com a conta Microsoft.
  - **30/10/2026:** **solicitação de acesso** para quem é de fora do domínio @treele (projetista ou comercial):
    pedido na tela de entrada, aprovação em Configurações → Solicitações de acesso, projetista só nas obras e
    disciplinas aprovadas. Módulos: Configurações e Qualidade só do administrador (com as exceções em
    `docs/permissoes.md`).

  Detalhes em `docs/ata-analise-critica.md`, `docs/fornecedores.md` e `docs/permissoes.md` (tipo de acesso).
- **Próximo passo:** a TREELE usar a ata e os fornecedores e dizer o que ajustar. Depois, seguir `docs/roteiro.md`.
- **Pendente com a TREELE:**
  - preencher o endereço das obras já cadastradas (Configurações da obra);
  - cadastrar os demais fornecedores;
  - confirmar se a sondagem fica com Fundação (FUN) e se o desempenho de vedação (VED) fica com Arquitetura.

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
- 2026-10-29 · Estágio de projetos (Vinícius) · Claude Code · módulo Fornecedores de projetos (PRO-FL-002) com avaliação de desempenho; menu lateral em três módulos (Projetos, Configurações, Qualidade) · (este commit)
- 2026-10-30 · Estágio de projetos (Vinícius) · Claude Code · tipo de acesso editável (novo: usuário de todas as obras), usuário sem senha entra com a Microsoft; cadastro dos 97 acessos da planilha de cargos · (este commit)
- 2026-10-30 · Estágio de projetos (Vinícius) · Claude Code · solicitação de acesso para externos (projetista por obra e disciplina, comercial), login de fora do domínio barrado com convite; Configurações e Qualidade só do administrador · (este commit)
- 2026-10-30 · Estágio de projetos (Vinícius) · Claude Code · chat: avaliações revistas — limite de tokens 2048 → 16000 (o raciocínio do Haiku 5.5 gastava tudo e a resposta saía vazia) e endereço da obra vindo do cadastro · (este commit)
- 2026-10-30 · Estágio de projetos (Vinícius) · Claude Code · 3D: câmera do conflito vai à região real das peças (conflitos antigos apontavam longe); pavimentos sem os vazios, agrupados por andar e com nome limpo · (este commit)
- 2026-10-30 · TI · Codex · visual local do portal e login ajustado ao cartão central do RH · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · favicon amarelo de Projetos e CHANGELOG.md local · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · API local passou a usar cópia isolada do banco local com a conta TI ativa, sem alterar o original · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · revisão do Entra local; AADSTS7000215 identificado e log seguro da troca do token · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · Vercel confirma segredo de produção não exportável; aguardando Value ou segredo local separado · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · perfil/tema e menu do usuário no frontend local; Vite aberto à LAN com proxy /api, firewall pendente de privilégio administrativo · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · menu lateral de Projetos com transição de largura, deslocamento e fade inspirada no RH · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · corrigido VITE_API herdado no processo local; frontend LAN agora chama /api pela mesma origem · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · corrigido contraste do modo escuro nas telas gerais e nos painéis do visualizador 3D · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · API local passou a usar S3 de produção com o banco já configurado; PDF validado por URL assinada · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · seletor de obra repaginado e carimbo de liberação legível no tema escuro · sem commit a pedido do usuário
- 2026-10-30 · TI · Codex · melhorias locais integradas aos commits novos de Projetos, com build e testes validados · 1251c4c (antes do ajuste final)
