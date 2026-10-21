# Chat do acervo (Fase 2)

Botão **Perguntar ao acervo**, no canto de todas as telas. Responde perguntas
em português sobre documentos, revisões, liberações e solicitações de revisão,
com os documentos citados como links.

## Como funciona

A IA não lê o banco nem os arquivos. Ela pede consultas
(`backend/app/services/chat_ferramentas.py`), e cada uma passa pelas **mesmas
regras da tela**: quem é da obra não vê revisão em andamento, o comercial só
vê COM liberado, ninguém vê obra de que não participa. Como a resposta sai do
banco, a IA não inventa número de revisão. Tudo é só leitura.

Consultas disponíveis: listar obras, buscar documentos (por obra, disciplina,
fase, status ou trecho do código/título), detalhar documento (histórico,
arquivos, solicitações), resumo da obra por disciplina e status, liberações
recentes e solicitações de revisão.

### Leitura do PDF (07/10/2026)

Para perguntas sobre o **conteúdo** de uma prancha — carimbo, escala,
responsável, tabela de revisões, notas gerais, legendas, especificações,
ambientes — o assistente abre o PDF da revisão (a vigente, ou a que a pessoa
pedir) e o lê numa chamada à parte, que devolve só o texto lido.

- Segue a regra do download: só lê o que a pessoa poderia baixar. Cada
  leitura fica no registro de atividades como *Arquivo lido pelo assistente*.
- Lê PDF até 14 MB (`CHAT_PDF_MAX_MB`). DWG e RVT não: só o PDF que vai junto.
- **Letra miúda de prancha grande (16/10/2026):** o modelo vê a página como
  imagem reduzida, e numa A0 a anotação some — "Caixa d'água de polietileno,
  1000 litros" não era lida no MIL-HID-PE-AF. Por isso a leitura leva junto
  (`backend/app/services/pdf_leitura.py`, com o PDFium):
  - o **texto** gravado no PDF, exato (80% das pranchas do acervo têm);
  - nas páginas maiores que A3 **sem texto** (o CAD exportou as letras como
    desenho, comum na estrutura), **recortes ampliados** numa grade de 4 x 3,
    sem os pedaços em branco. Assim ele leu a tabela de aço inteira de uma
    prancha de armação. Custo da leitura: de US$ 0,001 a 0,005 no Haiku.
- **Medidas e cotas lidas do desenho podem ter erro.** O assistente avisa, e
  a conferência é sempre no PDF.
- No plano gratuito, **o conteúdo do PDF lido também vai para o Google** e
  pode ser usado para melhorar os produtos dele (decisão da TREELE em
  07/10/2026: seguir com o gratuito).

### Quantitativos dos modelos IFC (21/10/2026)

Perguntas como "qual a área de reboco do prédio?", "volume de concreto das
lajes" ou "quantas portas tem o 3º pavimento" vão para a consulta
`quantitativos_modelo`. Ela não abre o IFC: lê o **resumo de quantitativos**
guardado ao lado dele (`<chave do IFC>.r1.resumo.json`), gerado na conversão
para o 3D por `frontend/src/modelo3d/resumo-ifc.ts` — para cada categoria +
tipo + pavimento, quantos elementos, os materiais das camadas (com
espessura) e a soma das quantidades exportadas (BaseQuantities / Qto_*), já
em m, m² e m³.

- A busca é por material, tipo ou categoria, sem acento ("reboco",
  "ceramica argamassa"); sem busca, a consulta mostra o que o modelo tem,
  para o assistente escolher.
- Em parede, a **área lateral líquida** é uma face, sem as aberturas — numa
  parede de acabamento, a área do revestimento. Elemento que veio sem área
  nas quantidades (o Revit faz isso com IfcWall que não é reta) usa o
  parâmetro **"Área"** do programa de projeto, e o assistente diz isso.
- Vale a regra do download: a obra só soma o que está liberado. Cada consulta
  fica no registro como leitura pelo assistente.
- Teste com o SER-ARQ-PE-ESD R01 (Revit, 155 MB, resumo de 216 KB em 11 s):
  reboco interno 15.221 m² e externo 8.942 m², com os tipos de cada um, a
  pastilha (que tem reboco embaixo) à parte e o aviso de que é uma face.

### Qualquer parâmetro do modelo (21/10/2026)

Junto do resumo, a conversão gera o **índice completo de parâmetros**
(`<chave do IFC>.r1.indice.json.gz`): cada elemento com categoria, tipo,
pavimento, GlobalId, atributos (nome, tag, classe IFC), materiais,
quantidades e **todos** os parâmetros dos conjuntos de propriedades — os do
tipo entram como `Tipo · conjunto/parâmetro`. Medidas já em m, m², m³. No
SER-ARQ-PE-ESD: 19.107 elementos, 690 parâmetros, 20 MB que viram 1,1 MB.

A consulta `consultar_elementos` filtra por qualquer parâmetro (`contem`,
`igual`, `diferente`, `maior`, `menor`, `preenchido`), agrupa (por
pavimento, tipo, categoria ou parâmetro — vários juntos, separados por
vírgula), soma um parâmetro numérico e lista elementos. Com
`mostrar_campos`, mostra os parâmetros que existem e exemplos de valores:
é como o assistente descobre os nomes antes de filtrar. O índice lido fica
na memória da função enquanto ela está quente.

Teste: "quantas portas externas, por pavimento e tamanho?" — o assistente
viu que `Pset_DoorCommon/IsExternal` está "Não" em todas as 782 portas,
usou o comentário "ESQUADRIAS EXTERNAS" (282 portas), avisou disso e montou
as tabelas. O chat responde só o que foi modelado: parâmetro que o
projetista não preencheu não aparece.

### Etapas na tela (21/10/2026)

Enquanto o assistente trabalha, a tela mostra o que ele está fazendo: cada
consulta ("Buscando documentos de HID na obra CRE", "Lendo o PDF de
MIL-HID-PE-AF (R02)"), o que ela trouxe ("12 documentos encontrados") e o
que a IA diz entre uma consulta e outra. Depois da resposta, as etapas ficam
recolhidas em **Ver etapas**, acima dela. A rota é `POST /chat/fluxo`, que
responde em NDJSON (uma linha por evento: `etapa`, `resposta` ou `erro`); a
`POST /chat` antiga continua, com a resposta só no fim.

### Avaliação das respostas (21/10/2026)

Cada resposta tem 👍 e 👎. No 👎, um campo opcional "O que estava errado?".
Avaliar **guarda** a conversa até aquela resposta, as etapas, o comentário,
a obra da tela e o modelo que respondeu (tabela `avaliacoes_chat`) — é o
material para corrigir o assistente. Quem avaliou pode trocar o voto ou
acrescentar o comentário; ninguém mexe na avaliação de outro.

Para ler: `GET /api/chat/avaliacoes` (só administrador; `?nota=-1` para só
os 👎), mais recentes primeiro.

Cada 👎 manda um e-mail (pergunta, resposta, etapas e obra) para
`CHAT_AVISAR_AVALIACOES` — padrão `estagio.projetos@treele.com.br`, vírgula
separa vários, vazio desliga. O comentário vem depois do voto, então sai um
segundo e-mail com o mesmo assunto quando ele chega. Trocar um 👍 por 👎
também avisa. Usa o mesmo SMTP das notificações (`services/aviso_avaliacao.py`).

Fora o e-mail, nada é automático e nada treina o modelo: os 👎 são lidos sob pedido,
agrupados pela causa, e a correção vai nas instruções, nas consultas ou no
extrator, com teste. Primeiro caso (21/10/2026): "quantos metros de PVC
marrom/água fria" — o chat parou no resumo, que não tem comprimento de tubo,
e disse que o modelo não tinha a medida; o índice tinha `Dimensions/Length`
(4.147 m de PVC marrom no SER-HID-PE-AGUA R00). Agora o resumo sem medida
aponta para `consultar_elementos`.

A conversa não fica guardada no servidor: a tela manda o histórico a cada
pergunta e esquece ao fechar o navegador. A exceção é a resposta avaliada.

## Fornecedor (06/10/2026)

**Google Gemini, plano gratuito**, modelo `gemini-3.8-flash`, pela API nativa
(a "compatível com OpenAI" tem problemas conhecidos com várias rodadas de
consulta). Tudo que é do fornecedor está em
`backend/app/services/chat_modelo.py`: trocar de fornecedor é reescrever só
esse arquivo.

Quando o Google responde que o modelo está sobrecarregado (503, comum no
plano gratuito em horário de pico), o chat espera um instante e repete, e
depois passa pelos modelos reserva, em ordem: `gemini-3.7-flash` e
`gemini-3.5-flash` (`CHAT_MODELO_RESERVA`, separados por vírgula). Cota
esgotada (429) e modelo indisponível (404) pulam direto para o próximo — a
cota gratuita é por modelo. O `gemini-2.5-flash` não serve: o Google não o
libera mais para chave nova. Só se todos falharem a pessoa vê o aviso de
sobrecarga. Administrador vê, junto da mensagem de erro, o motivo técnico.

Limites e condições do plano gratuito:

- **20 chamadas por dia por modelo** (medido em 16/10/2026; antes eram 1.000 a
  1.500). Cada pergunta usa de 1 a 5 chamadas, então o gratuito aguenta umas
  10 a 15 perguntas por dia somando os três modelos. Passou do limite, o chat
  avisa e pede para esperar.
- **O Google pode usar o que é enviado** (pergunta, resposta e o resultado das
  consultas: códigos, títulos, nomes da equipe) para melhorar os produtos
  dele. No plano pago isso não acontece. Para uso pela empresa, migrar para um
  plano pago (Gemini pago ou Claude).

## Claude (Anthropic), em teste desde 16/10/2026

O chat também funciona com o Claude, pela API da Anthropic
(`backend/app/services/chat_claude.py`), com as mesmas consultas e as mesmas
regras. Modelo padrão: `claude-haiku-5-5` (`CHAT_MODELO_CLAUDE`).

- **Qual fornecedor responde:** com `ANTHROPIC_API_KEY` configurada, o Claude;
  sem ela, o Gemini. `CHAT_FORNECEDOR=gemini` (ou `claude`) força um dos dois
  quando as duas chaves estão configuradas. A nota no rodapé do chat diz qual
  está respondendo.
- **Custo:** a API é paga por uso, com crédito pré-pago no console da
  Anthropic. Acabou o crédito, o chat para e avisa "Os créditos do assistente
  acabaram"; não há conta surpresa. A API não usa o que é enviado para
  treinar modelos.
- **Sobrecarga (529) ou limite por minuto (429) com espera curta:** repete uma
  vez depois de uma pausa. Não há modelo reserva.
- As instruções e as consultas vão com cache: da segunda rodada em diante,
  essa parte custa um décimo.
- A API do Claude não vem com a assinatura do Claude da empresa: é cobrada à
  parte.

## Ligar

1. Em [aistudio.google.com](https://aistudio.google.com), **Get API key →
   Create API key** (sem cadastrar cartão, fica no plano gratuito).
2. Na Vercel (Settings → Environment Variables, só Production):
   `GEMINI_API_KEY` = a chave. Opcional: `CHAT_MODELO` para outro modelo.
3. Redeploy. Sem a chave, o botão nem aparece.

Com o Claude: em [console.anthropic.com](https://console.anthropic.com),
**API Keys → Create Key**, e na Vercel `ANTHROPIC_API_KEY` = a chave (a do
Gemini pode ficar, como volta rápida: basta apagar a do Claude). Crie a
chave **dentro de um workspace**; chave da organização, fora de workspace,
exige também `ANTHROPIC_WORKSPACE_ID` (o ID do workspace, `wrkspc_...`).

Teste com o acervo real (16/10/2026, Haiku 5.5, cópia local do banco): 21
perguntas em quatro papéis, todas certas conferidas com o banco e com o texto
do PDF; nenhuma vazou o que o papel não vê. Média de US$ 0,0008 por pergunta
(a mais cara, leitura de um descritivo de personalização, US$ 0,004) e de 3 a
25 segundos.
