# Roteiro

Registro das decisões técnicas e do que vem pela frente.

---

## Fase 1 — Controle de revisões ✅ pronta

Nomenclatura obrigatória com extração de campos, catálogo por
obra/disciplina/fase/formato, status com obsolescência automática, regra de
arquivo companheiro, papéis por obra, trilha de auditoria, lista mestra em CSV.

38 testes automatizados cobrindo as regras de negócio.

---

## Fase 2 — Chat com IA sobre o acervo

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
| Disciplinas | 25 códigos (9 confirmados pela TREELE) | 17/09/2026 |
| Fases | 7 códigos: EP, AP, PL, PA, PB, PE, AB | 17/09/2026 |
| Revisão liberada | Aceita arquivo novo; substituição segue proibida | 17/09/2026 |

## Em aberto

- Onde hospedar: VPS com Docker (mais barato, ~R$100–300/mês) ou Azure
  (integra com o Microsoft 365 da empresa, 3–5× mais caro).
- Login por SSO com Entra ID em vez de senha própria.
- Confirmar os 16 códigos de disciplina que vieram da proposta inicial (os 9
  novos já estão confirmados) — ver [nomenclatura.md](nomenclatura.md).
- Estratégia de migração do acervo atual — ver o fim de
  [nomenclatura.md](nomenclatura.md).
- Preencher o título já na tela de envio, para documentos novos. Hoje o título
  só é editável depois, na tela do documento.
- Notificação por e-mail quando sai revisão nova em disciplina que a pessoa
  acompanha.
