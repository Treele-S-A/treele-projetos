# Fornecedores de projetos (PRO-FL-002)

Pedido da TREELE em 29/10/2026. A planilha "PRO-FL-002 – Fornecedores de
Projetos" virou o módulo **Qualidade → Fornecedores de projetos**: uma base em
tabela com os projetistas, a qualificação documental e o desempenho.

## Quem vê

Administradores e coordenadores de alguma obra, que são quem contrata e avalia
projetista. Projetista, equipe de campo e comercial não veem.

## Cadastro e qualificação documental

Os campos são os da planilha:
- código Sienge, razão social, nome fantasia, CNPJ;
- contato, e-mail, telefone e observações;
- escopos atendidos (ARQ, ELE, HID…, as mesmas colunas da planilha);
- padrões de empreendimento (MCMV, SBPE, alto padrão);
- ativo ou inativo.

A **qualificação documental** segue a fórmula da planilha:
- **qualificado** se tem registro no conselho (ou "não se aplica") e portfólio;
- **desqualificado** se falta um dos dois;
- **à qualificar** enquanto o registro não foi conferido.

## Avaliação de desempenho (procedimento 5.3)

Ao término das entregas contratadas, o coordenador avalia o projetista em
**Avaliar entrega**, no painel do fornecedor:

- **Empreendimento** (uma obra do sistema ou outra, digitada), escopo e data
  do término das entregas.
- Os quatro critérios do procedimento: qualidade do serviço, conformidade da
  documentação, prazo de entrega e atendimento/comunicação. Cada um é uma
  **régua de 1 a 10** com faixas (insatisfatório, regular, bom, excelente) e o
  que olhar em cada critério.
- O **mostrador** mostra a média enquanto se avalia, com a marca do mínimo
  **6**, a régua da planilha. Média 6 ou mais: "continua qualificado para
  novas contratações". Abaixo de 6: desqualificado, e o **motivo** passa a ser
  obrigatório.
- Cada avaliação fica no **histórico**: linha do tempo com as notas, o motivo
  e quem avaliou, mais a evolução das médias com a linha do 6.

**Situação** do fornecedor, na tabela: desqualificado se a qualificação
documental reprova **ou** se a última avaliação ficou abaixo de 6; pendente
enquanto a qualificação documental não foi conferida; senão, qualificado.

## Código

- `api/fornecedores.py`: regras e rotas:
  - `GET /fornecedores` e `GET /fornecedores/opcoes`;
  - `GET /fornecedores/{id}`;
  - `POST /fornecedores` e `PUT /fornecedores/{id}`;
  - `POST /fornecedores/{id}/avaliacoes`.
- Tabelas `fornecedores_projeto` e `avaliacoes_fornecedor` (migração
  `b8d0f2a4c6e9`). Tela: `paginas/Fornecedores.tsx`. Testes:
  `tests/test_fornecedores.py`.
- Os 2 fornecedores da planilha (CODICE e BAEPRO) foram importados em
  produção em 29/10/2026, com os dados que estavam nela.
