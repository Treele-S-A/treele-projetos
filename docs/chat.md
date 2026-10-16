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

A conversa não fica guardada no servidor: a tela manda o histórico a cada
pergunta e esquece ao fechar o navegador.

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
