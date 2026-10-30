# Registro de alterações — Portal de Projetos

## 30/10/2026

- Entrada e navegação alinhadas ao visual do RH, com foto de projetos/obra, ícone amarelo oficial, menu lateral animado e menu da conta.
- Tema claro/escuro, com contraste revisado em documentos, avisos e painéis do visualizador 3D. Canvas BIM/IFC e identidade das obras preservados.
- Seletor de obras redesenhado e carimbo de liberação legível no tema escuro.
- Minha conta permite editar nome e, mediante senha atual, e-mail corporativo. O e-mail de contas Microsoft continua dependente de alteração no Entra ID pela TI.
- Login por senha agora exibe o erro devolvido pela API; diagnóstico do retorno Microsoft registra apenas tipo e código de erro, sem código OAuth nem segredo.
- Integradas as melhorias recentes da equipe de Projetos em acesso por perfil, solicitações externas, chat e visualizador 3D.

### Configuração local

- O preview de `localhost:5173` usa `/api`; para abrir documentos de produção, o backend local usa o banco e o S3 de produção somente por variáveis de ambiente locais. Nenhum segredo ou arquivo `.env` faz parte desta versão.
