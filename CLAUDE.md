# Regras obrigatórias para qualquer IA (Claude, ChatGPT/Codex ou outra)

Valem para todas as pessoas que usam IA neste projeto. O mesmo texto está em `CLAUDE.md` (lido pelo Claude) e em
`AGENTS.md` (lido pelo ChatGPT/Codex e outras IAs). Se mudar um, mude o outro.

## 1. Antes de começar
- Leia o **`CONTEXTO_IA.md`** desta pasta: o que é o sistema, onde está publicado, como rodar, onde está cada coisa,
  cuidados e o histórico do que já foi feito.
- **Sua primeira resposta ao usuário começa pela seção "Onde paramos"** do `CONTEXTO_IA.md`, em 2 ou 3 linhas:
  "Paramos em … · próximo passo: … · pendente com você: …". Só depois siga com o pedido.
- Leia o mapa de todos os sistemas da Treèle: **`MAPA_SISTEMAS.md`** do repositório `Treele-S-A/treele-desenvolvimento`
  (em `C:\GitHub\Desenvolvimento`). Para baixar ou atualizar todos os projetos: `pwsh C:\GitHub\Desenvolvimento\baixar_tudo.ps1`.
- Rode `git pull` antes de mexer: outra pessoa pode ter trabalhado no projeto.

## 2. Ao terminar (obrigatório, mesmo em mudança pequena)
- Atualize o **`CONTEXTO_IA.md`**:
  - **reescreva "Onde paramos"** (data, o que ficou pronto, próximo passo, o que está pendente e com quem), para a
    próxima pessoa ou IA continuar dali;
  - acrescente uma linha no fim de **Histórico**: `AAAA-MM-DD · pessoa · IA usada · o que mudou · commit`;
  - se mudou endereço, banco, variável, pasta importante ou regra, corrija a seção correspondente.
- Se mudou algo que afeta outros sistemas (endereço, banco, integração, sistema novo ou desativado), atualize também
  o **`MAPA_SISTEMAS.md`** no `treele-desenvolvimento` e commite lá.
- Commite essas atualizações **junto com o trabalho**, respeitando as regras de branch do projeto (ver `CONTEXTO_IA.md`).

## 3. Sempre
- Nunca escreva senhas, tokens ou chaves nestes arquivos nem em nenhum arquivo do Git.
- Na dúvida sobre algo que publica em produção, apaga dados ou mexe em outro sistema: pergunte antes.
