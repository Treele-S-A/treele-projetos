# Registro de alterações — Portal de Projetos

## Não publicado

### 30/10/2026

- Interface local alinhada ao RH: foto da equipe na obra, login em cartão central, navegação clara e logo amarela que recolhe o menu.
- O ícone da aba do navegador usa o símbolo amarelo oficial de Projetos.
- Sem alterações de dados, commit ou publicação, conforme pedido do usuário.
- Preview local: API reiniciada com cópia isolada do SQLite local para permitir testar o acesso da conta TI; banco original preservado. O login Microsoft ainda depende do endereço de retorno cadastrado no Entra.
- Revisão Entra ID: o retorno local chega com cookie válido, mas a troca do código pela Microsoft falha com HTTP 401 / `invalid_client` / AADSTS7000215. Tenant ID e Client ID locais foram comparados com o início do OAuth em produção e coincidem. O backend local registra somente HTTP, tipo de erro e código AADSTS; a API foi iniciada sem log de URLs de acesso. Falta corrigir o Client Secret **Value** no `.env` local e retestar.
- Consulta à Vercel confirmou `ENTRA_CLIENT_SECRET` em Production com tipo **Secret** e indisponível para exportação pela CLI; arquivo exportado de 14/10 não o contém. Nenhuma variável de produção foi copiada para a API local.
- Segredo separado do Entra criado pela TI e carregado no localhost. O preview local passou a usar o banco de produção a pedido da TI, com migrações desativadas na inicialização.
- Menu lateral com abertura suave; menu da conta, edição do nome, troca protegida do e-mail e seleção de tema claro/escuro.
- Contraste do tema escuro corrigido em cartões, avisos e nos painéis do visualizador 3D. O canvas BIM/IFC e a identidade das obras foram preservados.
- Preview local passou a usar o S3 de produção para abrir os documentos já cadastrados no banco; conexão e leitura de PDF validadas, sem migrações ou alteração de arquivos.
- Seletor de obras da barra lateral redesenhado para os dois temas; carimbo de liberação com contraste adequado no modo escuro.
