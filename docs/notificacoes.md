# Notificações

Avisos no sistema (item *Notificações* no menu, com contador de não lidas) e
por e-mail, quando o e-mail está configurado.

## Quem recebe o quê (02/10/2026)

| Evento | Quem recebe |
|---|---|
| **Pedido de revisão novo** | Os **coordenadores** da obra, sempre. Os administradores entram, porque são coordenadores de todas as obras. O **projetista** só se foi ele quem subiu a última revisão do documento. |
| **Revisão liberada para obra** | As pessoas com papel **obra**. Um aviso por revisão, nunca por arquivo. |

Detalhes:

- **"Última revisão"** é a mais recente que não foi cancelada, mesmo que ainda
  esteja em revisão. Se já há uma R02 subindo pela mão de outro projetista, é
  ele quem precisa saber do pedido feito sobre a R01. Conta como "quem subiu"
  quem criou a revisão ou enviou algum arquivo dela.
- **A liberação avisa, o envio não.** Antes de liberada, a revisão nem aparece
  para a obra, e o link levaria a algo que ela não pode abrir.
- **Quem fez a ação não é avisado dela.** O coordenador que pede revisão não
  recebe o próprio pedido.
- O perfil comercial não recebe aviso nenhum.
- Clicar no aviso abre o documento e marca o aviso como lido. Cada pessoa marca
  os seus.

## E-mail

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
endereço do próprio sistema (`BASE_URL` sem o `/api`).

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

### Opção 2: Resend (serviço de envio)

Gratuito até 3.000 e-mails por mês e 100 por dia.

1. Criar a conta em resend.com e adicionar o domínio `treele.com.br`.
2. Cadastrar no DNS do domínio os registros que o Resend mostrar (SPF e DKIM).
   É quem administra o domínio que faz isso.
3. Criar uma API key.

Variáveis: host `smtp.resend.com`, porta `587`, usuário `resend`, senha = a API
key, remetente com qualquer endereço `@treele.com.br`.

Sem os registros no DNS, nos dois casos, o e-mail sai mas cai no spam.
