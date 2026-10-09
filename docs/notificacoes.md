# Notificações

Avisos no sistema (item *Notificações* no menu, com contador de não lidas) e
por e-mail, quando o e-mail está configurado.

## Quem recebe o quê (05/10/2026)

| Evento | Quem recebe |
|---|---|
| **Revisão nova enviada** (primeiro arquivo dela) | Os **coordenadores** da obra. Os administradores entram, porque são coordenadores de todas as obras. |
| **Pedido de revisão da obra** | Os **coordenadores**, que autorizam ou recusam. |
| **Revisão autorizada** (de um pedido ou direto pelo coordenador) | O **projetista que subiu a última revisão** do documento, só ele. É aqui — e não no pedido — que o projetista fica sabendo. |
| **Pedido recusado** | Quem pediu, com o motivo. |
| **Revisão liberada para obra** | As pessoas com papel **obra**. É o único aviso que a obra recebe. Um por revisão, nunca por arquivo. |
| **Revisão reprovada** na análise crítica (09/10/2026) | **Quem enviou a revisão** — quem a criou ou mandou arquivo dela —, com a observação do coordenador. |

Detalhes:

- **"Última revisão"** é a mais recente que não foi cancelada, mesmo que ainda
  esteja em revisão. Se já há uma R02 subindo pela mão de outro projetista, é
  ele quem precisa saber da autorização feita sobre a R01. Conta como "quem
  subiu" quem criou a revisão ou enviou algum arquivo dela.
- **Revisão enviada avisa uma vez.** O segundo arquivo da mesma revisão (o DWG
  depois do PDF) ou um arquivo substituído não avisam de novo. Arquivo novo
  numa revisão já liberada também não.
- **A liberação avisa a obra, o envio não.** Antes de liberada, a revisão nem
  aparece para a obra, e o link levaria a algo que ela não pode abrir.
- **Quem fez a ação não é avisado dela.** O coordenador que autoriza não
  recebe a própria autorização; quem envia não recebe o próprio envio.
- O perfil comercial não recebe aviso nenhum.
- Clicar no aviso abre o documento e marca o aviso como lido. Cada pessoa marca
  os seus.

## E-mail

Desde 06/10/2026 o e-mail sai com a cara da Treèle: cabeçalho petróleo com o
símbolo, a régua nas três cores da marca, um selo dizendo o que aconteceu, a
prancha como título, o pedido ou o motivo em destaque e o botão **Abrir
documento**. A faixa lateral leva a cor da obra. O símbolo vai dentro da
mensagem — aparece mesmo no programa que bloqueia imagem de fora — e a versão
em texto puro segue junto, para quem lê sem HTML. Modelo em
`backend/app/services/email_modelo.py`.

O sistema envia por **SMTP**, então serve qualquer serviço: Microsoft 365 (o que
a TREELE usa), Google Workspace, Resend e outros. Trocar de serviço é trocar
variável de ambiente, não código.

**Sem configuração, o e-mail fica desligado** e os avisos aparecem só no
sistema. Se o servidor de e-mail falhar, o aviso continua no sistema e a ação
(pedir revisão, liberar) acontece normalmente.

### Variáveis (Vercel → Settings → Environment Variables, só Production)

| Variável | Exemplo |
|---|---|
| `EMAIL_SMTP_HOST` | `smtp.office365.com` |
| `EMAIL_SMTP_PORTA` | `587` (padrão; use `465` se o serviço pedir SSL direto) |
| `EMAIL_SMTP_USUARIO` | a conta que envia |
| `EMAIL_SMTP_SENHA` | a senha dela (ou a chave do serviço) |
| `EMAIL_REMETENTE` | `Treèle Projetos <projetos@treele.com.br>` |

Basta `EMAIL_SMTP_HOST` para ligar. Com ela definida e alguma das outras
faltando, o sistema não sobe e diz qual falta. Os links dos e-mails usam o
domínio de produção que a própria Vercel informa (`projetos.treele.com.br`);
para forçar outro endereço, defina `SITE_URL`.

### Opção 1: Microsoft 365 (conta da empresa)

Depende do TI:

1. Uma caixa para enviar, por exemplo `projetos@treele.com.br`.
2. **SMTP AUTH** ligado para essa caixa (Admin do Microsoft 365 → Usuários →
   a caixa → Email → Gerenciar aplicativos de email → *SMTP autenticado*). Vem
   desligado por padrão.
3. SPF e DKIM do domínio. Num domínio que já envia pelo Microsoft 365, isso
   costuma estar pronto.

Variáveis: host `smtp.office365.com`, porta `587`, usuário e senha da caixa.
`EMAIL_REMETENTE` tem de ser essa mesma caixa: o Microsoft 365 recusa remetente
diferente da conta que autentica.

**Atenção:** a Microsoft vem desligando o SMTP com usuário e senha ("basic
auth") no Exchange Online. Confirme com o TI se ainda está disponível no
tenant da TREELE antes de contar com esta opção. Se não estiver, use a opção 2.

### Opção 2: Resend (serviço de envio) — a escolhida em 02/10/2026

Gratuito até 3.000 e-mails por mês e 100 por dia.

1. Criar a conta em resend.com.
2. **Domains → Add Domain**: `projetos.treele.com.br`, região **São Paulo (sa-east-1)**.
3. O Resend mostra os registros DNS: um DKIM (TXT) e os do subdomínio
   `send`. O DNS do `treele.com.br` fica na **SiteGround** (Site Tools →
   Domain → DNS Zone Editor). Lá, o campo *Name* leva só o prefixo — por
   exemplo `resend._domainkey.projetos` —, porque a SiteGround completa com
   `.treele.com.br`. Ficam em `resend._domainkey.projetos.treele.com.br` e
   `send.projetos.treele.com.br`, então **não mexem no e-mail da empresa**
   (Microsoft 365), que usa os registros da raiz.
4. Clicar em **Verify DNS Records** e esperar o domínio ficar **Verified**.
   Antes disso, todo envio volta com "550 … domain is not verified".
5. **API Keys → Create API Key**: permissão *Sending access*, domínio
   `projetos.treele.com.br`. A chave aparece uma vez só, e vai direto para a
   Vercel.

Variáveis: host `smtp.resend.com`, porta `587`, usuário `resend`, senha = a API
key, remetente `Treèle Projetos <avisos@projetos.treele.com.br>`. O domínio do
remetente tem de ser **exatamente** o verificado no Resend: com
`@treele.com.br` ele recusa ("treele.com.br domain is not verified"). O endereço
não precisa existir como caixa de e-mail.

Sem os registros no DNS, nos dois casos, o e-mail sai mas cai no spam.

### Conferir

Depois do Redeploy, um administrador entra em **Minha conta → Enviar e-mail de
teste**. O e-mail vai para ele mesmo, sem gerar aviso para a equipe. Se não
sair, a tela diz o motivo (senha recusada, domínio não verificado, servidor
inalcançável). `/api/saude` mostra `"email": true` quando o envio está ligado.
