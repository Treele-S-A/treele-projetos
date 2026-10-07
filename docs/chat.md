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
depois troca para o modelo reserva, `gemini-2.5-flash`
(`CHAT_MODELO_RESERVA`). Só se todos falharem a pessoa vê o aviso de
sobrecarga. Administrador vê, junto da mensagem de erro, o motivo técnico.

Limites e condições do plano gratuito:

- Algo como 10 a 15 perguntas por minuto e 1.000 a 1.500 por dia. Passou do
  limite, o chat avisa e pede para esperar um minuto.
- **O Google pode usar o que é enviado** (pergunta, resposta e o resultado das
  consultas: códigos, títulos, nomes da equipe) para melhorar os produtos
  dele. No plano pago isso não acontece. Para uso pela empresa, migrar para um
  plano pago (Gemini pago ou Claude).

## Ligar

1. Em [aistudio.google.com](https://aistudio.google.com), **Get API key →
   Create API key** (sem cadastrar cartão, fica no plano gratuito).
2. Na Vercel (Settings → Environment Variables, só Production):
   `GEMINI_API_KEY` = a chave. Opcional: `CHAT_MODELO` para outro modelo.
3. Redeploy. Sem a chave, o botão nem aparece.
