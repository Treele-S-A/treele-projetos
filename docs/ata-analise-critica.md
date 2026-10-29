# Ata de análise crítica (PRO-FL-005)

Pedido da TREELE em 29/10/2026, para o SIAC: nenhuma revisão é liberada para
obra sem a ata de análise crítica preenchida.

## Como funciona

1. O coordenador clica em **Liberar para obra…**, na revisão ou no lote do
   Acervo. Se falta a ata, abre antes o pop-up com o checklist.
2. Cada item recebe uma resposta: **S**, **N** ou **N/A**. Item **N** exige
   comentário. "Restantes: S" e "Restantes: N/A" preenchem o que falta num
   grupo. Há também um campo de observações gerais.
3. **Salvar e gerar ata de análise crítica** registra a ata, numerada por obra
   (`ATA-UNO-007`). Depois disso:
   - **Ata conforme**: a liberação segue normalmente (observação e aviso à obra).
   - **Algum N**: a ata fica registrada como **não conforme** e a revisão **não é
     liberada** (decisão da TREELE). A tela já abre a reprovação com os itens N
     na observação. A outra saída é refazer a análise: uma ata nova substitui a
     não conforme.
4. A ata fica disponível em dois lugares:
   - no link da revisão, na página do documento;
   - em **Atas de análise crítica**, no menu lateral, com filtros por obra,
     disciplina, resultado e documento.

   A página da ata imprime ou salva em PDF (botão "Imprimir ou salvar PDF").

- **Uma ata por liberação**: as revisões da mesma obra e disciplina liberadas
  juntas cabem numa ata só. Um lote com várias disciplinas abre um checklist
  por disciplina, em sequência.
- **Uma ata por revisão**: uma revisão com ata conforme não ganha outra.
- **Quem preenche**: quem pode liberar (permissão `publicar`). A equipe da obra
  vê as atas; o perfil comercial não vê.
- A ata não se edita. Ela guarda as perguntas e as respostas como foram dadas,
  e os documentos e revisões como estavam, mesmo que a planilha mude depois.

## Quais itens aparecem

A planilha é dividida pelo **projeto analisado**, e cada bloco recomeça em
"1.1 RGF". Dentro de um bloco, a coluna DISC diz com que disciplina o item
compatibiliza. Por exemplo, o bloco da Hidráulica tem itens EST ("passagens em
vigas e lajes") que se conferem no projeto de hidráulica.

A disciplina da revisão escolhe o bloco inteiro. Os itens de **representação
gráfica** entram sempre, sem repetição: são 7, juntando os RGF de todos os
blocos. As colunas de fase (estudo preliminar, executivo) e de quem confere
ficaram de fora, porque a ata é respondida uma vez por revisão.

| Disciplina do sistema | Bloco da planilha |
|---|---|
| ARQ | Arquitetura, mais desempenho de ARQ e de VED |
| EST | Estrutura, mais desempenho de EST |
| HID | Hidráulica, mais desempenho de HID |
| ELE | Elétrica |
| FUN | Sondagem + Fundação, mais desempenho de FUND |
| TOP | Levantamento planialtimétrico |
| CTL | Simulações de desempenho (DES) |
| as demais (GAS, INC, CLI…) | só representação gráfica |

## Código

- Itens: `backend/app/services/checklist_pro_fl_005.json`, gerado da planilha
  por `backend/scripts/gerar_checklist_pro_fl_005.py`. Numa revisão nova da
  planilha, confira as faixas de linhas e gere de novo.
- Regras: `backend/app/services/atas.py`. A trava fica em
  `conferir_publicacao` (`services/revisoes.py`), que vale para a liberação
  avulsa e para a liberação em lote. `ATA_ANALISE_OBRIGATORIA=false` desliga a
  trava; só os testes usam isso.
- Rotas (`api/atas.py`):
  - `POST /atas/pendentes`: dos ids, os que pedem ata, por obra e disciplina,
    com o formulário;
  - `POST /atas`;
  - `GET /atas`;
  - `GET /atas/{id}`.
- `GET /revisoes/{id}/verificar` traz `falta_ata` e `ata_impedimento`. A
  revisão traz `ata`, a que vale.
- Tela: `FormularioAta.tsx` (o pop-up), `Revisoes.tsx`, `paginas/Acervo.tsx`,
  `paginas/Atas.tsx` e `paginas/Ata.tsx`.
- Tabelas `atas_analise` e `atas_analise_revisoes` (migração `f6a8c0e2b4d6`).
- Testes: `tests/test_atas.py`.

As revisões liberadas antes de 29/10/2026 não têm ata. A trava vale só para as
liberações daqui em diante.
