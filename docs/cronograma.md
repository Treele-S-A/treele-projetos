# Cronograma de projetos (Gantt) — PRO-FL-001

Desde 03/11/2026. Módulo **Qualidade → Cronograma de projetos**. Um cronograma
por obra; só os **coordenadores** da obra veem e mexem (administrador é
coordenador de todas). Projetista, obra e comercial recebem 403.

## Como as datas saem

Nada de data guardada na atividade: o servidor calcula a cada leitura
(`backend/app/services/cronograma.py`).

- **Dias úteis**, segunda a sexta. Feriado não entra (ainda).
- Sem predecessora, a atividade começa no **início do projeto**.
- Vínculos: **TI** (término-início, o padrão), **II** (início-início) e
  **TT** (término-término), com **defasagem** em dias úteis (negativa adianta).
- **Duração 0** é marco (losango).
- Arrastar a barra grava o **"não iniciar antes de"** (`inicio_fixo`), que
  aparece com um ponto ao lado do início; clicar no ponto devolve a atividade
  ao cálculo. Puxar a ponta direita muda a duração.
- **Folga** e **caminho crítico** pela ida e volta (CPM): folga zero é o que
  atrasa o fim do projeto; a barra fica vermelha. Laranja: atrasada (previsão
  além do planejado). Azul: em andamento. Verde: concluída. "Hoje" é sempre o de
  Brasília (`services/tempo.py`), mesmo com o servidor em UTC.

Toda alteração devolve o cronograma inteiro recalculado; a tela não faz conta.

## Planejado × realizado e status (03/11/2026)

- **Status** no lugar do %: Não iniciado, Em andamento, Concluído. Status e
  datas andam juntos: marcar Em andamento registra o início realizado (hoje);
  Concluído, o término (hoje). Preencher as datas acerta o status.
- **Planejado**: o cálculo pelo plano (durações, vínculos, "não iniciar antes
  de"). Congela quando a atividade começa (`inicio_base`/`termino_base`): mudar
  o plano depois não apaga o atraso já registrado.
- **Realizado**: início e término que a equipe registra.
- **Previsão** (as barras): o realizado onde houver; o que não começou não
  começa antes de hoje; o que está em andamento termina no mínimo hoje.
- **Atraso**: término realizado (ou previsto) menos o planejado, em dias úteis.
  O término realizado fica vermelho quando atrasou e verde no prazo; o traço
  fino sob a barra é o planejado. No topo: concluídas, no prazo, concluídas
  com atraso e atrasadas em aberto.

## Na tela

- Tela cheia, como o visualizador 3D: o menu recolhe ao abrir (o logo traz de
  volta) e o Gantt ocupa a altura toda. A tabela tem três tamanhos — completa,
  compacta (planejado, realizado e status; o padrão) e só nomes —, e o navegador
  lembra a escolha.
- Tabela editável: nome, responsável, dias, início planejado (muda o "não iniciar
  antes de"), término planejado (muda a duração), início e término realizados,
  status e predecessoras no formato do MS Project:
  `3; 5II+2; 7TT-1` (aceita também FS/SS/FF).
- Fases recolhíveis, com barra de resumo; dois cliques no nome renomeiam.
- Painel da atividade (clique na linha): fase, área, observação, vínculos um a
  um, sucessoras, subir/descer, inserir abaixo, apagar.
- Escala em dias, semanas ou meses; "Hoje"; liga/desliga vínculos e caminho
  crítico; exportar CSV para o Excel.

## O modelo (48 atividades, 7 fases)

Desde 03/11/2026 o modelo é o cronograma do **Residencial Treviso (TRE)** como a
equipe o ajustou (nomes "Aprovação Copel/Sanepar", executivos com "executivo"
no nome, responsáveis), menos o projeto de drenagem, a aprovação nas
concessionárias e a fase de análise de engenharia da CEF. A aprovação do
projeto de drenagem passou a depender da terraplenagem. Abaixo, a primeira
versão, de onde o Treviso partiu.

### Primeira versão (56 atividades, 8 fases)

Compilado em 03/11/2026 de duas planilhas:

- **PRO-FL-001** (Cronograma técnico de contratação e desenvolvimento de
  projetos): fases Preliminares, Projetos, Laudos e estudos e PCP, e os
  responsáveis já preenchidos (Caique, Eduardo, Ewander).
- **Macrofluxo do Vivere Due** (Cockpit Novos Negócios e Incorporação): as
  seções e as 49 predecessoras, incluindo o único II (gás com o ante-projeto
  de incêndio).

Decisões:

- O que as duas tinham com nomes diferentes virou uma linha (ensaio de ruído =
  análise de entorno de ruído; simulação de desempenho = termo-lumínica +
  acústica).
- Atividades de Incorporação, PCP e da Caixa que o macrofluxo usa como
  predecessoras (passagem, SPE, RI, transferência, PGRCC, orçamento
  preliminar…) entram, senão os vínculos ficam soltos.
- Acrescentados os vínculos óbvios que faltavam: análises da CEF em sequência;
  executivos a partir do arquitetônico em II com defasagem (estrutura +10,
  hidro +10, elétrico +10, fundações +15 da estrutura); compatibilização depois
  de todos os executivos; PCP (cronograma de obra, orçamento, 4D) depois da
  compatibilização.
- **Durações estimadas**: nenhuma planilha traz duração (as datas do
  macrofluxo são quase todas de um dia). Cada coordenador ajusta na obra.
- Pontos de revisão da planilha do Vivere Due que seguem valendo: confirmar com
  a Incorporação se a 1ª análise da CEF depende mesmo do RI e da transferência,
  e se a aprovação nas concessionárias depende do paisagismo.
- "FRE", "PDE" e "PCT" ficaram com o nome da PRO-FL-001.

## Tabelas

`cronogramas` (um por obra, início), `cronograma_atividades` e
`cronograma_vinculos` (migração `e2b4d6f8a0c3`). Apagar a obra apaga o
cronograma.
