# Ata de análise crítica (PRO-FL-005)

Pedido da TREELE em 29/10/2026, para o SIAC: nenhuma revisão é liberada para
obra sem a ata de análise crítica preenchida.

## Como funciona

1. O coordenador clica em **Liberar para obra…**, na revisão ou no lote do
   Acervo. Se falta a ata, abre antes o pop-up com o checklist.
2. Cada item recebe uma resposta: **S**, **N** ou **N/A**. Item **N** exige
   comentário. No topo, **Marcar todos como S** marca o checklist inteiro;
   depois se ajustam só os N e N/A. "Restantes: N/A" preenche o que falta num
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

   Na página da ata, **Ver PDF** e **Baixar PDF** trazem o arquivo
   `ATA-UNO-007.pdf`, gerado no servidor no modelo ENG-FL-001: é o mesmo
   arquivo para todos, sem depender da impressão do navegador. **Imprimir**
   continua disponível.

## O documento: modelo ENG-FL-001

A ata segue o modelo Word da Treèle, "ENG-FL-001 – Ata Análise Crítica de
Projeto Arquitetônico" (pedido de 29/10/2026). A página reproduz esse modelo e
repete o cabeçalho e a faixa do rodapé em cada página impressa.

- **Cabeçalho**: logo da treèle, "Análise crítica de projeto {disciplina}" e,
  à direita, ENG-FL-001 com a data da ata. O adjetivo vem da disciplina:
  arquitetônico, estrutural, hidrossanitário, elétrico… (`ADJETIVO` em
  `paginas/Ata.tsx`).
- **Projeto**: "Projeto {disciplina} do empreendimento {nome}, localizado na
  {endereço}", mais os documentos e as revisões analisados. O endereço vem da
  obra:
  - é obrigatório ao criar uma obra;
  - nas obras antigas, preenche-se em Configurações da obra → Endereço do
    empreendimento.
- **Itens analisados**: o que foi respondido no checklist, com SIM, NÃO e N/A.
  O modelo só tem SIM e NÃO; a coluna N/A foi acrescentada para os itens que
  não se aplicam. O comentário de cada item vem logo abaixo dele.
- **Solicitação de alterações**: só tem linha quando a revisão foi
  **reprovada**. Cada linha traz:
  - a revisão;
  - a data e quem reprovou;
  - o motivo da reprovação (obrigatório) como alteração solicitada;
  - como data do recebimento, a data em que chegou a revisão seguinte do
    documento.

  A reprovação vem depois da ata, por isso a página lê a situação atual da
  revisão.
- **Analisado por**: sempre "Luigi Gasparin Ogliari" (`ATA_ANALISADO_POR`,
  em `config.py`).

O PDF sai de `services/ata_pdf.py` (ReportLab): `GET /atas/{id}/pdf`, com o
mesmo controle de acesso da ata. O logo está em
`services/logo-treele-construtora.png`. O adjetivo do título vem de
`ADJETIVOS`, em `services/atas.py`, e a página da ata usa o mesmo.

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
