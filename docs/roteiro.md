# Roteiro

Registro das decisões técnicas e do que vem pela frente.

---

## Fase 1 — Controle de revisões ✅ pronta

Nomenclatura obrigatória com extração de campos, catálogo por
obra/disciplina/fase/formato, status com obsolescência automática, regra de
arquivo companheiro, papéis por obra, trilha de auditoria, lista mestra em CSV.
Acervo em duas visões: tabela com filtros e navegação por pastas
(disciplina → fase), com o histórico completo de cada documento dentro da pasta.

52 testes automatizados cobrindo as regras de negócio.

---

## Fase 1.5 — Colaboração (quase pronta: faltam os comentários na revisão)

**Estimativa: ~3 semanas**, mais o e-mail quando o TI liberar o envio.

Entra **antes** da Fase 2 de propósito. A solicitação de revisão fecha o ciclo
obra ↔ projetos, que é o trabalho de todo dia. O chat com IA ajuda a achar
coisas — importante, mas menos.

### O que entra

**Comentários na revisão.** Qualquer pessoa com acesso à obra comenta numa
revisão. O comentário fica preso à revisão, não ao documento: "o que foi dito
sobre a R02" continua verdade depois que a R03 sair.

**Solicitação de revisão.** Quem é da obra pede alteração, com descrição
obrigatória. A equipe de projetos é notificada, e a última revisão do documento
passa a exibir a solicitação em aberto.

**Notificações dentro do sistema.** Aba com contador de não lidas. Dispara em:
revisão liberada, revisão solicitada e comentário novo.

**Notificação por e-mail.** Depois — ver a dependência abaixo.

### Decisões tomadas (18/09/2026)

| Pergunta | Resposta |
|---|---|
| Como mostrar a solicitação | **Marca ao lado do status**, não status novo |
| Quem é notificado | ~~Toda a equipe de projetos~~ → definido em 02/10/2026, ver [notificacoes.md](notificacoes.md) |
| Engenheiro responsável | **Um por obra** |

Sobre a primeira: o carimbo continua `LIBERADO PARA OBRA`, com um aviso
*"revisão solicitada em 18/09 por Fulano"* ao lado. O status responde uma
pergunta só — *posso executar com isto?* — e a resposta continua sendo sim até
a revisão nova sair. A solicitação ganha ciclo próprio (aberta → atendida), que
é o que dá para cobrar prazo em cima.

### A dependência que não é nossa

E-mail precisa de servidor de envio. A TREELE usa Microsoft 365, então dá para
enviar pela conta corporativa, mas alguém do TI precisa liberar uma conta de
envio e configurar SPF e DKIM no domínio. Sem isso o e-mail cai em spam e a
funcionalidade nasce morta.

Por isso as notificações saem em duas partes: **dentro do sistema primeiro**
(não depende de ninguém, ~1 semana), e-mail quando o TI resolver.

### O que isso adianta da Fase 3

Enviar e-mail exige fila de tarefas assíncronas — a **mesma** fila que a Fase 3
usa para comparar revisões. Construir aqui adianta lá.

---

## Fase 2 — Chat com IA sobre o acervo ✅ pronta (06/10/2026)

Entregue com o Gemini, plano gratuito — ver [chat.md](chat.md).

**Estimativa: 1 a 2 semanas.** É rápido justamente porque a Fase 1 estruturou os
dados.

### A decisão de arquitetura

Não é busca semântica sobre o conteúdo dos arquivos. É a IA com **ferramentas que
consultam o banco do catálogo** — as mesmas consultas que a tela de acervo faz.

Perguntas que isso responde:

- "Quais projetos de estrutura ainda não têm revisão liberada para obra?"
- "Me dá a última revisão de arquitetura do pavimento tipo."
- "Quais disciplinas não entregaram nada na fase executiva?"
- "Que documentos foram liberados na última semana?"

Por que importa: com ferramentas sobre o banco, a IA **não inventa revisão que
não existe**. Ela chama `buscar_documentos(obra, disciplina, status…)` e responde
com o que voltou. Um RAG sobre o texto dos arquivos alucinaria número de revisão,
que é exatamente o erro que não se pode cometer aqui.

Busca semântica entra depois, como complemento, para achar documento por
descrição quando o código não ajuda.

### O que é preciso construir

- Endpoint de chat com histórico de conversa, escopado à obra e ao papel de quem
  pergunta (o cliente não pode descobrir pelo chat o que não enxerga na tela).
- Um conjunto pequeno de ferramentas: buscar documentos, detalhar documento,
  listar revisões, resumir pendências por disciplina.
- Interface de chat lateral, acessível de qualquer tela.

---

## Fase 3 — Descrição automática do que mudou entre revisões

**Estimativa: 3 a 6 semanas.** O campo `descricao_ia` já existe no modelo de
dados e já é exibido na interface — quando isso entrar, nada na API ou na tela
precisa mudar.

### A qualidade depende do formato, não da IA

| Formato | Viabilidade | Como |
|---|---|---|
| **IFC** | Excelente | `IfcOpenShell` (Python, open source). Compara GlobalIds entre as duas versões: elementos adicionados, removidos, propriedades alteradas, geometria modificada, quantitativos. A IA só transforma o diff estruturado em texto legível. Resultado confiável. |
| **PDF** | Muito bom | Extração de texto + renderização das páginas e diff visual. Os trechos alterados viram recortes de imagem enviados a um modelo com visão, que lê nuvem de revisão, cota alterada e nota nova. |
| **DWG** | Indireto | Não existe leitor nativo open source confiável. A regra de arquivo companheiro resolve: o diff é feito sobre o PDF plotado que acompanha o DWG, mais a tabela de revisões do carimbo. Alternativas pagas: SDK da ODA (anuidade na casa de milhares de dólares) ou Autodesk Platform Services (cobrança por crédito de conversão). |
| **RVT** | Indireto | Mesma situação. A regra de companheiro exige o IFC exportado, e aí cai no melhor caso da tabela. |

**É por isso que a regra de arquivo companheiro é obrigatória desde a Fase 1.**
Ela é o que torna esta fase possível sem licença paga: se a equipe sobe DWG+PDF e
RVT+IFC, existe descrição automática de qualidade em 100% do acervo.

### Arquitetura necessária

Esta fase é a primeira que precisa de **processamento assíncrono**. Comparar dois
IFCs de 200 MB leva minutos; isso não pode acontecer dentro da requisição HTTP.

- Fila de tarefas (Celery + Redis, ou RQ).
- Ao confirmar o envio de uma revisão, enfileira-se o diff contra a revisão
  anterior do mesmo documento.
- O resultado preenche `revisoes.descricao_ia`. A interface já mostra esse campo
  quando ele existe.
- O campo de descrição manual continua: a IA descreve o que consegue ler, a
  pessoa complementa o que só ela sabe.

---

## Fase 4 — Visualizador IFC 3D com comentários e marcações

**Estimativa: 4 a 8 semanas.**

### Base técnica

[That Open Engine](https://thatopen.com) (antigo IFC.js) — three.js + `web-ifc`
em WebAssembly, open source, feito exatamente para isto. Entrega carregamento de
IFC, árvore de elementos, painel de propriedades, corte e seção, medição e
isolamento.

IFC acima de ~200 MB precisa de pré-conversão no servidor para formato otimizado
e carregamento por streaming, senão trava o navegador. Essa conversão usa a mesma
fila da Fase 3.

### Comentários e marcações devem ser BCF

**BCF** (BIM Collaboration Format, padrão buildingSMART) é a decisão que vale
mais aqui. Um comentário vira um "tópico" com ponto de vista de câmera, GUIDs dos
elementos envolvidos, captura de tela e anotação.

A vantagem é grande: BCF **exporta e importa de Revit, Navisworks, Solibri e do
próprio Trimble Connect**. O sistema não vira uma ilha — vira o hub de
compatibilização, e o apontamento feito aqui abre direto no Revit do projetista.

"Desenhar em cima do modelo" é overlay 2D salvo junto com o ponto de vista, que é
justamente como o BCF já funciona.

---

## Decisões já tomadas

| Decisão | Escolha | Quando |
|---|---|---|
| Ordem de construção | Fase 0 + 1 completas antes das demais | set/2026 |
| Infraestrutura | Tudo em Docker; hospedagem definida na hora de subir | set/2026 |
| DWG e RVT | Exigir PDF plotado e IFC exportado junto, sem licença paga | set/2026 |
| Banco | Postgres em produção, SQLite só em desenvolvimento | set/2026 |
| Armazenamento | Object storage com URL assinada; arquivo nunca passa pela API | set/2026 |
| Nomenclatura | `{obra}-{disciplina}-{fase}-{prancha}-R{revisao}` | 17/09/2026 |
| Número da prancha | Formato livre — varia por obra | 17/09/2026 |
| Revisão | Sempre `R` + 2 dígitos | 17/09/2026 |
| Título | Fora do nome do arquivo; preenchido na tela do documento | 17/09/2026 |
| Título obrigatório | Pedido no primeiro envio do documento; reaproveitado nas revisões seguintes | 25/09/2026 |
| Solicitação de revisão | Coordenador ou obra pedem, com descrição obrigatória e fotos/PDF opcionais; marca ao lado do status; na liberação da revisão nova, quem libera marca os pedidos atendidos, que fecham; os outros seguem abertos. Avisa coordenadores e o projetista da última revisão | 02/10/2026 |
| Notificações | No sistema (contador no menu) e por e-mail via SMTP (Resend). Ver [notificacoes.md](notificacoes.md) | 02/10/2026 |
| Autorização de revisão | Coordenador autoriza ou recusa (com motivo) o pedido da obra, ou autoriza direto. Documento liberado só aceita revisão nova com revisão autorizada. Avisos: revisão enviada e pedido da obra → coordenadores; autorizada → projetista da última revisão; recusada → quem pediu; liberada → obra | 05/10/2026 |
| Administradores | Coordenadores de todas as obras, automaticamente — as de hoje e as futuras | 02/10/2026 |
| O que mudou na revisão | Obrigatório para quem sobe o primeiro arquivo da revisão (projetista ou coordenador); saiu do momento de liberar | 02/10/2026 |
| Disciplinas | 25 códigos (9 confirmados pela TREELE) | 17/09/2026 |
| Disciplina Comercial | `COM`, a pedido da TREELE | 02/10/2026 |
| Pastas no acervo | A fase abre na própria árvore (disciplina → fase → documentos) e o documento abre direto a tela dele; a tela própria de pasta saiu, e o endereço antigo leva à árvore com a pasta aberta | 06/10/2026 |
| Excluir obra | ~~Só administrador, com o código da obra digitado e a própria senha~~ → **não se exclui** obra nem revisão (09/10/2026, PBQP-H) | 06/10/2026 |
| Download em lote | No acervo (lista), qualquer pessoa marca documentos — de várias páginas — e baixa um ZIP com uma pasta por disciplina, escolhendo os formatos (PDF, DWG, IFC…). Vale a regra do download avulso, e cada arquivo baixado fica no registro. O ZIP é montado no navegador (no Chrome e no Edge, gravado direto no disco), sem passar pelo servidor | 21/10/2026 |
| Etapas do chat | O assistente mostra o que está fazendo (cada consulta, o que ela trouxe, o que a IA diz entre uma e outra); depois da resposta, ficam recolhidas em "Ver etapas" | 21/10/2026 |
| Avisos e liberação em lote | Coordenador escolhe se avisa (notificação e e-mail) ao enviar arquivo e ao liberar; projetista e obra avisam sempre. No acervo (lista), o coordenador marca revisões em revisão — de várias páginas — e libera todas de uma vez; as que não passam nas conferências voltam com o motivo | 15/10/2026 |
| Análise crítica | Revisão em revisão é a análise crítica do PBQP-H: o coordenador libera (observação opcional) ou reprova (observação obrigatória, vai por e-mail a quem enviou). A reprovada fica no histórico; a correção vem numa revisão nova, sem outra autorização. O administrador cancela revisão em qualquer status | 09/10/2026 |
| Painel de solicitações | Administrador vê no menu os pedidos de revisão de todas as obras, com filtro e contador dos que aguardam autorização; o item abre o documento no pedido | 06/10/2026 |
| Manter conectado | Opção no login: sessão de 30 dias na máquina (sem marcar, 12 horas). Trocar ou redefinir a senha derruba todas as sessões abertas; quem trocou a própria segue logado | 07/10/2026 |
| Disciplina Incêndio | `INC`, a pedido da TREELE; substitui o `PCI` da proposta inicial, desativado | 05/10/2026 |
| Perfil comercial | Todas as obras, só a disciplina COM liberada, só baixar — o acesso mais restrito do sistema | 02/10/2026 |
| Fases | 7 códigos: EP, AP, PL, PA, PB, PE, AB | 17/09/2026 |
| Revisão liberada | Aceita arquivo novo; substituição segue proibida | 17/09/2026 |
| Migrações | Alembic no lugar de `create_all` | 18/09/2026 |
| Responsável | Um engenheiro por obra, separado do papel de coordenador | 18/09/2026 |
| Acesso da obra | Vê liberado e obsoleto; não vê o que está em andamento | 22/09/2026 |
| Ordem das fases | Colaboração (1.5) antes do chat com IA (2) | 18/09/2026 |
| Hospedagem | ~~Render~~ → **Vercel** (Pro), para centralizar os sistemas da empresa em subdomínios; Render e VPS ficam como alternativa | 28/09/2026 |
| Banco em produção | Supabase, schema próprio `treele`. Começou numa conta pessoal (Free); em 09/10/2026 o projeto foi transferido para a organização da TREELE — mesmo endereço e mesmas chaves, nada mudou na Vercel | 30/09/2026 |
| Arquivos em produção | **Supabase Storage** (R2 dispensado): envio direto do navegador testado, sem configurar CORS | 30/09/2026 |
| Backup fora do Supabase | Diário pelo GitHub Actions para um site privado do SharePoint da TREELE: arquivos (espelho + excluídos por 90 dias) e `pg_dump` do banco (90 dias). Ver [backup.md](backup.md) | 09/10/2026 |
| Em produção | `projetos.treele.com.br` desde 30/09/2026. **Provisório:** Vercel no plano Hobby, que não permite uso comercial — passar para Pro antes do uso pela equipe | 30/09/2026 |
| Identidade visual | Cores, símbolo e site da treèle; carimbo de liberação redondo | 25/09/2026 |
| Visual dos painéis | Linguagem dos painéis da treèle (creme, cartões com bisel); títulos em IBM Plex Sans — reta, de engenharia; cada obra com a cor da sua identidade na capa | 01/10/2026 |
| Logo por obra | Enviado em Configurações; passa pela API, conferido pelos bytes, sem SVG | 25/09/2026 |
| Interface e API | Mesma imagem, mesmo processo: API sob `/api`, telas sob `/` | 22/09/2026 |

## Em aberto

- Login por SSO com Entra ID em vez de senha própria.
- Confirmar os 16 códigos de disciplina que vieram da proposta inicial (os 9
  novos já estão confirmados) — ver [nomenclatura.md](nomenclatura.md).
- Estratégia de migração do acervo atual — ver o fim de
  [nomenclatura.md](nomenclatura.md).
- Notificação por e-mail quando sai revisão nova em disciplina que a pessoa
  acompanha.
